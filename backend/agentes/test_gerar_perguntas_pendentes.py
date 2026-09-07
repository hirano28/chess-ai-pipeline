"""Testes unitários do critério de elegibilidade para novas perguntas."""

import unittest

from backend.agentes.gerar_perguntas_pendentes import selecionar_elegiveis


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


if __name__ == "__main__":
    unittest.main()
