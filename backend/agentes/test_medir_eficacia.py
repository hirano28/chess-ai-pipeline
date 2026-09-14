"""Testes unitários de medição de eficácia das sessões de treino."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from backend.agentes.medir_eficacia import (
    buscar_sessoes_elegiveis,
    calcular_reducao_percentual,
    contar_diagnosticos_categoria,
    extrair_categoria,
    montar_observacao,
    processar_sessao,
)


class CalcularReducaoPercentualTest(unittest.TestCase):
    def test_reducao_positiva(self) -> None:
        self.assertEqual(calcular_reducao_percentual(10, 5), 50.0)

    def test_sem_mudanca(self) -> None:
        self.assertEqual(calcular_reducao_percentual(10, 10), 0.0)

    def test_aumento_de_falhas(self) -> None:
        self.assertEqual(calcular_reducao_percentual(10, 15), -50.0)

    def test_base_zero_retorna_none(self) -> None:
        self.assertIsNone(calcular_reducao_percentual(0, 5))


class ExtrairCategoriaTest(unittest.TestCase):
    def test_categoria_valida(self) -> None:
        self.assertEqual(extrair_categoria("TATICA: cálculo tático deficiente"), "TATICA")
        self.assertEqual(extrair_categoria("  finais : final de torres"), "FINAIS")

    def test_categoria_invalida_lanca_erro(self) -> None:
        with self.assertRaises(ValueError):
            extrair_categoria("CATEGORIA_INEXISTENTE: erro")

    def test_sem_separador_lanca_erro(self) -> None:
        with self.assertRaises(ValueError):
            extrair_categoria("TATICA")


class MontarObservacaoTest(unittest.TestCase):
    def test_observacao_caiu(self) -> None:
        obs = montar_observacao("TATICA", 10, 5, 50.0)
        self.assertIn("caiu", obs)
        self.assertIn("50.0%", obs)

    def test_observacao_subiu(self) -> None:
        obs = montar_observacao("TATICA", 5, 10, -100.0)
        self.assertIn("subiu", obs)

    def test_observacao_permaneceu(self) -> None:
        obs = montar_observacao("TATICA", 5, 5, 0.0)
        self.assertIn("permaneceu", obs)


class BuscarSessoesElegiveisTest(unittest.TestCase):
    def test_select_inclui_user_id(self) -> None:
        client = MagicMock()
        query_mock = client.table.return_value.select.return_value
        query_mock.not_.is_.return_value.is_.return_value.order.return_value.execute.return_value.data = [
            {
                "id": "sess-1",
                "diagnostico_gargalo": "TATICA: cálculo",
                "data_concluida": "2026-09-01T00:00:00Z",
                "user_id": "user-123",
            }
        ]

        sessoes = buscar_sessoes_elegiveis(client)

        client.table.assert_called_with("sessoes_treino")
        select_arg = client.table.return_value.select.call_args[0][0]
        self.assertIn("user_id", select_arg)
        self.assertEqual(len(sessoes), 1)
        self.assertEqual(sessoes[0]["user_id"], "user-123")


class ContarDiagnosticosCategoriaTest(unittest.TestCase):
    def test_filtra_por_user_id_quando_informado(self) -> None:
        client = MagicMock()
        query_chain = (
            client.table.return_value.select.return_value.gte.return_value.lt.return_value
        )
        query_chain.eq.return_value.range.return_value.execute.return_value.data = [
            {"id": "d1", "tags_falha": ["calculo_tatico_deficiente"]},
            {"id": "d2", "tags_falha": ["visao_em_tunel"]},
            {"id": "d3", "tags_falha": ["erro_tecnico_de_final"]},  # não é TATICA
        ]

        inicio = datetime(2026, 8, 1, tzinfo=timezone.utc)
        fim = datetime(2026, 8, 15, tzinfo=timezone.utc)

        total = contar_diagnosticos_categoria(
            client, "TATICA", inicio, fim, user_id="user-xyz"
        )

        select_arg = client.table.return_value.select.call_args[0][0]
        self.assertIn("lances_criticos!inner", select_arg)
        self.assertIn("partidas!inner", select_arg)
        self.assertIn("user_id", select_arg)

        # Confirma que .eq foi chamado com o user_id correto
        query_chain.eq.assert_called_once_with(
            "lances_criticos.partidas.user_id", "user-xyz"
        )
        self.assertEqual(total, 2)

    def test_sem_user_id_nao_chama_eq_de_usuario(self) -> None:
        client = MagicMock()
        query_chain = (
            client.table.return_value.select.return_value.gte.return_value.lt.return_value
        )
        query_chain.range.return_value.execute.return_value.data = []

        inicio = datetime(2026, 8, 1, tzinfo=timezone.utc)
        fim = datetime(2026, 8, 15, tzinfo=timezone.utc)

        total = contar_diagnosticos_categoria(client, "TATICA", inicio, fim)

        query_chain.eq.assert_not_called()
        self.assertEqual(total, 0)


class ProcessarSessaoTest(unittest.TestCase):
    def test_dados_pos_treino_insuficientes(self) -> None:
        client = MagicMock()
        logger = MagicMock()
        sessao = {
            "id": "sess-1",
            "diagnostico_gargalo": "TATICA: cálculo",
            "data_concluida": "2026-09-01T00:00:00Z",
            "user_id": "user-abc",
        }

        # Mock de contar_diagnosticos_categoria: frequencia_antes=5, frequencia_depois=2 (< 3)
        client.table.return_value.select.return_value.gte.return_value.lt.return_value.eq.return_value.range.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "d1", "tags_falha": ["calculo_tatico_deficiente"]}] * 5),
            MagicMock(data=[{"id": "d2", "tags_falha": ["calculo_tatico_deficiente"]}] * 2),
        ]

        resultado = processar_sessao(client, sessao, logger)

        self.assertFalse(resultado)
        client.table("sessoes_treino").update.assert_not_called()

    def test_sucesso_atualiza_sessao_com_eficacia(self) -> None:
        client = MagicMock()
        logger = MagicMock()
        sessao = {
            "id": "sess-1",
            "diagnostico_gargalo": "TATICA: cálculo",
            "data_concluida": "2026-09-01T00:00:00Z",
            "user_id": "user-abc",
        }

        # frequencia_antes = 10, frequencia_depois = 4
        client.table.return_value.select.return_value.gte.return_value.lt.return_value.eq.return_value.range.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "d1", "tags_falha": ["calculo_tatico_deficiente"]}] * 10),
            MagicMock(data=[{"id": "d2", "tags_falha": ["calculo_tatico_deficiente"]}] * 4),
        ]

        resultado = processar_sessao(client, sessao, logger)

        self.assertTrue(resultado)
        update_call = client.table("sessoes_treino").update.call_args[0][0]
        self.assertEqual(update_call["eficacia_medida"], 60.0)
        self.assertIn("caiu de 10 para 4", update_call["observacoes"])


if __name__ == "__main__":
    unittest.main()

