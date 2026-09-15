"""Testes unitários para o módulo backend.common.syzygy_tablebase."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.common.syzygy_tablebase import (
    avaliar_lance_final_syzygy,
    consultar_syzygy,
    contar_pecas_fen,
)


class ContarPecasFenTest(unittest.TestCase):
    def test_posicao_inicial_tem_32_pecas(self) -> None:
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        self.assertEqual(contar_pecas_fen(fen), 32)

    def test_final_kq_vs_k_tem_3_pecas(self) -> None:
        fen = "8/8/8/4k3/8/8/4Q3/4K3 b - - 0 1"
        self.assertEqual(contar_pecas_fen(fen), 3)

    def test_fen_invalido_retorna_99(self) -> None:
        self.assertEqual(contar_pecas_fen("fen_completamente_invalido"), 99)


class ConsultarSyzygyTest(unittest.TestCase):
    def test_posicao_com_mais_de_7_pecas_retorna_none(self) -> None:
        # Posição inicial tem 32 peças
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        self.assertIsNone(consultar_syzygy(fen))

    def test_posicao_ilegal_rei_oponente_em_xeque_retorna_none(self) -> None:
        # Branco a jogar mas preto já em xeque ilegal
        fen = "4k3/8/8/8/8/8/4Q3/4K3 w - - 0 1"
        self.assertIsNone(consultar_syzygy(fen))

    @patch("backend.common.syzygy_tablebase.requests.get")
    def test_consulta_sucesso_retorna_json(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "category": "win",
            "dtz": 15,
            "moves": [{"uci": "e1d2", "san": "Kd2", "category": "win"}],
        }
        mock_get.return_value = mock_resp

        fen = "8/8/8/4k3/8/8/4Q3/4K3 b - - 0 1"
        res = consultar_syzygy(fen)

        self.assertIsNotNone(res)
        self.assertEqual(res["category"], "win")

    @patch("backend.common.syzygy_tablebase.requests.get")
    def test_status_diferente_de_200_retorna_none(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        fen = "8/8/8/4k3/8/8/4Q3/4K3 b - - 0 1"
        self.assertIsNone(consultar_syzygy(fen))


class AvaliarLanceFinalSyzygyTest(unittest.TestCase):
    def test_inelegivel_se_tiver_mais_de_7_pecas(self) -> None:
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        res = avaliar_lance_final_syzygy(fen, "e2e4")
        self.assertFalse(res["elegivel_syzygy"])
        self.assertIn("Posição possui", res["motivo"])

    @patch("backend.common.syzygy_tablebase.consultar_syzygy")
    def test_identifica_erro_de_conversao_win_virou_draw(self, mock_syzygy: MagicMock) -> None:
        mock_syzygy.return_value = {
            "category": "win",
            "dtz": 5,
            "dtm": 12,
            "moves": [
                {"uci": "e1d2", "san": "Kd2", "category": "draw", "dtz": 0},
                {"uci": "e1f2", "san": "Kf2", "category": "win", "dtz": 4},
            ],
        }

        fen = "8/8/8/4k3/8/8/4Q3/4K3 w - - 0 1"
        res = avaliar_lance_final_syzygy(fen, "Kd2")

        self.assertTrue(res["elegivel_syzygy"])
        self.assertEqual(res["categoria_antes"], "win")
        self.assertEqual(res["categoria_lance_jogado"], "draw")
        self.assertTrue(res["eh_blunder_teorico"])
        self.assertEqual(res["tipo_erro_final"], "erro_conversao")
        self.assertIn("vitória provada perdida", res["veredito_pt"])
        self.assertEqual(res["melhores_lances"][0]["san"], "Kf2")

    @patch("backend.common.syzygy_tablebase.consultar_syzygy")
    def test_identifica_erro_de_defesa_draw_virou_loss(self, mock_syzygy: MagicMock) -> None:
        mock_syzygy.return_value = {
            "category": "draw",
            "dtz": 0,
            "moves": [
                {"uci": "e1d1", "san": "Kd1", "category": "loss", "dtz": -8},
                {"uci": "e1f1", "san": "Kf1", "category": "draw", "dtz": 0},
            ],
        }

        fen = "8/8/8/4k3/8/8/4Q3/4K3 w - - 0 1"
        res = avaliar_lance_final_syzygy(fen, "Kd1")

        self.assertTrue(res["elegivel_syzygy"])
        self.assertEqual(res["categoria_antes"], "draw")
        self.assertEqual(res["categoria_lance_jogado"], "loss")
        self.assertTrue(res["eh_blunder_teorico"])
        self.assertEqual(res["tipo_erro_final"], "erro_defesa")
        self.assertIn("empate entregue em derrota", res["veredito_pt"])

    @patch("backend.common.syzygy_tablebase.consultar_syzygy")
    def test_lance_preciso_mantem_vitoria(self, mock_syzygy: MagicMock) -> None:
        mock_syzygy.return_value = {
            "category": "win",
            "dtz": 5,
            "moves": [
                {"uci": "e1f2", "san": "Kf2", "category": "win", "dtz": 4},
            ],
        }

        fen = "8/8/8/4k3/8/8/4Q3/4K3 w - - 0 1"
        res = avaliar_lance_final_syzygy(fen, "Kf2")

        self.assertTrue(res["elegivel_syzygy"])
        self.assertFalse(res["eh_blunder_teorico"])
        self.assertIsNone(res["tipo_erro_final"])
        self.assertIn("vitória teórica mantida", res["veredito_pt"])


if __name__ == "__main__":
    unittest.main()

