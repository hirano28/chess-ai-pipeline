"""Testes unitários do módulo explicador_posicao.py.

Cobre:
- Normalização de lado (válidos, inválidos, maiúsculas/minúsculas, nulo).
- Inspeção posicional via python-chess (material, peças indefesas, cravadas, segurança do rei, ameaças).
- Avaliação com engine (score centipawns, mate, win%, PV em SAN, refutação da melhor defesa).
- Montagem do prompt do Gemini e regras anti-alucinação.
- Fallback determinístico caso o Gemini esteja indisponível.
- Geração da explicação com Gemini com validação de schema e retry anti-alucinação.
- Pipeline completa de explicar_posicao com FEN e PGN.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

import chess

from backend.agentes.explicador_posicao import (
    ExplicacaoPosicao,
    analisar_posicao_com_engine,
    build_prompt_explicador,
    detectar_lances_inventados,
    explicar_posicao,
    fallback_explicacao_posicao,
    gerar_explicacao_gemini,
    inspecionar_elementos_tabuleiro,
    normalizar_lado,
    obter_lances_permitidos,
    salvar_explicacao_posicao,
)
from backend.agentes.revisar_pensamento import Settings


def _fake_settings() -> Settings:
    return Settings(
        supabase_url="https://example.test",
        supabase_service_role_key="chave-servico",
        stockfish_path="/usr/games/stockfish",
        stockfish_depth=16,
        gemini_api_key="chave-gemini",
        limiar_lance_bom=5.0,
        limiar_lance_ruim=15.0,
    )


def _fake_logger() -> logging.Logger:
    logger = logging.getLogger("test_explicador_posicao")
    logger.addHandler(logging.NullHandler())
    return logger


class _FakeEngine:
    def __init__(
        self,
        eval_dict: dict[str, Any] | None = None,
        top_moves: list[dict[str, Any]] | None = None,
    ) -> None:
        self.eval_dict = eval_dict or {"type": "cp", "value": 350}
        self.top_moves = top_moves if top_moves is not None else [
            {"PVMoves": "d2d4 d7d5 c2c4", "Move": "d2d4", "Centipawn": 350}
        ]
        self.last_fen: str | None = None

    def set_fen_position(self, fen: str) -> None:
        self.last_fen = fen

    def get_evaluation(self, searchtime: int | None = None) -> dict[str, Any]:
        return self.eval_dict

    def get_top_moves(self, n: int, verbose: bool = False) -> list[dict[str, Any]]:
        return self.top_moves


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeGeminiClient:
    def __init__(self, respostas: list[str] | str | None = None) -> None:
        if respostas is None:
            respostas = [
                json.dumps(
                    {
                        "veredito": "As Brancas possuem vantagem decisiva (+3.50).",
                        "ameaca_concreta": "Ameaça direta d4 abrindo linhas no centro.",
                        "o_que_parece_bom_mas_falha": "O lance d5 falha após c4.",
                        "plano_conversao": "Avançar peões centrais e ativar peças.",
                        "resumo_didatico": "Domínio central consolidado sem contra-jogo.",
                    }
                )
            ]
        elif isinstance(respostas, str):
            respostas = [respostas]
        self.respostas = list(respostas)
        self.chamadas = 0

        class _Models:
            def __init__(self, outer: _FakeGeminiClient) -> None:
                self.outer = outer

            def generate_content(self, model: str, contents: str) -> _FakeResponse:
                idx = min(self.outer.chamadas, len(self.outer.respostas) - 1)
                self.outer.chamadas += 1
                return _FakeResponse(self.outer.respostas[idx])

        self.models = _Models(self)


class NormalizarLadoTest(unittest.TestCase):
    def test_lado_none_ou_vazio_retorna_none(self) -> None:
        self.assertIsNone(normalizar_lado(None))
        self.assertIsNone(normalizar_lado(""))
        self.assertIsNone(normalizar_lado("   "))

    def test_brancas_normaliza_corretamente(self) -> None:
        for entrada in ["brancas", "BRANCAS", "branca", "white", "WHITE", "w", "W"]:
            self.assertEqual(normalizar_lado(entrada), "BRANCAS")

    def test_pretas_normaliza_corretamente(self) -> None:
        for entrada in ["pretas", "PRETAS", "preta", "black", "BLACK", "negras", "p", "P"]:
            self.assertEqual(normalizar_lado(entrada), "PRETAS")

    def test_modo_automatico_ou_todos_normaliza_como_none(self) -> None:
        for entrada in ["todos", "TODOS", "ambos", "AMBOS", "auto", "AUTO", "automatico", "all"]:
            self.assertIsNone(normalizar_lado(entrada))

    def test_lado_invalido_levanta_value_error(self) -> None:
        with self.assertRaises(ValueError):
            normalizar_lado("azul")
        with self.assertRaises(ValueError):
            normalizar_lado("amarelas")


class InspecionarElementosTabuleiroTest(unittest.TestCase):
    def test_posicao_inicial(self) -> None:
        board = chess.Board()
        elementos = inspecionar_elementos_tabuleiro(board)

        self.assertEqual(elementos["material"]["pontos_brancas"], 39)
        self.assertEqual(elementos["material"]["pontos_pretas"], 39)
        self.assertEqual(elementos["material"]["saldo_brancas"], 0)
        self.assertTrue(elementos["material"]["par_bispos_brancas"])
        self.assertTrue(elementos["material"]["par_bispos_pretas"])

        # Na posição inicial, nenhum rei está em xeque e ambos têm roque disponível
        self.assertFalse(elementos["seguranca_rei"]["BRANCAS"]["em_xeque"])
        self.assertTrue(elementos["seguranca_rei"]["BRANCAS"]["roque_disponivel"])
        self.assertFalse(elementos["seguranca_rei"]["PRETAS"]["em_xeque"])
        self.assertTrue(elementos["seguranca_rei"]["PRETAS"]["roque_disponivel"])

    def test_detecta_peca_cravada(self) -> None:
        # FEN onde o cavalo preto em c6 está cravado pelo bispo em b5 ao rei em e8:
        # 1. e4 e5 2. Nf3 Nc6 3. Bb5 d6 (peão em d6 desobstrui a diagonal b5-c6-d7-e8)
        fen = "r1bqkbnr/ppp2ppp/2np4/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4"
        board = chess.Board(fen)
        elementos = inspecionar_elementos_tabuleiro(board)

        cravadas_pretas = elementos["pecas_cravadas"]["PRETAS"]
        self.assertTrue(
            any("Cavalo em c6 cravado ao Rei em e8" in item for item in cravadas_pretas),
            f"Esperado cavalo em c6 cravado, recebido: {cravadas_pretas}",
        )

    def test_detecta_peca_indefesa_e_atacada(self) -> None:
        # Bispo em b5 atacado por a6 e sem defensores
        fen = "r1bqkbnr/1ppp1ppp/p1n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4"
        board = chess.Board(fen)
        elementos = inspecionar_elementos_tabuleiro(board)

        indefesas_brancas = elementos["pecas_indefesas"]["BRANCAS"]
        self.assertTrue(
            any("Bispo em b5" in item and "atacado" in item for item in indefesas_brancas),
            f"Esperado bispo em b5 atacado e indefeso, recebido: {indefesas_brancas}",
        )

    def test_detecta_rei_em_xeque(self) -> None:
        # Rei preto em e8 em xeque pelo bispo em b5
        # 1. e4 d5 2. Bb5+
        fen = "rnbqkbnr/ppp1pppp/8/1B1p4/4P3/8/PPPP1PPP/RNBQK1NR b KQkq - 1 2"
        board = chess.Board(fen)
        elementos = inspecionar_elementos_tabuleiro(board)

        self.assertTrue(elementos["seguranca_rei"]["PRETAS"]["em_xeque"])
        self.assertIn("sob xeque", elementos["seguranca_rei"]["PRETAS"]["resumo"])


class AnalisarPosicaoComEngineTest(unittest.TestCase):
    def test_avaliacao_centipawns_vencedor_brancas(self) -> None:
        board = chess.Board()
        engine = _FakeEngine(
            eval_dict={"type": "cp", "value": 250},
            top_moves=[{"PVMoves": "e2e4 e7e5 g1f3", "Move": "e2e4", "Centipawn": 250}],
        )

        resultado = analisar_posicao_com_engine(engine, board)

        self.assertEqual(resultado["score_cp"], 250)
        self.assertIsNone(resultado["mate"])
        self.assertEqual(resultado["lado_vencedor"], "BRANCAS")
        self.assertGreater(resultado["win_percent"], 50.0)
        self.assertEqual(len(resultado["linhas_taticas"]), 1)
        self.assertEqual(resultado["linhas_taticas"][0]["lance"], "e4")
        self.assertEqual(resultado["linhas_taticas"][0]["pv_san"], ["e4", "e5", "Nf3"])

        # Refutação da defesa
        self.assertIsNotNone(resultado["refutacao_defesa"])
        self.assertEqual(resultado["refutacao_defesa"]["defesa"], "e5")

    def test_avaliacao_mate_vencedor_pretas(self) -> None:
        board = chess.Board()
        engine = _FakeEngine(
            eval_dict={"type": "mate", "value": -2},
            top_moves=[{"PVMoves": "d1h5 e8f8", "Move": "d1h5", "Mate": -2}],
        )

        resultado = analisar_posicao_com_engine(engine, board)

        self.assertEqual(resultado["mate"], -2)
        self.assertEqual(resultado["lado_vencedor"], "PRETAS")
        self.assertEqual(resultado["win_percent"], 100.0)
        self.assertEqual(resultado["win_percent_pretas"], 100.0)
        self.assertEqual(resultado["win_percent_brancas"], 0.0)
        self.assertIn("Mate forçado em 2 lance(s) para as Pretas", resultado["descricao"])

    def test_posicao_equilibrada(self) -> None:
        board = chess.Board()
        engine = _FakeEngine(eval_dict={"type": "cp", "value": 15})

        resultado = analisar_posicao_com_engine(engine, board)

        self.assertEqual(resultado["lado_vencedor"], "EQUILIBRADO")
        self.assertIsNone(resultado["refutacao_defesa"])


class PromptEFallbackTest(unittest.TestCase):
    def test_build_prompt_inclui_dados_essenciais(self) -> None:
        board = chess.Board()
        elementos = inspecionar_elementos_tabuleiro(board)
        avaliacao = {
            "score_cp": 300,
            "mate": None,
            "win_percent": 90.0,
            "lado_vencedor": "BRANCAS",
            "descricao": "+3.00 centipawns",
        }
        linhas_taticas = [
            {"lance": "e4", "avaliacao": "+300", "pv_san": ["e4", "e5", "Nf3"]}
        ]
        refutacao = {
            "defesa": "e5",
            "refutacao_linha": ["e4", "e5", "Nf3"],
            "detalhes": "Após e4, e5 é refutado por Nf3.",
        }

        prompt = build_prompt_explicador(
            board.fen(),
            "BRANCAS",
            "BRANCAS",
            avaliacao,
            linhas_taticas,
            refutacao,
            elementos,
        )

        self.assertIn("FEN:", prompt)
        self.assertIn("+3.00 centipawns", prompt)
        self.assertIn("Melhor defesa: e5", prompt)
        self.assertIn("veredito", prompt)
        self.assertIn("ameaca_concreta", prompt)
        self.assertIn("o_que_parece_bom_mas_falha", prompt)
        self.assertIn("plano_conversao", prompt)
        self.assertIn("resumo_didatico", prompt)

    def test_fallback_explicacao_retorna_modelo_completo(self) -> None:
        board = chess.Board()
        elementos = inspecionar_elementos_tabuleiro(board)
        avaliacao = {
            "score_cp": 450,
            "mate": None,
            "win_percent": 95.0,
            "lado_vencedor": "BRANCAS",
            "descricao": "+4.50 centipawns",
        }
        linhas = [{"lance": "e4", "avaliacao": "+450", "pv_san": ["e4"]}]
        refutacao = {
            "defesa": "e5",
            "refutacao_linha": ["e4", "e5"],
            "detalhes": "Refutada com cálculo direto.",
        }

        fallback = fallback_explicacao_posicao(
            board, "BRANCAS", avaliacao, linhas, refutacao, elementos
        )

        self.assertIsInstance(fallback, ExplicacaoPosicao)
        self.assertIn("brancas", fallback.veredito.lower())
        self.assertIn("e4", fallback.ameaca_concreta)
        self.assertTrue(len(fallback.plano_conversao) > 10)
        self.assertTrue(len(fallback.resumo_didatico) > 10)

    def test_fallback_posicao_xeque_mate(self) -> None:
        # Posição de mate pastor já consumado no tabuleiro
        fen_mate = "r1bqkb1r/pppp1Qpp/2n5/4p3/2B1n3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4"
        board = chess.Board(fen_mate)
        elementos = inspecionar_elementos_tabuleiro(board)
        avaliacao = {
            "score_cp": 10000,
            "mate": 0,
            "win_percent": 100.0,
            "lado_vencedor": "BRANCAS",
            "descricao": "Xeque-mate! As Brancas venceram a partida.",
        }
        fallback = fallback_explicacao_posicao(
            board, "BRANCAS", avaliacao, [], None, elementos
        )
        self.assertIn("xeque-mate", fallback.veredito.lower())
        self.assertIn("terminal", fallback.ameaca_concreta.lower())
        self.assertNotIn("o melhor lance", fallback.ameaca_concreta.lower())

    def test_fallback_posicao_afogamento(self) -> None:
        # Posição de afogamento (stalemate)
        fen_afogamento = "k7/8/1Q6/8/8/8/8/7K b - - 0 1"
        board = chess.Board(fen_afogamento)
        elementos = inspecionar_elementos_tabuleiro(board)
        avaliacao = {
            "score_cp": 0,
            "mate": None,
            "win_percent": 50.0,
            "lado_vencedor": "EQUILIBRADO",
            "descricao": "Empate por afogamento (stalemate).",
        }
        fallback = fallback_explicacao_posicao(
            board, "BRANCAS", avaliacao, [], None, elementos
        )
        self.assertIn("afogamento", fallback.veredito.lower())
        self.assertIn("terminal", fallback.ameaca_concreta.lower())


class GerarExplicacaoGeminiTest(unittest.TestCase):
    def test_gemini_client_none_usa_fallback(self) -> None:
        board = chess.Board()
        elementos = inspecionar_elementos_tabuleiro(board)
        avaliacao = {
            "score_cp": 200,
            "mate": None,
            "win_percent": 85.0,
            "lado_vencedor": "BRANCAS",
            "descricao": "+2.00 centipawns",
        }
        resultado = gerar_explicacao_gemini(
            None,
            board,
            "BRANCAS",
            "BRANCAS",
            avaliacao,
            [{"lance": "d4", "avaliacao": "+200", "pv_san": ["d4"]}],
            None,
            elementos,
            _fake_logger(),
        )

        self.assertIsInstance(resultado, ExplicacaoPosicao)
        self.assertIn("brancas", resultado.veredito.lower())

    def test_gemini_valido_faz_parse_correto(self) -> None:
        board = chess.Board()
        elementos = inspecionar_elementos_tabuleiro(board)
        avaliacao = {
            "score_cp": 350,
            "mate": None,
            "win_percent": 90.0,
            "lado_vencedor": "BRANCAS",
            "descricao": "+3.50 centipawns",
        }
        client = _FakeGeminiClient()
        resultado = gerar_explicacao_gemini(
            client,
            board,
            "BRANCAS",
            "BRANCAS",
            avaliacao,
            [{"lance": "d4", "avaliacao": "+350", "pv_san": ["d4", "d5", "c4"]}],
            {"defesa": "d5", "refutacao_linha": ["d4", "d5", "c4"], "detalhes": "c4 vence."},
            elementos,
            _fake_logger(),
        )

        self.assertIsInstance(resultado, ExplicacaoPosicao)
        self.assertIn("Brancas", resultado.veredito)
        self.assertEqual(client.chamadas, 1)

    def test_detectar_lances_inventados_distingue_lances_de_casas(self) -> None:
        board = chess.Board()
        permitidos = obter_lances_permitidos(board, [{"lance": "e4", "pv_san": ["e4", "e5"]}])

        # Lances legais e referências posicionais legítimas não devem ser marcados
        texto_legitimo = "Após e4 e5, o rei em e1 fica seguro e a casa d4 está sob controle."
        self.assertEqual(detectar_lances_inventados(texto_legitimo, permitidos), [])

        # Lances inventados de peças
        texto_alucinando_peca = "As Brancas devem jogar Qxe7# para arrematar a posição."
        self.assertIn("Qxe7#", detectar_lances_inventados(texto_alucinando_peca, permitidos))

        # Lances de peão prefixados inventados
        texto_alucinando_peao = "O lance e7 decide a partida imediatamente."
        self.assertIn("e7", detectar_lances_inventados(texto_alucinando_peao, permitidos))

    def test_gemini_retry_anti_alucinacao(self) -> None:
        board = chess.Board()
        elementos = inspecionar_elementos_tabuleiro(board)
        avaliacao = {
            "score_cp": 350,
            "mate": None,
            "win_percent": 90.0,
            "lado_vencedor": "BRANCAS",
            "descricao": "+3.50 centipawns",
        }
        # 1ª resposta tem lance inventado Qxe7#; 2ª resposta corrigida cita apenas d4
        resposta_alucinada = json.dumps(
            {
                "veredito": "Brancas vencem.",
                "ameaca_concreta": "O lance Qxe7# decide.",
                "o_que_parece_bom_mas_falha": "d5 falha.",
                "plano_conversao": "Avançar peões.",
                "resumo_didatico": "Vantagem branca.",
            }
        )
        resposta_corrigida = json.dumps(
            {
                "veredito": "Brancas vencem.",
                "ameaca_concreta": "O lance d4 decide.",
                "o_que_parece_bom_mas_falha": "d5 falha.",
                "plano_conversao": "Avançar peões.",
                "resumo_didatico": "Vantagem branca.",
            }
        )
        client = _FakeGeminiClient([resposta_alucinada, resposta_corrigida])
        resultado = gerar_explicacao_gemini(
            client,
            board,
            "BRANCAS",
            "BRANCAS",
            avaliacao,
            [{"lance": "d4", "avaliacao": "+350", "pv_san": ["d4"]}],
            None,
            elementos,
            _fake_logger(),
        )

        self.assertIsInstance(resultado, ExplicacaoPosicao)
        self.assertIn("d4", resultado.ameaca_concreta)
        self.assertEqual(client.chamadas, 2)

    def test_gemini_retry_json_invalido(self) -> None:
        board = chess.Board()
        elementos = inspecionar_elementos_tabuleiro(board)
        avaliacao = {
            "score_cp": 350,
            "mate": None,
            "win_percent": 90.0,
            "lado_vencedor": "BRANCAS",
            "descricao": "+3.50 centipawns",
        }
        # 1ª resposta inválida; 2ª resposta JSON válido
        resposta_invalida = "Isto não é um JSON válido: {errado}"
        resposta_valida = json.dumps(
            {
                "veredito": "Brancas vencem.",
                "ameaca_concreta": "d4 pressiona o centro.",
                "o_que_parece_bom_mas_falha": "d5 falha.",
                "plano_conversao": "Avançar peões.",
                "resumo_didatico": "Vantagem branca.",
            }
        )
        client = _FakeGeminiClient([resposta_invalida, resposta_valida])
        resultado = gerar_explicacao_gemini(
            client,
            board,
            "BRANCAS",
            "BRANCAS",
            avaliacao,
            [{"lance": "d4", "avaliacao": "+350", "pv_san": ["d4"]}],
            None,
            elementos,
            _fake_logger(),
        )

        self.assertIsInstance(resultado, ExplicacaoPosicao)
        self.assertEqual(client.chamadas, 2)


class ExplicarPosicaoEndToEndTest(unittest.TestCase):
    def test_explicar_posicao_com_fen_valida(self) -> None:
        engine = _FakeEngine()
        gemini = _FakeGeminiClient()
        settings = _fake_settings()
        logger = _fake_logger()
        lock = threading.Lock()

        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        resposta = explicar_posicao(
            engine,
            gemini,
            settings,
            logger,
            posicao=fen,
            lado="BRANCAS",
            engine_lock=lock,
        )

        self.assertEqual(resposta["fen"], fen)
        self.assertEqual(resposta["lado_a_jogar"], "BRANCAS")
        self.assertEqual(resposta["lado_analisado"], "BRANCAS")
        self.assertIn("avaliacao", resposta)
        self.assertIn("linhas_taticas", resposta)
        self.assertIn("elementos_posicionais", resposta)
        self.assertIn("explicacao", resposta)
        self.assertIn("veredito", resposta["explicacao"])
        self.assertIn("ameaca_concreta", resposta["explicacao"])

    def test_explicar_posicao_com_pgn_valido(self) -> None:
        engine = _FakeEngine()
        gemini = _FakeGeminiClient()
        settings = _fake_settings()
        logger = _fake_logger()

        pgn = "1. e4 e5 2. Nf3 Nc6"
        resposta = explicar_posicao(
            engine,
            gemini,
            settings,
            logger,
            posicao=pgn,
            lado=None,
        )

        self.assertIn("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R", resposta["fen"])
        self.assertEqual(resposta["lado_a_jogar"], "BRANCAS")
        self.assertEqual(resposta["lado_analisado"], "BRANCAS")

    def test_explicar_posicao_com_string_invalida_levanta_value_error(self) -> None:
        engine = _FakeEngine()
        gemini = _FakeGeminiClient()
        settings = _fake_settings()
        logger = _fake_logger()

        with self.assertRaises(ValueError):
            explicar_posicao(
                engine,
                gemini,
                settings,
                logger,
                posicao="nao_eh_nem_fen_nem_pgn",
            )


class SalvarExplicacaoPosicaoTest(unittest.TestCase):
    """Cobre a persistência que fecha a pendência P-10 (ESTADO.md)."""

    USER_ID_TESTE = "11111111-2222-3333-4444-555555555555"

    def setUp(self) -> None:
        # explicacoes_posicao é tabela raiz: user_id é NOT NULL (D-14).
        self._env = patch.dict(
            os.environ, {"DEFAULT_USER_ID": self.USER_ID_TESTE}
        )
        self._env.start()
        self.addCleanup(self._env.stop)

    def _resultado_minimo(self) -> dict[str, Any]:
        return {
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "lado_a_jogar": "BRANCAS",
            "lado_analisado": "BRANCAS",
            "avaliacao": {
                "score_cp": 0,
                "mate": None,
                "win_percent": 50.0,
                "lado_vencedor": "EQUILIBRADO",
                "descricao": "Posição inicial",
            },
            "linhas_taticas": [],
            "refutacao_defesa": None,
            "elementos_posicionais": {},
            "explicacao": {
                "veredito": "Equilibrado.",
                "ameaca_concreta": "Nenhuma.",
                "o_que_parece_bom_mas_falha": "N/A",
                "plano_conversao": "Desenvolver.",
                "resumo_didatico": "Início.",
            },
        }

    def test_insere_na_tabela_correta_com_o_resultado_completo(self) -> None:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"id": "novo-id-123"}]
        client.table.return_value.insert.return_value.execute.return_value = resp

        resultado = self._resultado_minimo()
        novo_id = salvar_explicacao_posicao(client, resultado)

        self.assertEqual(novo_id, "novo-id-123")
        client.table.assert_called_once_with("explicacoes_posicao")
        payload = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(payload["fen"], resultado["fen"])
        self.assertEqual(payload["lado_analisado"], "BRANCAS")
        self.assertEqual(payload["resultado"], resultado)
        self.assertEqual(payload["user_id"], self.USER_ID_TESTE)

    def test_user_id_explicito_sobrepoe_o_default_do_ambiente(self) -> None:
        # Fase B.2 (D-17): dono real da sessão, resolvido em api_server.py,
        # sobrepõe o fallback DEFAULT_USER_ID.
        user_id_sessao = "99999999-8888-7777-6666-555555555555"
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"id": "novo-id-456"}]
        client.table.return_value.insert.return_value.execute.return_value = resp

        salvar_explicacao_posicao(client, self._resultado_minimo(), user_id=user_id_sessao)

        payload = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(payload["user_id"], user_id_sessao)

    def test_retorna_none_se_resposta_nao_trouxer_dados(self) -> None:
        client = MagicMock()
        resp = MagicMock()
        resp.data = []
        client.table.return_value.insert.return_value.execute.return_value = resp

        novo_id = salvar_explicacao_posicao(client, self._resultado_minimo())

        self.assertIsNone(novo_id)


if __name__ == "__main__":
    unittest.main()
