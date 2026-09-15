"""Testes unitários da análise de partidas."""

import unittest
from unittest.mock import MagicMock, patch

import chess
from backend.analise_engine.analisar_partidas import (
    AnalysisSettings,
    CriticalMove,
    PlayerMoveEval,
    ProcessResult,
    detectar_erosao,
    evaluate_position,
    fetch_lances_anotados_partida,
    insert_critical_moves,
    limpar_registros_derivados_partida,
    parse_args,
    processar_partida,
    processar_partida_com_timeout,
    promover_lances_anotados,
    recuperar_partidas_com_falha,
    recuperar_partidas_orfas,
    resetar_partida_para_pendente,
    selecionar_picos,
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


class SelecionarPicosTest(unittest.TestCase):
    def test_pico_carrega_fen_de_antes_do_lance(self) -> None:
        player_moves = [
            PlayerMoveEval(
                move_number=5,
                notation="Qxd5",
                evaluation_before_cp=50,
                evaluation_after_cp=-200,
                win_percent_before=55.0,
                win_percent_after=25.0,
                fen_antes="fen-antes-do-erro",
            )
        ]

        picos = selecionar_picos(player_moves)

        self.assertEqual(len(picos), 1)
        self.assertEqual(picos[0].fen_antes_lance, "fen-antes-do-erro")


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
            fen_antes=f"fen-lance-{numero}",
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
        # D-27: a janela guarda o FEN de ANTES do lance inicial, não do final.
        self.assertEqual(evento.fen_antes_lance, "fen-lance-1")

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


class EvaluatePositionTest(unittest.TestCase):
    def test_searchtime_zero_chama_sem_argumentos(self) -> None:
        engine = MagicMock()
        engine.get_evaluation.return_value = {"type": "cp", "value": 50}
        board = chess.Board()

        score = evaluate_position(engine, board, "BRANCAS", searchtime_ms=0)

        engine.get_evaluation.assert_called_once_with()
        self.assertEqual(score, 50)

    def test_searchtime_positivo_passa_searchtime(self) -> None:
        engine = MagicMock()
        engine.get_evaluation.return_value = {"type": "cp", "value": 50}
        board = chess.Board()

        score = evaluate_position(engine, board, "BRANCAS", searchtime_ms=1500)

        engine.get_evaluation.assert_called_once_with(searchtime=1500)
        self.assertEqual(score, 50)


class LimpezaRegistrosDerivadosTest(unittest.TestCase):
    def test_limpar_registros_deleta_em_ordem_respeitando_fk(self) -> None:
        client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [{"id": "lance-1"}, {"id": "lance-2"}]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp

        limpar_registros_derivados_partida(client, "partida-1")

        tables_called = [call.args[0] for call in client.table.call_args_list]
        self.assertIn("resumo_partida", tables_called)
        self.assertIn("lances_criticos", tables_called)
        self.assertIn("perguntas_pendentes", tables_called)
        self.assertIn("diagnosticos", tables_called)

    def test_limpar_registros_sem_lances_criticos_nao_deleta_filhos(self) -> None:
        client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = []
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp

        limpar_registros_derivados_partida(client, "partida-1")

        tables_called = [call.args[0] for call in client.table.call_args_list]
        self.assertIn("resumo_partida", tables_called)
        self.assertIn("lances_criticos", tables_called)
        self.assertNotIn("perguntas_pendentes", tables_called)
        self.assertNotIn("diagnosticos", tables_called)

    def test_resetar_partida_para_pendente_limpa_e_atualiza(self) -> None:
        client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = []
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp

        resetar_partida_para_pendente(client, "partida-1")

        client.table("partidas").update.assert_called_with({"status_processamento": "pendente"})


class RecuperacaoPartidasTest(unittest.TestCase):
    def test_recuperar_partidas_orfas(self) -> None:
        client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [
            {"id": "p1", "external_id": "ext1"},
            {"id": "p2", "external_id": "ext2"},
        ]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp
        logger = MagicMock()

        count = recuperar_partidas_orfas(client, logger)

        self.assertEqual(count, 2)
        client.table("partidas").update.assert_called_with({"status_processamento": "pendente"})

    def test_recuperar_partidas_com_falha(self) -> None:
        client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [
            {"id": "p1", "external_id": "ext1"},
        ]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp
        logger = MagicMock()

        count = recuperar_partidas_com_falha(client, logger)

        self.assertEqual(count, 1)
        client.table("partidas").update.assert_called_with({"status_processamento": "pendente"})


class ParseArgsTest(unittest.TestCase):
    def test_args_default(self) -> None:
        with patch("sys.argv", ["analisar_partidas.py"]):
            args = parse_args()
            self.assertFalse(args.reprocessar_falhas)
            self.assertIsNone(args.partida_id)

    def test_args_reprocessar_falhas(self) -> None:
        with patch("sys.argv", ["analisar_partidas.py", "--reprocessar-falhas"]):
            args = parse_args()
            self.assertTrue(args.reprocessar_falhas)

    def test_args_partida_id(self) -> None:
        with patch("sys.argv", ["analisar_partidas.py", "--partida-id", "uuid-123"]):
            args = parse_args()
            self.assertEqual(args.partida_id, "uuid-123")


class PromoverLancesAnotadosTest(unittest.TestCase):
    def test_sem_lances_anotados_retorna_inalterado(self) -> None:
        moves = [
            PlayerMoveEval(10, "Nf3", 0, 0, 50.0, 50.0, "fen1"),
        ]
        criticos = [
            CriticalMove(10, "Nf3", 0, 0, 0.0, "PICO", "fen1", origem="GRAVIDADE"),
        ]
        res = promover_lances_anotados(moves, criticos, set())
        self.assertEqual(res, criticos)

    def test_promove_lance_anotado_inexistente_nos_criticos(self) -> None:
        moves = [
            PlayerMoveEval(10, "Nf3", 0, 0, 50.0, 50.0, "fen1"),
            PlayerMoveEval(15, "d4", 10, -50, 50.0, 42.0, "fen2"),
        ]
        criticos = [
            CriticalMove(10, "Nf3", 0, 0, 0.0, "PICO", "fen1", origem="GRAVIDADE"),
        ]
        res = promover_lances_anotados(moves, criticos, {15})
        self.assertEqual(len(res), 2)
        lance15 = next(m for m in res if m.move_number == 15)
        self.assertEqual(lance15.origem, "ANOTACAO")
        self.assertEqual(lance15.notation, "d4")
        self.assertEqual(lance15.win_percent_drop, 8.0)

    def test_nao_duplica_lance_ja_presente(self) -> None:
        moves = [
            PlayerMoveEval(10, "Nf3", 0, 0, 50.0, 50.0, "fen1"),
        ]
        criticos = [
            CriticalMove(10, "Nf3", 0, 0, 0.0, "PICO", "fen1", origem="GRAVIDADE"),
        ]
        res = promover_lances_anotados(moves, criticos, {10})
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].origem, "GRAVIDADE")


