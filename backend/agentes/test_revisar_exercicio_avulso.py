"""Testes unitários da revisão avulsa: foco na serialização do engine compartilhado."""

from __future__ import annotations

import logging
import threading
import time
import unittest
from typing import Any

import chess

from backend.agentes.revisar_exercicio_avulso import (
    EngineIndisponivelError,
    _acquire_engine_lock,
    _descrever_contexto_sequencia,
    normalizar_lances,
    processar_revisao_avulsa,
    processar_revisao_sequencia,
)
from backend.agentes.revisar_pensamento import Settings


class _FakeEngineConcorrente:
    """Fake do Stockfish: expõe os mesmos métodos usados pela pipeline e acusa
    corrupção se duas chamadas se sobrepõem (via um sleep interno simulando o
    tempo real gasto pelo subprocesso do motor)."""

    def __init__(self, tempo_por_chamada: float = 0.05) -> None:
        self._em_uso = False
        self._tempo_por_chamada = tempo_por_chamada
        self.corrompeu = False
        self.chamadas = 0

    def _tocar(self) -> None:
        if self._em_uso:
            self.corrompeu = True
        self._em_uso = True
        self.chamadas += 1
        time.sleep(self._tempo_por_chamada)
        self._em_uso = False

    def set_fen_position(self, fen: str) -> None:
        self._tocar()

    def get_evaluation(self, searchtime: int | None = None) -> dict[str, Any]:
        self._tocar()
        return {"type": "cp", "value": 20}

    def get_best_move_time(self, time_ms: int) -> str:
        self._tocar()
        return "e2e4"

    def get_top_moves(self, n: int, verbose: bool = False) -> list[dict[str, Any]]:
        self._tocar()
        # PV vazia de propósito: evita disparar a validação/retry de
        # analise_mestre, que é irrelevante para este teste de concorrência.
        return [{"PVMoves": ""}]


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def generate_content(self, model: str, contents: str) -> _FakeResponse:
        return _FakeResponse(
            '{"qualidade_raciocinio": "SOLIDO", "feedback_texto": "ok", '
            '"analise_mestre": "Plano solido baseado na linha do motor."}'
        )


class _FakeGeminiClient:
    def __init__(self) -> None:
        self.models = _FakeModels()


def _fake_settings() -> Settings:
    return Settings(
        supabase_url="https://example.test",
        supabase_service_role_key="chave",
        stockfish_path="/usr/games/stockfish",
        stockfish_depth=16,
        gemini_api_key="chave-gemini",
        limiar_lance_bom=5.0,
        limiar_lance_ruim=15.0,
    )


def _fake_logger() -> logging.Logger:
    logger = logging.getLogger("test_revisar_exercicio_avulso")
    logger.addHandler(logging.NullHandler())
    return logger


def _rodar_processar_revisao(
    engine: Any,
    resultados: list[dict[str, Any]],
    erros: list[Exception],
    engine_lock: threading.Lock | None,
) -> None:
    try:
        resultado = processar_revisao_avulsa(
            engine,
            _FakeGeminiClient(),
            _fake_settings(),
            _fake_logger(),
            chess.Board().fen(),
            "e4",
            "teste de concorrência",
            engine_lock,
        )
        resultados.append(resultado)
    except Exception as error:  # noqa: BLE001 - captura para asserção no teste
        erros.append(error)


