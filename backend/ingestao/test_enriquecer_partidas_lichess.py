"""Testes da montagem de métricas: cobre a extração de precisão por fase."""

from __future__ import annotations

import unittest

from backend.ingestao.enriquecer_partidas_lichess import montar_metricas


def _game_export(white_analysis: dict, black_analysis: dict) -> dict:
    return {
        "players": {
            "white": {"user": {"name": "tantofaz123"}, "analysis": white_analysis},
            "black": {"user": {"name": "oponente"}, "analysis": black_analysis},
        },
        "division": {"middle": 18, "end": 40},
    }


class MontarMetricasFasesTest(unittest.TestCase):
    """players.<cor>.analysis.phases vira precisao_abertura/meiojogo/final."""

    def test_extrai_as_tres_precisoes_por_fase_do_lado_proprio(self) -> None:
        game_export = _game_export(
            white_analysis={
                "accuracy": 73,
                "inaccuracy": 10,
                "mistake": 1,
                "blunder": 3,
                "acpl": 70,
                "phases": {"opening": 88, "middlegame": 87, "endgame": 61},
            },
            black_analysis={"accuracy": 83, "phases": {"opening": 91, "middlegame": 68, "endgame": 87}},
        )

        metricas = montar_metricas("partida-1", game_export, "tantofaz123")

        assert metricas is not None
        self.assertEqual(metricas["precisao_abertura"], 88)
        self.assertEqual(metricas["precisao_meiojogo"], 87)
        self.assertEqual(metricas["precisao_final"], 61)
        # Continua usando a análise do lado PRÓPRIO, não a do oponente.
        self.assertEqual(metricas["precisao_propria"], 73)

    def test_sem_phases_nao_quebra_e_devolve_none_nas_tres_colunas(self) -> None:
        game_export = _game_export(
            white_analysis={"accuracy": 73},
            black_analysis={"accuracy": 83},
        )

        metricas = montar_metricas("partida-1", game_export, "tantofaz123")

        assert metricas is not None
        self.assertIsNone(metricas["precisao_abertura"])
        self.assertIsNone(metricas["precisao_meiojogo"])
        self.assertIsNone(metricas["precisao_final"])


if __name__ == "__main__":
    unittest.main()