class FetchLancesAnotadosPartidaTest(unittest.TestCase):
    def test_fetch_lances_anotados_sucesso(self) -> None:
        client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [{"numero_lance": 12}, {"numero_lance": 25}]
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_resp

        resultado = fetch_lances_anotados_partida(client, "partida-123")
        self.assertEqual(resultado, {12, 25})

    def test_fetch_lances_anotados_erro_retorna_vazio(self) -> None:
        client = MagicMock()
        client.table.side_effect = Exception("DB error")

        resultado = fetch_lances_anotados_partida(client, "partida-123")
        self.assertEqual(resultado, set())


class InsertCriticalMovesTest(unittest.TestCase):
    def test_insert_critical_moves_com_origem(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        move = CriticalMove(
            move_number=12,
            notation="e4",
            evaluation_before_cp=10,
            evaluation_after_cp=-20,
            win_percent_drop=5.0,
            tipo_evento="PICO",
            fen_antes_lance="fen",
            origem="ANOTACAO",
        )
        res = ProcessResult(partida_id="p1", critical_moves=[move])
        count = insert_critical_moves(client, res)
        self.assertEqual(count, 1)

        insert_calls = client.table("lances_criticos").insert.call_args_list
        self.assertTrue(len(insert_calls) >= 1)
        payload = insert_calls[-1][0][0]
        self.assertEqual(payload.get("origem"), "ANOTACAO")

    def test_insert_critical_moves_fallback_sem_coluna_origem(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        insert_mock = MagicMock()
        insert_mock.execute.side_effect = [Exception("column origem does not exist"), MagicMock()]
        client.table("lances_criticos").insert.return_value = insert_mock

        move = CriticalMove(
            move_number=12,
            notation="e4",
            evaluation_before_cp=10,
            evaluation_after_cp=-20,
            win_percent_drop=5.0,
            tipo_evento="PICO",
            fen_antes_lance="fen",
            origem="ANOTACAO",
        )
        res = ProcessResult(partida_id="p1", critical_moves=[move])
        count = insert_critical_moves(client, res)
        self.assertEqual(count, 1)

        self.assertEqual(client.table("lances_criticos").insert.call_count, 2)
        fallback_payload = client.table("lances_criticos").insert.call_args_list[1][0][0]
        self.assertNotIn("origem", fallback_payload)


if __name__ == "__main__":
    unittest.main()