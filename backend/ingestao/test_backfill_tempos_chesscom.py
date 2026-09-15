"""Testes unitários da extração de relógios de partidas do Chess.com (Fase 15)."""

from __future__ import annotations

import unittest

from backend.ingestao.backfill_tempos_chesscom import (
    extrair_tempos_pgn_chesscom,
    parse_time_control,
)

SAMPLE_PGN_300 = """[Event "Live Chess"]
[Site "Chess.com"]
[Date "2026.08.29"]
[White "Player1"]
[Black "Player2"]
[TimeControl "300"]

1. e4 {[%clk 0:04:58.1]} 1... e6 {[%clk 0:04:59.9]} 2. e5 {[%clk 0:04:56.5]} 2... d6 {[%clk 0:04:59.7]} 0-1
"""

SAMPLE_PGN_INCREMENT = """[Event "Live Chess"]
[Site "Chess.com"]
[Date "2026.08.29"]
[White "Player1"]
[Black "Player2"]
[TimeControl "180+2"]

1. d4 {[%clk 0:02:59.0]} 1... d5 {[%clk 0:03:01.0]} 2. c4 {[%clk 0:02:58.5]} 2... e6 {[%clk 0:03:00.5]} 1/2-1/2
"""

SAMPLE_PGN_NO_CLK = """[Event "Classical"]
[Site "Chess.com"]
[Date "2026.08.29"]
[White "Player1"]
[Black "Player2"]

1. e4 e5 2. Nf3 Nc6 1-0
"""


class BackfillTemposChesscomTest(unittest.TestCase):
    def test_parse_time_control_simples(self) -> None:
        initial, inc = parse_time_control("300")
        self.assertEqual(initial, 300.0)
        self.assertEqual(inc, 0.0)

    def test_parse_time_control_com_incremento(self) -> None:
        initial, inc = parse_time_control("180+2")
        self.assertEqual(initial, 180.0)
        self.assertEqual(inc, 2.0)

    def test_parse_time_control_invalido_ou_ausente(self) -> None:
        initial, inc = parse_time_control("-")
        self.assertEqual(initial, 300.0)
        self.assertEqual(inc, 0.0)

        initial, inc = parse_time_control(None)
        self.assertEqual(initial, 300.0)
        self.assertEqual(inc, 0.0)

    def test_extrair_tempos_pgn_300(self) -> None:
        rows = extrair_tempos_pgn_chesscom(SAMPLE_PGN_300, "partida-1")
        self.assertEqual(len(rows), 4)

        # Lance 1 Brancas
        self.assertEqual(rows[0]["partida_id"], "partida-1")
        self.assertEqual(rows[0]["numero_lance"], 1)
        self.assertEqual(rows[0]["cor"], "BRANCAS")
        self.assertAlmostEqual(rows[0]["tempo_restante_seg"], 298.1, places=1)
        self.assertAlmostEqual(rows[0]["tempo_gasto_seg"], 1.9, places=1)

        # Lance 1 Pretas
        self.assertEqual(rows[1]["numero_lance"], 1)
        self.assertEqual(rows[1]["cor"], "PRETAS")
        self.assertAlmostEqual(rows[1]["tempo_restante_seg"], 299.9, places=1)
        self.assertAlmostEqual(rows[1]["tempo_gasto_seg"], 0.1, places=1)

        # Lance 2 Brancas
        self.assertEqual(rows[2]["numero_lance"], 2)
        self.assertEqual(rows[2]["cor"], "BRANCAS")
        self.assertAlmostEqual(rows[2]["tempo_restante_seg"], 296.5, places=1)
        # 298.1 - 296.5 = 1.6s
        self.assertAlmostEqual(rows[2]["tempo_gasto_seg"], 1.6, places=1)

        # Lance 2 Pretas
        self.assertEqual(rows[3]["numero_lance"], 2)
        self.assertEqual(rows[3]["cor"], "PRETAS")
        self.assertAlmostEqual(rows[3]["tempo_restante_seg"], 299.7, places=1)
        # 299.9 - 299.7 = 0.2s
        self.assertAlmostEqual(rows[3]["tempo_gasto_seg"], 0.2, places=1)

    def test_extrair_tempos_com_incremento(self) -> None:
        rows = extrair_tempos_pgn_chesscom(SAMPLE_PGN_INCREMENT, "partida-2")
        self.assertEqual(len(rows), 4)

        # Lance 1 Brancas: 180 inicial - 179 restante + 2 inc = 3.0s gastos
        self.assertAlmostEqual(rows[0]["tempo_restante_seg"], 179.0, places=1)
        self.assertAlmostEqual(rows[0]["tempo_gasto_seg"], 3.0, places=1)

    def test_extrair_tempos_pgn_sem_clk(self) -> None:
        rows = extrair_tempos_pgn_chesscom(SAMPLE_PGN_NO_CLK, "partida-3")
        self.assertEqual(rows, [])

    def test_extrair_tempos_pgn_vazio(self) -> None:
        self.assertEqual(extrair_tempos_pgn_chesscom("", "partida-4"), [])
        self.assertEqual(extrair_tempos_pgn_chesscom("   ", "partida-4"), [])


if __name__ == "__main__":
    unittest.main()

