"""Testes unitários do critério de elegibilidade para novas perguntas."""

import unittest
from datetime import date
from unittest.mock import MagicMock

from backend.agentes.gerar_perguntas_pendentes import (
    PERGUNTA_VALIDADE_DIAS,
    data_da_partida,
    dentro_da_validade,
    expirar_perguntas_vencidas,
    selecionar_elegiveis,
)


class SelecionarElegiveisTest(unittest.TestCase):
    def _lance(self, lance_id: str, partida_id: str, numero_lance: int) -> dict:
        return {
            "id": lance_id,
            "partida_id": partida_id,
            "numero_lance": numero_lance,
            "numero_lance_fim": None,
            "lance_notacao": "Nf3",
            "tipo_evento": "PICO",
        }

    def test_partida_com_anotacao_gera_pergunta_para_lance_sem_anotacao(self) -> None:
        lance = self._lance("lance-1", "partida-A", 10)

        elegiveis = selecionar_elegiveis(
            lances=[lance],
            anotadas=set(),
            lance_ids_com_pergunta=set(),
            partidas_com_anotacao={"partida-A"},
        )

        self.assertEqual(elegiveis, [lance])

    def test_partida_sem_nenhuma_anotacao_nao_gera_pergunta(self) -> None:
        lance = self._lance("lance-2", "partida-B", 5)

        elegiveis = selecionar_elegiveis(
            lances=[lance],
            anotadas=set(),
            lance_ids_com_pergunta=set(),
            partidas_com_anotacao=set(),
        )

        self.assertEqual(elegiveis, [])

    def test_lance_com_anotacao_propria_nao_gera_pergunta(self) -> None:
        lance = self._lance("lance-3", "partida-A", 10)

        elegiveis = selecionar_elegiveis(
            lances=[lance],
            anotadas={("partida-A", 10)},
            lance_ids_com_pergunta=set(),
            partidas_com_anotacao={"partida-A"},
        )

        self.assertEqual(elegiveis, [])

    def test_lance_com_pergunta_existente_nao_duplica(self) -> None:
        lance = self._lance("lance-4", "partida-A", 12)

        elegiveis = selecionar_elegiveis(
            lances=[lance],
            anotadas=set(),
            lance_ids_com_pergunta={"lance-4"},
            partidas_com_anotacao={"partida-A"},
        )

        self.assertEqual(elegiveis, [])


class ValidadeDaPerguntaTest(unittest.TestCase):
    """D-64: a pergunta só vale enquanto o jogador ainda lembra do lance.

    Medido em 17/09/2026: 6 perguntas pendentes, todas de partidas de 10 dias
    atrás, nenhuma respondida desde que o recurso existe. Uma pergunta sem
    resposta possível não é tarefa pendente, é entulho que finge ser tarefa.
    """

    HOJE = date(2026, 9, 17)

    def _linha(self, data_partida: str | None) -> dict:
        return {"partidas": {"data_partida": data_partida}}

    def test_le_a_data_com_e_sem_fuso(self) -> None:
        self.assertEqual(
            data_da_partida(self._linha("2026-09-10T14:30:00+00:00")), date(2026, 9, 10)
        )
        self.assertEqual(data_da_partida(self._linha("2026-09-10Z")), date(2026, 9, 10))

    def test_embed_como_lista_tambem_e_lido(self) -> None:
        # PostgREST devolve o embed como lista em algumas formas de select.
        self.assertEqual(
            data_da_partida({"partidas": [{"data_partida": "2026-09-10"}]}),
            date(2026, 9, 10),
        )

    def test_partida_recente_esta_na_validade(self) -> None:
        self.assertTrue(dentro_da_validade(self._linha("2026-09-16"), self.HOJE))

    def test_partida_no_limite_ainda_vale(self) -> None:
        limite = self.HOJE.replace(day=self.HOJE.day - PERGUNTA_VALIDADE_DIAS)
        self.assertTrue(dentro_da_validade(self._linha(limite.isoformat()), self.HOJE))

    def test_partida_velha_demais_perde_a_validade(self) -> None:
        self.assertFalse(dentro_da_validade(self._linha("2026-06-01"), self.HOJE))

    def test_data_ausente_ou_ilegivel_nao_derruba_a_pergunta(self) -> None:
        """Sumir com uma pergunta por causa de um campo que não conseguimos
        ler seria pior que deixar uma pergunta velha na tela."""
        self.assertTrue(dentro_da_validade(self._linha(None), self.HOJE))
        self.assertTrue(dentro_da_validade(self._linha("nao-e-data"), self.HOJE))
        self.assertTrue(dentro_da_validade({}, self.HOJE))


class SelecionarElegiveisComValidadeTest(unittest.TestCase):
    """A mesma régua governa as duas pontas: não gerar, e expirar."""

    def _lance(self, data_partida: str) -> dict:
        return {
            "id": "lance-1",
            "partida_id": "partida-A",
            "numero_lance": 10,
            "numero_lance_fim": None,
            "lance_notacao": "Nf3",
            "tipo_evento": "PICO",
            "partidas": {"data_partida": data_partida},
        }

    def _selecionar(self, lance: dict) -> list:
        return selecionar_elegiveis(
            lances=[lance],
            anotadas=set(),
            lance_ids_com_pergunta=set(),
            partidas_com_anotacao={"partida-A"},
            hoje=date(2026, 9, 17),
        )

    def test_partida_recente_gera_pergunta(self) -> None:
        self.assertEqual(len(self._selecionar(self._lance("2026-09-15"))), 1)

    def test_partida_antiga_nao_gera_pergunta_que_nasceria_morta(self) -> None:
        self.assertEqual(self._selecionar(self._lance("2026-05-01")), [])


class ExpirarPerguntasVencidasTest(unittest.TestCase):
    HOJE = date(2026, 9, 17)

    def _client(self, linhas: list[dict]) -> MagicMock:
        client = MagicMock()
        (
            client.table.return_value.select.return_value.eq.return_value.execute
        ).return_value = MagicMock(data=linhas)
        return client

    def test_expira_so_as_de_partida_velha(self) -> None:
        client = self._client(
            [
                {"id": "p-nova", "lances_criticos": {"partidas": {"data_partida": "2026-09-16"}}},
                {"id": "p-velha", "lances_criticos": {"partidas": {"data_partida": "2026-05-01"}}},
            ]
        )

        expiradas = expirar_perguntas_vencidas(client, MagicMock(), self.HOJE)

        self.assertEqual(expiradas, 1)
        update_mock = client.table.return_value.update
        self.assertEqual(update_mock.call_args[0][0], {"status": "EXPIRADA"})
        # Só a velha entra no filtro do update.
        self.assertEqual(update_mock.return_value.in_.call_args[0][1], ["p-velha"])

    def test_marca_em_vez_de_apagar(self) -> None:
        """EXPIRADA preserva o registro de que a pergunta existiu e não foi
        respondida — que é o dado interessante sobre o recurso."""
        client = self._client(
            [{"id": "p-velha", "lances_criticos": {"partidas": {"data_partida": "2026-01-01"}}}]
        )

        expirar_perguntas_vencidas(client, MagicMock(), self.HOJE)

        client.table.return_value.delete.assert_not_called()

    def test_nada_vencido_nao_toca_no_banco(self) -> None:
        client = self._client(
            [{"id": "p-nova", "lances_criticos": {"partidas": {"data_partida": "2026-09-17"}}}]
        )

        self.assertEqual(expirar_perguntas_vencidas(client, MagicMock(), self.HOJE), 0)
        client.table.return_value.update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
