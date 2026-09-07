"""Testes unitários da análise de partidas."""

import unittest

from backend.analise_engine.analisar_partidas import (
    PlayerMoveEval,
    detectar_erosao,
    processar_partida,
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


if __name__ == "__main__":
    unittest.main()