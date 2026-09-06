"""Testes unitários da análise de partidas."""

import unittest

from backend.analise_engine.analisar_partidas import processar_partida


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


if __name__ == "__main__":
    unittest.main()