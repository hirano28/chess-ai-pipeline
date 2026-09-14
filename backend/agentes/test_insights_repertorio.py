"""Testes das agregações de repertório: cálculo puro com dados sintéticos."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from backend.agentes.agente2_analista import HEXAGON_CATEGORIES
from backend.agentes.insights_repertorio import (
    MIN_AMOSTRA,
    OUTRAS,
    calcular_categorias_por_abertura,
    calcular_lance_medio_pico_por_abertura,
    calcular_metricas_por_abertura_e_cor,
    calcular_taxa_vitoria_por_cor,
    fetch_diagnosticos_com_partida,
    fetch_lances_pico,
    fetch_metricas_por_partida,
    fetch_partidas_repertorio,
)


def _partida(
    id_: str,
    cor: str = "BRANCAS",
    resultado: str = "VITORIA",
    abertura: str | None = "Francesa",
) -> dict:
    return {
        "id": id_,
        "cor_jogada": cor,
        "resultado": resultado,
        "abertura_normalizada": abertura,
    }


class CalcularTaxaVitoriaPorCorTest(unittest.TestCase):
    def test_conta_total_e_vitorias_por_cor_separadamente(self) -> None:
        partidas = [
            _partida("1", "BRANCAS", "VITORIA"),
            _partida("2", "BRANCAS", "VITORIA"),
            _partida("3", "BRANCAS", "DERROTA"),
            _partida("4", "PRETAS", "DERROTA"),
            _partida("5", "PRETAS", "EMPATE"),
        ]

        resultado = calcular_taxa_vitoria_por_cor(partidas)

        self.assertEqual(
            resultado["BRANCAS"],
            {"total": 3, "vitorias": 2, "taxa_vitoria_pct": 66.67},
        )
        self.assertEqual(
            resultado["PRETAS"],
            {"total": 2, "vitorias": 0, "taxa_vitoria_pct": 0.0},
        )

    def test_ignora_partida_sem_cor_jogada(self) -> None:
        partidas = [_partida("1", cor=""), _partida("2", "BRANCAS", "VITORIA")]

        resultado = calcular_taxa_vitoria_por_cor(partidas)

        self.assertEqual(set(resultado.keys()), {"BRANCAS"})
        self.assertEqual(resultado["BRANCAS"]["total"], 1)


class CalcularMetricasPorAberturaECorTest(unittest.TestCase):
    def test_abertura_com_amostra_suficiente_aparece_com_o_proprio_nome(self) -> None:
        partidas = [
            _partida(str(i), "BRANCAS", "VITORIA" if i % 2 == 0 else "DERROTA", "Francesa")
            for i in range(6)
        ]
        metricas = {
            str(i): {
                "precisao_abertura": 80.0,
                "precisao_meiojogo": 70.0,
                "precisao_final": None,
            }
            for i in range(6)
        }

        resultado = calcular_metricas_por_abertura_e_cor(partidas, metricas)

        self.assertEqual(len(resultado), 1)
        linha = resultado[0]
        self.assertEqual(linha["abertura_normalizada"], "Francesa")
        self.assertEqual(linha["cor_jogada"], "BRANCAS")
        self.assertEqual(linha["total"], 6)
        self.assertEqual(linha["vitorias"], 3)
        self.assertEqual(linha["taxa_vitoria_pct"], 50.0)
        self.assertEqual(linha["precisao_media_abertura"], 80.0)
        self.assertEqual(linha["precisao_media_meiojogo"], 70.0)
        # precisao_final só tem None nesta amostra -> média é None, não 0.
        self.assertIsNone(linha["precisao_media_final"])

    def test_abertura_abaixo_do_limiar_vira_outras_por_cor(self) -> None:
        self.assertEqual(MIN_AMOSTRA, 5)
        partidas = [
            _partida("1", "BRANCAS", "VITORIA", "Siciliana"),
            _partida("2", "BRANCAS", "DERROTA", "Siciliana"),
            _partida("3", "BRANCAS", "VITORIA", "Caro-Kann"),
        ]

        resultado = calcular_metricas_por_abertura_e_cor(partidas, {})

        self.assertEqual(len(resultado), 1)
        linha = resultado[0]
        self.assertEqual(linha["abertura_normalizada"], OUTRAS)
        self.assertEqual(linha["cor_jogada"], "BRANCAS")
        self.assertEqual(linha["total"], 3)
        self.assertEqual(linha["vitorias"], 2)

    def test_outras_nao_mistura_cores_diferentes(self) -> None:
        partidas = [
            _partida("1", "BRANCAS", "VITORIA", "Siciliana"),
            _partida("2", "PRETAS", "DERROTA", "Siciliana"),
        ]

        resultado = calcular_metricas_por_abertura_e_cor(partidas, {})

        chaves = {(item["abertura_normalizada"], item["cor_jogada"]) for item in resultado}
        self.assertEqual(chaves, {(OUTRAS, "BRANCAS"), (OUTRAS, "PRETAS")})

    def test_ignora_partida_sem_abertura_normalizada(self) -> None:
        partidas = [_partida("1", "BRANCAS", "VITORIA", abertura=None)]

        resultado = calcular_metricas_por_abertura_e_cor(partidas, {})

        self.assertEqual(resultado, [])


class CalcularLanceMedioPicoPorAberturaTest(unittest.TestCase):
    def test_calcula_media_e_mediana_com_amostra_suficiente(self) -> None:
        partidas = [_partida(str(i), abertura="Francesa") for i in range(5)]
        lances_pico = [
            {"partida_id": "0", "numero_lance": 10},
            {"partida_id": "1", "numero_lance": 12},
            {"partida_id": "2", "numero_lance": 14},
            {"partida_id": "3", "numero_lance": 16},
            {"partida_id": "4", "numero_lance": 18},
        ]

        resultado = calcular_lance_medio_pico_por_abertura(partidas, lances_pico)

        self.assertEqual(len(resultado), 1)
        linha = resultado[0]
        self.assertEqual(linha["abertura_normalizada"], "Francesa")
        self.assertEqual(linha["total_eventos"], 5)
        self.assertEqual(linha["lance_medio"], 14.0)
        self.assertEqual(linha["lance_mediano"], 14)

    def test_abertura_abaixo_do_limiar_de_eventos_fica_de_fora(self) -> None:
        partidas = [_partida(str(i), abertura="Caro-Kann") for i in range(3)]
        lances_pico = [
            {"partida_id": "0", "numero_lance": 8},
            {"partida_id": "1", "numero_lance": 9},
        ]

        resultado = calcular_lance_medio_pico_por_abertura(partidas, lances_pico)

        self.assertEqual(resultado, [])

    def test_ignora_evento_de_partida_sem_abertura_conhecida(self) -> None:
        partidas = [_partida("0", abertura=None)]
        lances_pico = [{"partida_id": "0", "numero_lance": 10}]

        resultado = calcular_lance_medio_pico_por_abertura(partidas, lances_pico)

        self.assertEqual(resultado, [])


class CalcularCategoriasPorAberturaTest(unittest.TestCase):
    def test_conta_tags_na_categoria_certa_reaproveitando_hexagon_categories(self) -> None:
        # calculo_tatico_deficiente -> TATICA; avaliacao_posicional_incorreta -> ESTRATEGIA.
        self.assertIn("calculo_tatico_deficiente", HEXAGON_CATEGORIES["TATICA"])
        self.assertIn("avaliacao_posicional_incorreta", HEXAGON_CATEGORIES["ESTRATEGIA"])

        partidas = [_partida(str(i), abertura="Francesa") for i in range(5)]
        diagnosticos = [
            {
                "tags_falha": ["calculo_tatico_deficiente"],
                "lances_criticos": {"partida_id": "0"},
            },
            {
                "tags_falha": ["calculo_tatico_deficiente"],
                "lances_criticos": {"partida_id": "1"},
            },
            {
                "tags_falha": ["avaliacao_posicional_incorreta"],
                "lances_criticos": {"partida_id": "2"},
            },
            {
                "tags_falha": ["calculo_tatico_deficiente", "avaliacao_posicional_incorreta"],
                "lances_criticos": [{"partida_id": "3"}],
            },
            {"tags_falha": [], "lances_criticos": {"partida_id": "4"}},
        ]

        resultado = calcular_categorias_por_abertura(partidas, diagnosticos)

        self.assertIn("Francesa", resultado)
        self.assertEqual(resultado["Francesa"]["TATICA"], 3)
        self.assertEqual(resultado["Francesa"]["ESTRATEGIA"], 2)
        self.assertEqual(resultado["Francesa"]["FINAIS"], 0)

    def test_abertura_abaixo_do_limiar_de_diagnosticos_fica_de_fora(self) -> None:
        partidas = [_partida(str(i), abertura="Caro-Kann") for i in range(2)]
        diagnosticos = [
            {
                "tags_falha": ["calculo_tatico_deficiente"],
                "lances_criticos": {"partida_id": "0"},
            },
            {
                "tags_falha": ["calculo_tatico_deficiente"],
                "lances_criticos": {"partida_id": "1"},
            },
        ]

        resultado = calcular_categorias_por_abertura(partidas, diagnosticos)

        self.assertEqual(resultado, {})

    def test_ignora_tag_fora_do_vocabulario_sem_quebrar(self) -> None:
        partidas = [_partida(str(i), abertura="Francesa") for i in range(5)]
        diagnosticos = [
            {"tags_falha": ["tag_inexistente"], "lances_criticos": {"partida_id": "0"}},
            {
                "tags_falha": ["calculo_tatico_deficiente"],
                "lances_criticos": {"partida_id": "1"},
            },
            {
                "tags_falha": ["calculo_tatico_deficiente"],
                "lances_criticos": {"partida_id": "2"},
            },
            {
                "tags_falha": ["calculo_tatico_deficiente"],
                "lances_criticos": {"partida_id": "3"},
            },
            {
                "tags_falha": ["calculo_tatico_deficiente"],
                "lances_criticos": {"partida_id": "4"},
            },
        ]

        resultado = calcular_categorias_por_abertura(partidas, diagnosticos)

        self.assertEqual(resultado["Francesa"]["TATICA"], 4)


class FetchFiltraPeloDonoTest(unittest.TestCase):
    """D-30: as 4 buscas precisam filtrar por user_id NA QUERY, não só no endpoint."""

    @staticmethod
    def _resp_vazia() -> MagicMock:
        resp = MagicMock()
        resp.data = []
        return resp

    def test_fetch_partidas_repertorio_filtra_por_user_id(self) -> None:
        # select(...).in_("plataforma", ...).eq("user_id", user_id).range(...).execute()
        client = MagicMock()
        no = client.table.return_value.select.return_value.in_.return_value
        no.eq.return_value.range.return_value.execute.return_value = self._resp_vazia()

        fetch_partidas_repertorio(client, "user-a")

        select_arg = client.table.return_value.select.call_args[0][0]
        self.assertNotIn("!inner", select_arg)  # tem user_id próprio, sem embed
        no.eq.assert_called_once_with("user_id", "user-a")

    def test_fetch_metricas_por_partida_filtra_via_embed(self) -> None:
        # select(...).eq("partidas.user_id", user_id).range(...).execute()
        client = MagicMock()
        no = client.table.return_value.select.return_value
        no.eq.return_value.range.return_value.execute.return_value = self._resp_vazia()

        fetch_metricas_por_partida(client, "user-a")

        select_arg = client.table.return_value.select.call_args[0][0]
        self.assertIn("partidas!inner", select_arg)
        no.eq.assert_called_once_with("partidas.user_id", "user-a")

    def test_fetch_lances_pico_filtra_via_embed(self) -> None:
        # select(...).eq("tipo_evento", "PICO").eq("partidas.user_id", user_id).range(...).execute()
        client = MagicMock()
        primeiro_eq = client.table.return_value.select.return_value.eq
        segundo_eq = primeiro_eq.return_value.eq
        segundo_eq.return_value.range.return_value.execute.return_value = self._resp_vazia()

        fetch_lances_pico(client, "user-a")

        select_arg = client.table.return_value.select.call_args[0][0]
        self.assertIn("partidas!inner", select_arg)
        primeiro_eq.assert_called_once_with("tipo_evento", "PICO")
        segundo_eq.assert_called_once_with("partidas.user_id", "user-a")

    def test_fetch_diagnosticos_com_partida_filtra_via_embed_duplo(self) -> None:
        # select(...).eq("lances_criticos.partidas.user_id", user_id).range(...).execute()
        client = MagicMock()
        no = client.table.return_value.select.return_value
        no.eq.return_value.range.return_value.execute.return_value = self._resp_vazia()

        fetch_diagnosticos_com_partida(client, "user-a")

        select_arg = client.table.return_value.select.call_args[0][0]
        self.assertIn("lances_criticos!inner", select_arg)
        self.assertIn("partidas!inner", select_arg)
        no.eq.assert_called_once_with("lances_criticos.partidas.user_id", "user-a")


if __name__ == "__main__":
    unittest.main()
