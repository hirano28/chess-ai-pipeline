"""Testes unitários para o módulo backend.common.lichess_explorer."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.common.lichess_explorer import (
    _extrair_lances_pgn,
    consultar_opening_explorer,
    detectar_saida_teoria,
)


class ConsultarOpeningExplorerTest(unittest.TestCase):
    @patch("backend.common.lichess_explorer.requests.get")
    def test_consulta_sucesso_retorna_dados_formatados(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "white": 100,
            "draws": 50,
            "black": 30,
            "opening": {"eco": "B00", "name": "King's Pawn Opening"},
            "moves": [{"uci": "e7e5", "san": "e5", "white": 60, "draws": 30, "black": 20}],
        }
        mock_get.return_value = mock_resp

        res = consultar_opening_explorer(["e2e4"], token="token_fake")

        self.assertTrue(res["sucesso"])
        self.assertEqual(res["total"], 180)
        self.assertEqual(res["opening"]["eco"], "B00")
        self.assertEqual(len(res["moves"]), 1)

    @patch("backend.common.lichess_explorer.requests.get")
    def test_status_401_retorna_autenticacao_necessaria(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        res = consultar_opening_explorer(["e2e4"])

        self.assertFalse(res["sucesso"])
        self.assertEqual(res["erro"], "autenticacao_necessaria")

    @patch("backend.common.lichess_explorer.requests.get")
    def test_falha_de_rede_retorna_erro_gracioso(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = RuntimeError("timeout simulado")

        res = consultar_opening_explorer(["e2e4"])

        self.assertFalse(res["sucesso"])
        self.assertEqual(res["erro"], "falha_rede")


class ExtrairLancesPgnTest(unittest.TestCase):
    def test_extrai_lances_de_pgn_valido(self) -> None:
        pgn = "1. e4 e5 2. Nf3 Nc6 *"
        uci, san = _extrair_lances_pgn(pgn)
        self.assertEqual(uci, ["e2e4", "e7e5", "g1f3", "b8c6"])
        self.assertEqual(san, ["e4", "e5", "Nf3", "Nc6"])

    def test_extrai_de_lista_uci(self) -> None:
        moves = ["e2e4", "e7e5"]
        uci, san = _extrair_lances_pgn(moves)
        self.assertEqual(uci, ["e2e4", "e7e5"])
        self.assertEqual(san, ["e4", "e5"])

    def test_pgn_invalido_retorna_vazio(self) -> None:
        uci, san = _extrair_lances_pgn("")
        self.assertEqual(uci, [])
        self.assertEqual(san, [])


class DetectarSaidaTeoriaTest(unittest.TestCase):
    def test_sem_lances_retorna_disponivel_false(self) -> None:
        res = detectar_saida_teoria("")
        self.assertFalse(res["disponivel"])
        self.assertEqual(res["motivo"], "sem_lances")

    @patch("backend.common.lichess_explorer.consultar_opening_explorer")
    def test_detecta_saida_de_livro_com_busca_binaria(self, mock_explorer: MagicMock) -> None:
        # Simula:
        # ply 1 (1. e4): 100 partidas
        # ply 2 (1... c5): 80 partidas
        # ply 3 (2. Nf3): 70 partidas (último lance teórico)
        # ply 4 (2... h6?!): 0 partidas (saída de livro)
        def mock_side_effect(moves: list[str], token: str | None = None) -> dict:
            n = len(moves)
            if n <= 3:
                return {
                    "sucesso": True,
                    "white": 40,
                    "draws": 20,
                    "black": 10,
                    "total": 70,
                    "opening": {"eco": "B27", "name": "Sicilian Defense"},
                    "moves": [{"uci": "d7d6", "san": "d6", "white": 20, "draws": 10, "black": 5}],
                }
            return {
                "sucesso": True,
                "white": 0,
                "draws": 0,
                "black": 0,
                "total": 0,
                "opening": {"eco": "B27", "name": "Sicilian Defense"},
                "moves": [],
            }

        mock_explorer.side_effect = mock_side_effect

        pgn = "1. e4 c5 2. Nf3 h6 3. d4 cxd4 *"
        res = detectar_saida_teoria(pgn, cor_jogada="PRETAS")

        self.assertTrue(res["sucesso"])
        self.assertTrue(res["disponivel"])
        self.assertFalse(res["ficou_no_livro"])
        # Saiu no ply 4 (lance 2 de Pretas: h6)
        self.assertEqual(res["ply_saida"], 4)
        self.assertEqual(res["numero_lance_saida"], 2)
        self.assertEqual(res["cor_saida"], "PRETAS")
        self.assertEqual(res["quem_saiu"], "JOGADOR")
        self.assertEqual(res["lance_san"], "h6")
        self.assertEqual(res["nome_abertura"], "Sicilian Defense")
        self.assertEqual(len(res["candidatos_recomendados"]), 1)

    @patch("backend.common.lichess_explorer.consultar_opening_explorer")
    def test_quem_saiu_oponente_quando_cor_diverge(self, mock_explorer: MagicMock) -> None:
        def mock_side_effect(moves: list[str], token: str | None = None) -> dict:
            if len(moves) <= 2:
                return {
                    "sucesso": True,
                    "white": 50,
                    "draws": 20,
                    "black": 10,
                    "total": 80,
                    "opening": {"eco": "C00", "name": "French Defense"},
                    "moves": [{"uci": "d2d4", "san": "d4"}],
                }
            return {"sucesso": True, "white": 0, "draws": 0, "black": 0, "total": 0, "moves": []}

        mock_explorer.side_effect = mock_side_effect

        # 1. e4 e6 2. h4?! (ply 3, Brancas)
        pgn = "1. e4 e6 2. h4 d5 *"
        res = detectar_saida_teoria(pgn, cor_jogada="PRETAS")

        self.assertEqual(res["ply_saida"], 3)
        self.assertEqual(res["cor_saida"], "BRANCAS")
        self.assertEqual(res["quem_saiu"], "OPONENTE")

    @patch("backend.common.lichess_explorer.consultar_opening_explorer")
    def test_partida_permanece_no_livro(self, mock_explorer: MagicMock) -> None:
        mock_explorer.return_value = {
            "sucesso": True,
            "white": 100,
            "draws": 50,
            "black": 30,
            "total": 180,
            "opening": {"eco": "C01", "name": "French Defense: Exchange Variation"},
            "moves": [{"uci": "g1f3", "san": "Nf3"}],
        }

        pgn = "1. e4 e6 2. d4 d5 3. exd5 exd5 *"
        res = detectar_saida_teoria(pgn)

        self.assertTrue(res["sucesso"])
        self.assertTrue(res["ficou_no_livro"])
        self.assertEqual(res["nome_abertura"], "French Defense: Exchange Variation")


if __name__ == "__main__":
    unittest.main()

