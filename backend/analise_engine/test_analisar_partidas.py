"""Testes unitários da análise de partidas."""

import unittest
from unittest.mock import MagicMock, patch

from backend.analise_engine.analisar_partidas import (
    AnalysisSettings,
    PlayerMoveEval,
    detectar_erosao,
    processar_partida,
    processar_partida_com_timeout,
)


class FakeEngine:
    """Engine falso que fornece avaliações apenas quando consultado."""

    def __init__(self) -> None:
        self.evaluations = iter(
            [
                {"type": "cp", "value": -20},
                {"type": "cp", "value": -30},
                {"type": "cp", "value": -40},
            ]
        )
        self.evaluation_calls = 0

    def set_fen_position(self, _fen: str) -> None:
        pass

    def get_evaluation(self) -> dict[str, str | int]:
        self.evaluation_calls += 1
        return next(self.evaluations)


class ProcessarPartidaTest(unittest.TestCase):
    def test_lance_que_da_mate_nao_e_critico(self) -> None:
        partida = {
            "id": 1,
            "cor_jogada": "PRETAS",
            "pgn": "1. f3 e5 2. g4 Qh4#",
        }
        engine = FakeEngine()

        result = processar_partida(partida, engine)

        self.assertNotIn(
            "Qh4#", [critical_move.notation for critical_move in result.critical_moves]
        )
        self.assertEqual(engine.evaluation_calls, 3)


class DetectarErosaoTest(unittest.TestCase):
    def _lance(
        self, numero: int, win_percent_before: float, win_percent_after: float
    ) -> PlayerMoveEval:
        return PlayerMoveEval(
            move_number=numero,
            notation="m",
            evaluation_before_cp=0,
            evaluation_after_cp=0,
            win_percent_before=win_percent_before,
            win_percent_after=win_percent_after,
        )

    def test_queda_gradual_sem_pico_e_detectada(self) -> None:
        # 8 lances perdendo ~2,5 pontos cada, 20 pontos líquidos no total.
        player_moves = [
            self._lance(i + 1, 80.0 - 2.5 * i, 80.0 - 2.5 * (i + 1))
            for i in range(8)
        ]

        eventos = detectar_erosao(player_moves, set(), 8, 15.0)

        self.assertEqual(len(eventos), 1)
        evento = eventos[0]
        self.assertEqual(evento.tipo_evento, "EROSAO")
        self.assertEqual(evento.move_number, 1)
        self.assertEqual(evento.move_number_fim, 8)
        self.assertIsNone(evento.notation)
        self.assertAlmostEqual(evento.win_percent_drop, 20.0, places=2)

    def test_sequencia_estavel_nao_gera_evento(self) -> None:
        player_moves = [self._lance(i + 1, 50.0, 50.0) for i in range(8)]

        eventos = detectar_erosao(player_moves, set(), 8, 15.0)

        self.assertEqual(eventos, [])

    def test_duas_quedas_nao_sobrepostas_sao_ambas_detectadas(self) -> None:
        # Partida longa (50 lances) com duas quedas graduais de 20 pontos
        # cada, separadas por um trecho estável, sem sobreposição entre elas.
        checkpoints = [80.0 - 2.5 * i for i in range(9)]  # lances 1-8: 80 -> 60
        checkpoints += [60.0] * 21  # lances 9-29: estável em 60
        checkpoints += [60.0 - 2.5 * i for i in range(1, 9)]  # lances 30-37: 60 -> 40
        checkpoints += [40.0] * 13  # lances 38-50: estável em 40

        player_moves = [
            self._lance(numero, checkpoints[numero - 1], checkpoints[numero])
            for numero in range(1, 51)
        ]

        eventos = detectar_erosao(player_moves, set(), 8, 15.0)

        self.assertEqual(len(eventos), 2)
        self.assertEqual((eventos[0].move_number, eventos[0].move_number_fim), (1, 8))
        self.assertEqual((eventos[1].move_number, eventos[1].move_number_fim), (30, 37))
        self.assertAlmostEqual(eventos[0].win_percent_drop, 20.0, places=2)
        self.assertAlmostEqual(eventos[1].win_percent_drop, 20.0, places=2)


