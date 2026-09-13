"""Testes unitários do backfill de fen_antes_lance (D-27)."""

import unittest

from backend.analise_engine.backfill_fen_lances_criticos import (
    mapear_fen_antes_por_lance,
)


class MapearFenAntesPorLanceTest(unittest.TestCase):
    def test_fen_e_da_posicao_antes_do_lance_do_jogador(self) -> None:
        # 1. e4 e5 2. Nf3 Nc6 3. Bb5 - jogador de PRETAS.
        pgn = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"

        fen_por_lance = mapear_fen_antes_por_lance(pgn, "PRETAS", partida_id=1)

        self.assertEqual(set(fen_por_lance), {1, 2, 3})
        # Antes do 1...e5, só 1.e4 foi jogado.
        self.assertEqual(
            fen_por_lance[1],
            "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        )

    def test_fen_do_jogador_de_brancas_ignora_lances_pretas(self) -> None:
        pgn = "1. e4 e5 2. Nf3 Nc6 3. Bb5"

        fen_por_lance = mapear_fen_antes_por_lance(pgn, "BRANCAS", partida_id=2)

        self.assertEqual(set(fen_por_lance), {1, 2, 3})
        # Antes do 2.Nf3, 1.e4 e 1...e5 já foram jogados.
        self.assertEqual(
            fen_por_lance[2],
            "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
        )


if __name__ == "__main__":
    unittest.main()
