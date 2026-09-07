"""Testes unitários da conversão de centipawns em win percent."""

import unittest

from backend.common.chess_math import centipawns_para_win_percent


class CentipawnsParaWinPercentTest(unittest.TestCase):
    def test_posicao_equilibrada_fica_perto_de_50_por_cento(self) -> None:
        self.assertAlmostEqual(centipawns_para_win_percent(0), 50.0, places=6)

    def test_cp_muito_alto_fica_perto_de_100_por_cento(self) -> None:
        self.assertGreater(centipawns_para_win_percent(10_000), 99.0)

    def test_cp_muito_baixo_fica_perto_de_0_por_cento(self) -> None:
        self.assertLess(centipawns_para_win_percent(-10_000), 1.0)

    def test_queda_a_partir_de_posicao_equilibrada_e_maior_que_a_partir_de_ganha(
        self,
    ) -> None:
        queda_do_equilibrio = centipawns_para_win_percent(
            0
        ) - centipawns_para_win_percent(-300)
        queda_da_posicao_ganha = centipawns_para_win_percent(
            800
        ) - centipawns_para_win_percent(500)

        self.assertGreater(queda_do_equilibrio, queda_da_posicao_ganha)


if __name__ == "__main__":
    unittest.main()