# ---------------------------------------------------------------------------
# Testes: processar_partida_com_timeout — contexto de multiprocessing
# ---------------------------------------------------------------------------

def _fake_analysis_settings() -> AnalysisSettings:
    return AnalysisSettings(
        supabase_url="http://localhost",
        supabase_service_role_key="fake-key",
        stockfish_path="/caminho/stockfish/inexistente",
        stockfish_depth=10,
    )


class ProcessarPartidaComTimeoutContextoTest(unittest.TestCase):
    """Regressão: Queue e Process devem vir do MESMO contexto multiprocessing.

    Bug original: `multiprocessing.Queue()` (contexto default - "fork" no
    Linux) era combinado com `multiprocessing.get_context("spawn").Process(...)`,
    causando "SemLock created in a fork context is being shared with a
    process in a spawn context" quando chamado de dentro do processo do
    Uvicorn/FastAPI (via BackgroundTasks, através de analisar_pgn_avulso.py).
    No Windows isso não reproduz (o contexto default já é "spawn"), então
    este teste verifica o requisito de forma direta e independente de SO:
    Queue e Process precisam ser construídos a partir do mesmo objeto de
    contexto explícito.
    """

    def test_queue_e_process_compartilham_o_mesmo_contexto_explicito(self):
        fake_ctx = MagicMock()
        fake_process = MagicMock()
        fake_process.is_alive.return_value = False
        fake_queue = MagicMock()
        fake_queue.get.side_effect = [
            {"kind": "ready"},
            {"kind": "result", "value": "resultado-fake"},
        ]
        fake_ctx.Queue.return_value = fake_queue
        fake_ctx.Process.return_value = fake_process

        with patch(
            "backend.analise_engine.analisar_partidas.multiprocessing.get_context",
            return_value=fake_ctx,
        ) as mock_get_context:
            resultado = processar_partida_com_timeout(
                {"id": "p1"},
                _fake_analysis_settings(),
                init_timeout_seconds=5,
                partida_timeout_seconds=5,
            )

        # get_context("spawn") chamado uma única vez e reaproveitado - se o
        # código voltar a usar multiprocessing.Queue() bare, fake_ctx.Queue
        # nunca é chamado e esta asserção falha.
        mock_get_context.assert_called_once_with("spawn")
        fake_ctx.Queue.assert_called_once_with()
        fake_ctx.Process.assert_called_once()
        self.assertEqual(resultado, "resultado-fake")

    def test_pipeline_real_funciona_com_event_loop_asyncio_ja_rodando(self):
        """Reproduz o cenário de deploy que quebrava: dispara o Process/Queue
        REAIS (contexto "spawn") enquanto um app FastAPI já mantém um event
        loop assíncrono rodando em background - o mesmo arranjo que o Uvicorn
        usa ao processar uma BackgroundTask. Usa um caminho de Stockfish
        inexistente para falhar rápido no processo filho sem precisar de um
        binário real; o que importa aqui é que a falha chega como um
        RuntimeError de negócio controlado, e não como um erro de
        multiprocessing (SemLock/contexto) nem como um travamento.
        """

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.get("/ping")
        def ping() -> dict[str, bool]:
            return {"ok": True}

        partida = {
            "id": "regressao-semlock",
            "cor_jogada": "BRANCAS",
            "pgn": "1. e4 e5 2. Nf3 Nc6",
        }

        with TestClient(app) as client:
            # Garante que o event loop assíncrono do TestClient já está de pé
            # (rodando em background) antes de disparar o multiprocessing.
            self.assertEqual(client.get("/ping").status_code, 200)

            with self.assertRaises(RuntimeError) as ctx:
                processar_partida_com_timeout(
                    partida,
                    _fake_analysis_settings(),
                    init_timeout_seconds=30,
                    partida_timeout_seconds=30,
                )

        self.assertIn("Falha ao inicializar Stockfish", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()