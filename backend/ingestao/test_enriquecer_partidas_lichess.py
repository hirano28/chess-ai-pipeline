"""Testes da montagem de métricas: cobre a extração de precisão por fase."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.ingestao.enriquecer_partidas_lichess import (
    enriquecer_uma_partida_manual,
    montar_metricas,
    selecionar_partidas,
)


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


def _resp(data: list) -> MagicMock:
    resposta = MagicMock()
    resposta.data = data
    return resposta


class SelecionarPartidasFiltraPeloPerfilTest(unittest.TestCase):
    """D-31: sem user_id, o loop de enriquecimento varreria partidas de todo mundo."""

    def test_com_user_id_filtra_por_dono_alem_da_plataforma(self) -> None:
        client = MagicMock()
        primeiro_eq = client.table.return_value.select.return_value.eq.return_value
        segundo_eq = primeiro_eq.eq.return_value
        segundo_eq.range.return_value.execute.return_value = _resp(
            [{"id": "p1", "external_id": "e1", "user_id": "user-a"}]
        )
        # tempos_lance / metricas_lichess_partida (sem filtro de dono, tabelas filhas)
        client.table.return_value.select.return_value.range.return_value.execute.return_value = _resp([])

        partidas = selecionar_partidas(client, user_id="user-a")

        primeiro_eq.eq.assert_called_once_with("user_id", "user-a")
        self.assertEqual(partidas, [{"id": "p1", "external_id": "e1", "user_id": "user-a"}])

    def test_sem_user_id_nao_filtra_por_dono(self) -> None:
        client = MagicMock()
        no = client.table.return_value.select.return_value.eq.return_value
        no.range.return_value.execute.return_value = _resp([])

        selecionar_partidas(client)

        no.eq.assert_not_called()


class EnriquecerUmaPartidaManualTest(unittest.TestCase):
    """Modo --external-id resolve o username do DONO real da partida, não um .env fixo."""

    @patch("backend.ingestao.enriquecer_partidas_lichess.enriquecer_partida")
    @patch("backend.ingestao.enriquecer_partidas_lichess.fetch_game_export")
    @patch("backend.ingestao.enriquecer_partidas_lichess.carregar_perfis")
    @patch("backend.ingestao.enriquecer_partidas_lichess.selecionar_partidas")
    def test_usa_o_username_do_perfil_com_o_mesmo_user_id_da_partida(
        self, mock_selecionar, mock_perfis, mock_fetch_export, mock_enriquecer
    ) -> None:
        mock_selecionar.return_value = [
            {"id": "p1", "external_id": "e1", "user_id": "user-a"}
        ]
        mock_perfis.return_value = [
            {"user_id": "user-b", "lichess_username": "contadaoutrapessoa"},
            {"user_id": "user-a", "lichess_username": "tantofaz123"},
        ]
        mock_fetch_export.return_value = {"moves": ""}
        client = MagicMock()
        logger = MagicMock()

        enriquecer_uma_partida_manual(client, logger, "e1", dry_run=True)

        mock_enriquecer.assert_called_once_with(
            client,
            {"id": "p1", "external_id": "e1", "user_id": "user-a"},
            {"moves": ""},
            "tantofaz123",
            True,
        )


if __name__ == "__main__":
    unittest.main()
