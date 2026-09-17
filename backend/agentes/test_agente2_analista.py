"""Testes unitários para backend.agentes.agente2_analista."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd

from backend.agentes.agente2_analista import (
    CADENCIA_MIN_PARTIDAS,
    CATEGORY_MIN_DIAGNOSTICS,
    HEXAGON_CATEGORIES,
    RECENT_WINDOW_DAYS,
    TAGS_VOCABULARY,
    _identify_bottleneck,
    analisar_usuario,
    build_dataframe,
    build_prompt,
    calcular_metricas_completas,
    calcular_metricas_hexagono,
    calcular_metricas_por_cadencia,
    fetch_diagnosticos,
    listar_usuarios_com_partidas,
    salvar_analise,
)


def _make_row(
    tags: list[str],
    queda_win_percent: float = 10.0,
    data_partida: str | None = None,
    eco: str | None = None,
    diag_id: int = 1,
    cadencia: str | None = None,
    partida_id: str | None = None,
) -> dict:
    """Helper que cria um registro no formato retornado por fetch_diagnosticos."""
    return {
        "id": diag_id,
        "tags_falha": tags,
        "lances_criticos": {
            "queda_win_percent": queda_win_percent,
            "numero_lance": 15,
            "partida_id": partida_id,
            "partidas": {
                "data_partida": data_partida or datetime.now(timezone.utc).isoformat(),
                "eco_abertura": eco,
                "cadencia": cadencia,
            },
        },
    }


class TestBuildDataframe(unittest.TestCase):
    """Verifica que build_dataframe extrai queda_win_percent corretamente."""

    def test_extrai_queda_win_percent(self):
        rows = [_make_row(["perda_de_material"], queda_win_percent=25.5)]
        df = build_dataframe(rows)
        self.assertIn("queda_win_percent", df.columns)
        self.assertNotIn("gravidade_cpl", df.columns)
        self.assertEqual(df.iloc[0]["queda_win_percent"], 25.5)

    def test_tags_filtradas_por_vocabulario(self):
        rows = [_make_row(["perda_de_material", "tag_falsa"])]
        df = build_dataframe(rows)
        self.assertEqual(df.iloc[0]["tags_falha"], ["perda_de_material"])


class TestCalcularMetricasHexagono(unittest.TestCase):
    """Testes de calcular_metricas_hexagono com foco na janela recente."""

    def _build_df_with_dates(
        self, old_tags: list[str], recent_tags: list[str]
    ) -> pd.DataFrame:
        """Constrói DataFrame com diagnósticos antigos e recentes."""
        old_date = (
            datetime.now(timezone.utc) - timedelta(days=RECENT_WINDOW_DAYS + 30)
        ).isoformat()
        recent_date = (
            datetime.now(timezone.utc) - timedelta(days=5)
        ).isoformat()

        rows = []
        for i, tag in enumerate(old_tags):
            rows.append(
                _make_row([tag], queda_win_percent=20.0, data_partida=old_date, diag_id=i)
            )
        for i, tag in enumerate(recent_tags, start=len(old_tags)):
            rows.append(
                _make_row([tag], queda_win_percent=15.0, data_partida=recent_date, diag_id=i)
            )
        return build_dataframe(rows)

    def test_metricas_cumulativas_incluem_todo_historico(self):
        """frequencia_por_categoria deve contar TUDO."""
        old_tags = ["calculo_tatico_deficiente"] * 10
        recent_tags = ["erro_tecnico_de_final"] * 6
        df = self._build_df_with_dates(old_tags, recent_tags)
        metrics = calcular_metricas_hexagono(df)

        self.assertEqual(metrics["frequencia_por_categoria"]["TATICA"], 10)
        self.assertEqual(metrics["frequencia_por_categoria"]["FINAIS"], 6)

    def test_metricas_recentes_excluem_historico_antigo(self):
        """frequencia_por_categoria_recente deve contar só os últimos 30 dias."""
        old_tags = ["calculo_tatico_deficiente"] * 10
        recent_tags = ["erro_tecnico_de_final"] * 6
        df = self._build_df_with_dates(old_tags, recent_tags)
        metrics = calcular_metricas_hexagono(df)

        self.assertEqual(metrics["frequencia_por_categoria_recente"]["TATICA"], 0)
        self.assertEqual(metrics["frequencia_por_categoria_recente"]["FINAIS"], 6)

    def test_top_3_tags_usa_contagens_recentes(self):
        """top_3_tags deve refletir a janela recente, não o acumulado."""
        old_tags = ["calculo_tatico_deficiente"] * 20
        recent_tags = ["erro_tecnico_de_final"] * 8 + ["seguranca_do_rei"] * 5
        df = self._build_df_with_dates(old_tags, recent_tags)
        metrics = calcular_metricas_hexagono(df)

        top_tags = [item["tag"] for item in metrics["top_3_tags"]]
        self.assertEqual(top_tags[0], "erro_tecnico_de_final")
        self.assertNotIn("calculo_tatico_deficiente", top_tags)

    def test_gravidade_usa_queda_win_percent(self):
        """A gravidade média por tag deve usar queda_win_percent."""
        recent_date = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        rows = [
            _make_row(["perda_de_material"], queda_win_percent=30.0, data_partida=recent_date, diag_id=1),
            _make_row(["perda_de_material"], queda_win_percent=10.0, data_partida=recent_date, diag_id=2),
        ]
        df = build_dataframe(rows)
        metrics = calcular_metricas_hexagono(df)

        self.assertAlmostEqual(
            metrics["gravidade_media_por_tag"]["perda_de_material"], 20.0
        )

    def test_dataframe_vazio(self):
        """Com zero diagnósticos, todas as métricas ficam zeradas."""
        df = pd.DataFrame(
            columns=[
                "diagnostico_id", "tags_falha", "queda_win_percent",
                "numero_lance", "data_partida", "eco_abertura",
            ]
        )
        metrics = calcular_metricas_hexagono(df)
        self.assertEqual(metrics["total_diagnosticos"], 0)
        self.assertIsNone(metrics["gargalo_sistemico_atual"])
        self.assertEqual(metrics["top_3_tags"], [])


class TestMetricasPorCadencia(unittest.TestCase):
    """D-63: o Hexágono ganha um recorte por cadência dentro do mesmo jsonb."""

    def _df(self) -> pd.DataFrame:
        recente = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        rows = []
        # BLITZ: 3 partidas, 6 diagnósticos de tática.
        for i in range(6):
            rows.append(
                _make_row(
                    ["calculo_tatico_deficiente"], data_partida=recente, diag_id=i,
                    cadencia="BLITZ", partida_id=f"blitz-{i % 3}",
                )
            )
        # RAPIDA: 3 partidas, 6 diagnósticos de finais — gargalo DIFERENTE.
        for i in range(6, 12):
            rows.append(
                _make_row(
                    ["erro_tecnico_de_final"], data_partida=recente, diag_id=i,
                    cadencia="RAPIDA", partida_id=f"rapida-{i % 3}",
                )
            )
        # Sem cadência: conta no total, em bloco nenhum.
        rows.append(
            _make_row(
                ["perda_de_material"], data_partida=recente, diag_id=99,
                cadencia=None, partida_id="manual-1",
            )
        )
        return build_dataframe(rows)

    def test_cada_cadencia_tem_o_proprio_gargalo(self):
        """É a razão de o recorte existir: o gargalo pode ser outro por cadência."""
        metrics = calcular_metricas_completas(self._df())

        self.assertEqual(
            metrics["por_cadencia"]["BLITZ"]["gargalo_sistemico_atual"], "TATICA"
        )
        self.assertEqual(
            metrics["por_cadencia"]["RAPIDA"]["gargalo_sistemico_atual"], "FINAIS"
        )

    def test_o_total_continua_somando_tudo_inclusive_sem_cadencia(self):
        metrics = calcular_metricas_completas(self._df())

        self.assertEqual(metrics["total_diagnosticos"], 13)
        # 6 de cálculo tático + 1 de perda de material, ambas TATICA.
        self.assertEqual(metrics["frequencia_por_categoria"]["TATICA"], 7)
        self.assertEqual(sorted(metrics["por_cadencia"]), ["BLITZ", "RAPIDA"])

    def test_conta_partidas_distintas_e_nao_diagnosticos(self):
        metrics = calcular_metricas_completas(self._df())

        self.assertEqual(metrics["partidas_distintas"], 7)
        self.assertEqual(metrics["por_cadencia"]["BLITZ"]["partidas_distintas"], 3)

    def test_bloco_tem_o_mesmo_shape_do_total_menos_a_frequencia_por_eco(self):
        """A tela reaproveita o render do total para qualquer recorte."""
        metrics = calcular_metricas_completas(self._df())
        bloco = metrics["por_cadencia"]["BLITZ"]

        for chave in ("frequencia_por_categoria", "frequencia_por_categoria_recente",
                      "gravidade_media_por_categoria", "gargalo_sistemico_atual",
                      "total_diagnosticos"):
            self.assertIn(chave, bloco)
        self.assertNotIn("frequencia_tags_por_eco", bloco)

    def test_cadencia_com_poucas_partidas_nao_ganha_bloco(self):
        """Um PGN colado à mão não pode virar chip permanente no seletor."""
        recente = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        rows = [
            _make_row(["erro_tecnico_de_final"], data_partida=recente, diag_id=i,
                      cadencia="CLASSICA", partida_id="classica-unica")
            for i in range(5)
        ]
        rows += [
            _make_row(["calculo_tatico_deficiente"], data_partida=recente, diag_id=10 + i,
                      cadencia="BLITZ", partida_id=f"blitz-{i}")
            for i in range(CADENCIA_MIN_PARTIDAS)
        ]

        por_cadencia = calcular_metricas_por_cadencia(build_dataframe(rows))

        self.assertNotIn("CLASSICA", por_cadencia)
        self.assertIn("BLITZ", por_cadencia)

    def test_o_gargalo_de_primeiro_nivel_segue_sendo_o_de_todas_as_partidas(self):
        """O Agente 3 e a medição de eficácia leem este; o recorte só informa."""
        metrics = calcular_metricas_completas(self._df())

        # 7 TATICA contra 6 FINAIS, mesma gravidade: TATICA no conjunto.
        self.assertEqual(metrics["gargalo_sistemico_atual"], "TATICA")

    def test_prompt_traz_o_gargalo_por_cadencia_e_pede_para_comparar(self):
        metrics = calcular_metricas_completas(self._df())

        prompt = build_prompt(metrics)

        self.assertIn('"BLITZ": "TATICA"', prompt)
        self.assertIn('"RAPIDA": "FINAIS"', prompt)
        self.assertIn("pressão de relógio", prompt)

    def test_prompt_tolera_metricas_antigas_sem_recorte(self):
        """As 5 análises gravadas antes do D-63 não têm `por_cadencia`."""
        metrics = calcular_metricas_hexagono(self._df())

        prompt = build_prompt(metrics)

        self.assertIn('"gargalo_por_cadencia": {}', prompt)

    def test_dataframe_vazio_devolve_recorte_vazio(self):
        self.assertEqual(calcular_metricas_por_cadencia(build_dataframe([])), {})


class TestIdentifyBottleneck(unittest.TestCase):
    """Testes de _identify_bottleneck usando métricas recentes."""

    def test_gargalo_recente_difere_do_cumulativo(self):
        """Cenário central de P-3: TATICA domina o acumulado, FINAIS domina o recente."""
        metrics = {
            # Cumulativo: TATICA tem 200, FINAIS tem 50
            "frequencia_por_categoria": {"TATICA": 200, "FINAIS": 50, **{
                c: 0 for c in HEXAGON_CATEGORIES if c not in ("TATICA", "FINAIS")
            }},
            "gravidade_media_por_categoria": {"TATICA": 15.0, "FINAIS": 12.0, **{
                c: None for c in HEXAGON_CATEGORIES if c not in ("TATICA", "FINAIS")
            }},
            # Recente: FINAIS tem 20, TATICA tem 3 (abaixo do mínimo)
            "frequencia_por_categoria_recente": {"FINAIS": 20, "TATICA": 3, **{
                c: 0 for c in HEXAGON_CATEGORIES if c not in ("TATICA", "FINAIS")
            }},
            "gravidade_media_por_categoria_recente": {"FINAIS": 18.0, "TATICA": 5.0, **{
                c: None for c in HEXAGON_CATEGORIES if c not in ("TATICA", "FINAIS")
            }},
        }
        result = _identify_bottleneck(metrics)
        self.assertEqual(result, "FINAIS")

    def test_nenhuma_categoria_elegivel_retorna_none(self):
        """Quando nenhuma categoria recente atinge o mínimo, retorna None."""
        metrics = {
            "frequencia_por_categoria_recente": {c: 0 for c in HEXAGON_CATEGORIES},
            "gravidade_media_por_categoria_recente": {c: None for c in HEXAGON_CATEGORIES},
        }
        result = _identify_bottleneck(metrics)
        self.assertIsNone(result)

    def test_empate_de_frequencia_desempata_por_gravidade(self):
        """Com mesma frequência, a maior gravidade ganha."""
        n = CATEGORY_MIN_DIAGNOSTICS + 5
        metrics = {
            "frequencia_por_categoria_recente": {
                "TATICA": n, "FINAIS": n,
                **{c: 0 for c in HEXAGON_CATEGORIES if c not in ("TATICA", "FINAIS")}
            },
            "gravidade_media_por_categoria_recente": {
                "TATICA": 10.0, "FINAIS": 25.0,
                **{c: None for c in HEXAGON_CATEGORIES if c not in ("TATICA", "FINAIS")}
            },
        }
        result = _identify_bottleneck(metrics)
        self.assertEqual(result, "FINAIS")


class TestBuildPrompt(unittest.TestCase):
    """Verifica que o prompt inclui contexto temporal."""

    def test_prompt_inclui_janela_recente(self):
        metrics = {
            "total_diagnosticos": 100,
            "top_3_tags": [],
            "frequencia_por_categoria": {c: 0 for c in HEXAGON_CATEGORIES},
            "frequencia_por_categoria_recente": {c: 0 for c in HEXAGON_CATEGORIES},
            "gravidade_media_por_categoria_recente": {c: None for c in HEXAGON_CATEGORIES},
            "gargalo_sistemico_atual": "TATICA",
        }
        prompt = build_prompt(metrics)
        self.assertIn(str(RECENT_WINDOW_DAYS), prompt)
        self.assertIn("recente", prompt.lower())
        self.assertIn("frequencia_por_categoria_recente", prompt)


class ListarUsuariosComPartidasTest(unittest.TestCase):
    """D-28: quem entra no loop de análise por usuário."""

    def test_deduplica_e_ignora_user_id_nulo(self):
        client = MagicMock()
        client.table.return_value.select.return_value.execute.return_value.data = [
            {"user_id": "user-b"},
            {"user_id": "user-a"},
            {"user_id": "user-a"},
            {"user_id": None},
        ]

        usuarios = listar_usuarios_com_partidas(client)

        self.assertEqual(usuarios, ["user-a", "user-b"])


class FetchDiagnosticosTest(unittest.TestCase):
    """D-28: o filtro por dono precisa usar !inner nos dois embeds."""

    def test_filtra_pelo_dono_via_join_aninhado(self):
        client = MagicMock()
        execute_mock = client.table.return_value.select.return_value.eq.return_value.range.return_value.execute
        execute_mock.return_value.data = []

        fetch_diagnosticos(client, MagicMock(), "user-a")

        select_arg = client.table.return_value.select.call_args[0][0]
        self.assertIn("lances_criticos!inner", select_arg)
        self.assertIn("partidas!inner", select_arg)
        client.table.return_value.select.return_value.eq.assert_called_once_with(
            "lances_criticos.partidas.user_id", "user-a"
        )


class SalvarAnaliseTest(unittest.TestCase):
    """D-28: a análise é gravada com o user_id de quem foi analisado, não um default."""

    def test_grava_com_user_id_explicito(self):
        client = MagicMock()
        metrics = {"gargalo_sistemico_atual": "TATICA"}

        salvar_analise(client, metrics, "uma narrativa", "user-a")

        payload = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(payload["user_id"], "user-a")


class AnalisarUsuarioTest(unittest.TestCase):
    """D-28: um usuário sem diagnósticos ainda não deve gerar narrativa nem gravar nada."""

    @patch("backend.agentes.agente2_analista.salvar_analise")
    @patch("backend.agentes.agente2_analista.gerar_narrativa")
    @patch("backend.agentes.agente2_analista.fetch_diagnosticos")
    def test_pula_narrativa_e_gravacao_sem_diagnosticos(
        self, fetch_mock, narrativa_mock, salvar_mock
    ):
        fetch_mock.return_value = []

        metrics = analisar_usuario(MagicMock(), MagicMock(), MagicMock(), "user-a")

        self.assertEqual(metrics["total_diagnosticos"], 0)
        narrativa_mock.assert_not_called()
        salvar_mock.assert_not_called()

    @patch("backend.agentes.agente2_analista.salvar_analise")
    @patch("backend.agentes.agente2_analista.gerar_narrativa")
    @patch("backend.agentes.agente2_analista.fetch_diagnosticos")
    def test_gera_narrativa_e_grava_quando_ha_diagnosticos(
        self, fetch_mock, narrativa_mock, salvar_mock
    ):
        fetch_mock.return_value = [
            {
                "id": 1,
                "tags_falha": ["perda_de_material"],
                "lances_criticos": {
                    "queda_win_percent": 20.0,
                    "numero_lance": 10,
                    "partidas": {
                        "data_partida": datetime.now(timezone.utc).isoformat(),
                        "eco_abertura": None,
                    },
                },
            }
        ]
        narrativa_mock.return_value = "narrativa gerada"

        analisar_usuario(MagicMock(), MagicMock(), MagicMock(), "user-a")

        narrativa_mock.assert_called_once()
        salvar_mock.assert_called_once()
        self.assertEqual(salvar_mock.call_args[0][3], "user-a")


if __name__ == "__main__":
    unittest.main()