class EngineLockConcorrenciaTest(unittest.TestCase):
    def test_lock_serializa_chamadas_concorrentes_sem_corromper_engine(self) -> None:
        engine = _FakeEngineConcorrente()
        engine_lock = threading.Lock()
        resultados: list[dict[str, Any]] = []
        erros: list[Exception] = []

        threads = [
            threading.Thread(
                target=_rodar_processar_revisao,
                args=(engine, resultados, erros, engine_lock),
            )
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(erros, [])
        self.assertEqual(len(resultados), 2)
        self.assertFalse(
            engine.corrompeu,
            "o engine detectou uso concorrente mesmo com o lock (segunda "
            "chamada deveria esperar a primeira terminar).",
        )

    def test_sem_lock_chamadas_concorrentes_corrompem_engine(self) -> None:
        # Reproduz o bug original: sem engine_lock, as duas threads se
        # sobrepõem no mesmo engine compartilhado.
        engine = _FakeEngineConcorrente()
        resultados: list[dict[str, Any]] = []
        erros: list[Exception] = []

        threads = [
            threading.Thread(
                target=_rodar_processar_revisao,
                args=(engine, resultados, erros, None),
            )
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertTrue(
            engine.corrompeu,
            "esperava reproduzir a corrupção por acesso concorrente sem lock.",
        )


class AcquireEngineLockTimeoutTest(unittest.TestCase):
    def test_timeout_gera_engine_indisponivel_error(self) -> None:
        lock = threading.Lock()
        lock.acquire()  # simula outra requisição já segurando o lock
        try:
            with self.assertRaises(EngineIndisponivelError):
                with _acquire_engine_lock(lock, timeout_seconds=0.1):
                    pass
        finally:
            lock.release()

    def test_sem_lock_e_no_op(self) -> None:
        executou = False
        with _acquire_engine_lock(None):
            executou = True
        self.assertTrue(executou)


class _FakeEngineSequencia:
    """Fake mínimo do Stockfish para os testes de sequência (sem concorrência)."""

    def set_fen_position(self, fen: str) -> None:
        pass

    def get_evaluation(self, searchtime: int | None = None) -> dict[str, Any]:
        return {"type": "cp", "value": 20}

    def get_best_move_time(self, time_ms: int) -> str:
        return "e2e4"

    def get_top_moves(self, n: int, verbose: bool = False) -> list[dict[str, Any]]:
        return []


class NormalizarLancesTest(unittest.TestCase):
    def test_lista_direta(self) -> None:
        self.assertEqual(normalizar_lances(["Nd5", "Qc6"], None), ["Nd5", "Qc6"])

    def test_lance_unico_compat(self) -> None:
        self.assertEqual(normalizar_lances(None, "e4"), ["e4"])

    def test_divide_por_virgula_e_espaco(self) -> None:
        self.assertEqual(
            normalizar_lances(None, "Nd5, Qc6 Bxe6"), ["Nd5", "Qc6", "Bxe6"]
        )

    def test_lista_com_prioridade_sobre_lance(self) -> None:
        self.assertEqual(normalizar_lances(["Nd5"], "e4"), ["Nd5"])

    def test_vazio_levanta_erro(self) -> None:
        with self.assertRaises(ValueError):
            normalizar_lances(None, None)


class DescreverContextoSequenciaTest(unittest.TestCase):
    def test_primeiro_lance_do_jogador(self) -> None:
        contexto = _descrever_contexto_sequencia(["Nd5", "Qc6", "Bxe6"], 0, 1)
        self.assertIn("1º lance do jogador", contexto)
        self.assertIn("Nd5", contexto)

    def test_lance_posterior_menciona_resposta_do_adversario(self) -> None:
        contexto = _descrever_contexto_sequencia(["Nd5", "Qc6", "Bxe6"], 2, 2)
        self.assertIn("APÓS a resposta do adversário", contexto)
        self.assertIn("Qc6", contexto)
        self.assertIn("Bxe6", contexto)


class ProcessarRevisaoSequenciaTest(unittest.TestCase):
    def test_avalia_apenas_lances_do_jogador(self) -> None:
        resultado = processar_revisao_sequencia(
            _FakeEngineSequencia(),
            _FakeGeminiClient(),
            _fake_settings(),
            _fake_logger(),
            chess.Board().fen(),
            ["e4", "e5", "Nf3"],
            "Quero abrir o centro e desenvolver.",
        )

        # e4 (índice 0) e Nf3 (índice 2) são do jogador; e5 só avança a posição.
        self.assertEqual(len(resultado["avaliacoes"]), 2)
        self.assertEqual(resultado["avaliacoes"][0]["lance_jogado"], "e4")
        self.assertEqual(resultado["avaliacoes"][0]["indice_na_sequencia"], 1)
        self.assertEqual(resultado["avaliacoes"][1]["lance_jogado"], "Nf3")
        self.assertEqual(resultado["avaliacoes"][1]["indice_na_sequencia"], 3)
        self.assertEqual(resultado["lances"], ["e4", "e5", "Nf3"])
        # 2 lances do jogador → resumo geral é gerado.
        self.assertIsNotNone(resultado["resumo_geral"])

    def test_lance_unico_gera_uma_avaliacao_sem_resumo(self) -> None:
        resultado = processar_revisao_sequencia(
            _FakeEngineSequencia(),
            _FakeGeminiClient(),
            _fake_settings(),
            _fake_logger(),
            chess.Board().fen(),
            ["e4"],
            "Abro no centro.",
        )

        self.assertEqual(len(resultado["avaliacoes"]), 1)
        self.assertIsNone(resultado["resumo_geral"])

    def test_lance_ilegal_na_sequencia_levanta_erro(self) -> None:
        with self.assertRaises(ValueError):
            processar_revisao_sequencia(
                _FakeEngineSequencia(),
                _FakeGeminiClient(),
                _fake_settings(),
                _fake_logger(),
                chess.Board().fen(),
                ["e4", "e5", "Zz9"],
                "x",
            )


if __name__ == "__main__":
    unittest.main()
