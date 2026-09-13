"""Testes unitários da revisão avulsa: foco na serialização do engine compartilhado."""

from __future__ import annotations

import logging
import os
import threading
import time
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

import chess

from backend.agentes.revisar_exercicio_avulso import (
    EngineIndisponivelError,
    _acquire_engine_lock,
    _descrever_contexto_sequencia,
    normalizar_lances,
    processar_revisao_avulsa,
    processar_revisao_sequencia,
    resolver_lance_usuario,
    resolver_sequencia_usuario,
    salvar_exercicio,
)
from backend.agentes.revisar_pensamento import CHECKLIST_KEYS, Settings


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
        checklist = ", ".join(f'"{chave}": "INDETERMINADO"' for chave in CHECKLIST_KEYS)
        return _FakeResponse(
            '{"qualidade_raciocinio": "SOLIDO", "feedback_texto": "ok", '
            '"analise_mestre": "Plano solido baseado na linha do motor.", '
            f'"checklist_rotina": {{{checklist}}}}}'
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


class ResolverLanceUsuarioTest(unittest.TestCase):
    # Rei branco em e1 e torre branca em d1, com d2 livre e não atacada: 'Rd2'
    # é legal tanto como Rei (leitura PT) quanto como Torre (leitura EN).
    FEN_R_AMBIGUO = "7k/8/8/8/8/8/8/3RK3 w - - 0 1"
    # Mesma torre, mas o rei em h1 não alcança d2: só a leitura EN é legal.
    FEN_R_SO_TORRE = "7k/8/8/8/8/8/8/3R3K w - - 0 1"

    def test_lance_em_portugues_e_interpretado_como_pt(self) -> None:
        board = chess.Board()
        board.push_san("e4")
        board.push_san("e5")

        resolvido = resolver_lance_usuario(board, "Cf3")

        self.assertEqual(resolvido.interpretacao, "PT")
        self.assertEqual(resolvido.san, "Nf3")
        self.assertEqual(resolvido.lance_interpretado, "Cf3")

    def test_lance_de_peao_funciona_sem_traducao(self) -> None:
        resolvido = resolver_lance_usuario(chess.Board(), "e4")

        self.assertEqual(resolvido.san, "e4")
        self.assertEqual(resolvido.lance_interpretado, "e4")

    def test_fallback_para_ingles_quando_portugues_e_ilegal(self) -> None:
        # 'Rd2' lido como português vira 'Kd2' (Rei), ilegal nesta posição;
        # o fallback tenta o texto original e acha a torre d1-d2.
        board = chess.Board(self.FEN_R_SO_TORRE)

        resolvido = resolver_lance_usuario(board, "Rd2")

        self.assertEqual(resolvido.interpretacao, "EN")
        self.assertEqual(resolvido.san, "Rd2")
        self.assertEqual(resolvido.lance_interpretado, "Td2")

    def test_fallback_para_ingles_com_letra_de_cavalo(self) -> None:
        board = chess.Board()

        # 'Nf3' traduzido de PT continua 'Nf3' (N não é letra de peça em PT),
        # então segue funcionando para quem digita em inglês.
        resolvido = resolver_lance_usuario(board, "Nf3")

        self.assertEqual(resolvido.san, "Nf3")
        self.assertEqual(resolvido.lance_interpretado, "Cf3")

    def test_ambiguidade_rei_x_torre_prioriza_portugues(self) -> None:
        board = chess.Board(self.FEN_R_AMBIGUO)
        # Pré-condição do caso construído: as duas leituras são legais aqui.
        self.assertIsNotNone(board.parse_san("Kd2"))
        self.assertIsNotNone(board.parse_san("Rd2"))

        resolvido = resolver_lance_usuario(board, "Rd2")

        self.assertEqual(resolvido.interpretacao, "PT")
        self.assertEqual(resolvido.san, "Kd2", "esperava o lance de REI (leitura PT)")
        self.assertEqual(resolvido.lance_interpretado, "Rd2")

    def test_promocao_em_portugues(self) -> None:
        board = chess.Board("8/4P2k/8/8/8/8/8/4K3 w - - 0 1")

        resolvido = resolver_lance_usuario(board, "e8=D")

        self.assertEqual(resolvido.san, "e8=Q")
        self.assertEqual(resolvido.lance_interpretado, "e8=D")

    def test_lance_invalido_nos_dois_idiomas_propaga_erro(self) -> None:
        with self.assertRaises(ValueError) as contexto:
            resolver_lance_usuario(chess.Board(), "Zz9")

        # O erro propagado é o do texto ORIGINAL, para o usuário reconhecer
        # o que digitou (e não a versão traduzida internamente).
        self.assertIn("Zz9", str(contexto.exception))

    def test_lance_ilegal_reporta_o_texto_digitado(self) -> None:
        with self.assertRaises(ValueError) as contexto:
            resolver_lance_usuario(chess.Board(), "Cd5")

        self.assertIn("Cd5", str(contexto.exception))


class ResolverSequenciaUsuarioTest(unittest.TestCase):
    def test_resolve_linha_em_portugues_sem_alterar_o_tabuleiro(self) -> None:
        board = chess.Board()

        resolvidos = resolver_sequencia_usuario(board, ["e4", "e5", "Cf3"])

        self.assertEqual([item.san for item in resolvidos], ["e4", "e5", "Nf3"])
        self.assertEqual(
            [item.lance_interpretado for item in resolvidos], ["e4", "e5", "Cf3"]
        )
        self.assertEqual(board.fen(), chess.Board().fen())

    def test_erro_menciona_a_posicao_na_sequencia(self) -> None:
        with self.assertRaises(ValueError) as contexto:
            resolver_sequencia_usuario(chess.Board(), ["e4", "e5", "Zz9"])

        self.assertIn("posição 3", str(contexto.exception))


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

    def test_aceita_notacao_em_portugues_e_devolve_interpretacao(self) -> None:
        resultado = processar_revisao_sequencia(
            _FakeEngineSequencia(),
            _FakeGeminiClient(),
            _fake_settings(),
            _fake_logger(),
            chess.Board().fen(),
            ["e4", "e5", "Cf3"],
            "Abro o centro e desenvolvo o cavalo.",
        )

        # Internamente tudo vira SAN em inglês...
        self.assertEqual(resultado["lances"], ["e4", "e5", "Nf3"])
        self.assertEqual(resultado["avaliacoes"][1]["lance_jogado"], "Nf3")
        # ...mas a interpretação devolvida ao usuário fica em português.
        self.assertEqual(resultado["avaliacoes"][1]["lance_interpretado"], "Cf3")
        self.assertEqual(resultado["lance_interpretado"], "e4")

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


class SalvarExercicioTest(unittest.TestCase):
    """salvar_exercicio precisa devolver o id da linha criada (usado pelo
    frontend para marcar o exercício salvo como "ativo" no histórico)."""

    USER_ID_TESTE = "11111111-2222-3333-4444-555555555555"

    def setUp(self) -> None:
        # revisao_exercicio_avulso é tabela raiz: user_id é NOT NULL (D-14).
        self._env = patch.dict(
            os.environ, {"DEFAULT_USER_ID": self.USER_ID_TESTE}
        )
        self._env.start()
        self.addCleanup(self._env.stop)

    def test_grava_o_user_id_do_ambiente_no_payload(self) -> None:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"id": "exercicio-novo-789"}]
        client.table.return_value.insert.return_value.execute.return_value = resp

        salvar_exercicio(
            client,
            chess.Board().fen(),
            "Abro o centro.",
            {
                "lance_jogado": "e4",
                "melhor_lance": "e4",
                "queda_win_percent": 0.0,
                "qualidade_lance": "BOM",
                "qualidade_raciocinio": "SOLIDO",
                "feedback_texto": "ok",
            },
        )

        payload = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(payload["user_id"], self.USER_ID_TESTE)

    def test_user_id_explicito_sobrepoe_o_default_do_ambiente(self) -> None:
        # Fase B.2 (D-17): dono real da sessão, resolvido em api_server.py,
        # sobrepõe o fallback DEFAULT_USER_ID.
        user_id_sessao = "99999999-8888-7777-6666-555555555555"
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"id": "exercicio-novo-999"}]
        client.table.return_value.insert.return_value.execute.return_value = resp

        salvar_exercicio(
            client,
            chess.Board().fen(),
            "Abro o centro.",
            {
                "lance_jogado": "e4",
                "melhor_lance": "e4",
                "queda_win_percent": 0.0,
                "qualidade_lance": "BOM",
                "qualidade_raciocinio": "SOLIDO",
                "feedback_texto": "ok",
            },
            user_id=user_id_sessao,
        )

        payload = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(payload["user_id"], user_id_sessao)

    def test_retorna_o_id_da_linha_criada(self) -> None:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"id": "exercicio-novo-789"}]
        client.table.return_value.insert.return_value.execute.return_value = resp

        novo_id = salvar_exercicio(
            client,
            chess.Board().fen(),
            "Abro o centro.",
            {
                "lance_jogado": "e4",
                "melhor_lance": "e4",
                "queda_win_percent": 0.0,
                "qualidade_lance": "BOM",
                "qualidade_raciocinio": "SOLIDO",
                "feedback_texto": "ok",
            },
        )

        self.assertEqual(novo_id, "exercicio-novo-789")
        client.table.assert_called_once_with("revisao_exercicio_avulso")

    def test_retorna_none_se_resposta_nao_trouxer_dados(self) -> None:
        client = MagicMock()
        resp = MagicMock()
        resp.data = []
        client.table.return_value.insert.return_value.execute.return_value = resp

        novo_id = salvar_exercicio(
            client,
            chess.Board().fen(),
            "x",
            {
                "lance_jogado": "e4",
                "melhor_lance": "e4",
                "queda_win_percent": 0.0,
                "qualidade_lance": "BOM",
                "qualidade_raciocinio": "SOLIDO",
                "feedback_texto": "ok",
            },
        )

        self.assertIsNone(novo_id)


if __name__ == "__main__":
    unittest.main()
