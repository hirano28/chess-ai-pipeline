"""Testes unitários da montagem de prompt e do schema de revisão de pensamento."""

import json
import logging
import unittest

from pydantic import ValidationError

from backend.agentes.revisar_pensamento import (
    AvaliacaoLance,
    RevisaoRaciocinio,
    build_prompt,
    extrair_lances_san,
    fallback_analise_mestre,
    gerar_revisao,
    lances_faltantes,
)


class BuildPromptLinhaPrincipalTest(unittest.TestCase):
    def test_prompt_inclui_linha_principal_completa(self) -> None:
        avaliacao = AvaliacaoLance(
            lance_jogado="Nb5",
            melhor_lance="Rb1",
            queda_win_percent=9.68,
            linha_principal=["Rb1", "Rxb1+", "Nxb1", "Qb6", "Nc3", "Qxb2"],
        )

        prompt = build_prompt("Achei que Nb5 dava tempo.", avaliacao, "SUBOTIMO")

        self.assertIn("Rb1 Rxb1+ Nxb1 Qb6 Nc3 Qxb2", prompt)
        self.assertIn("linha_principal_do_motor", prompt)
        self.assertIn("analise_mestre", prompt)
        self.assertIn(
            "Baseie sua explicação EXCLUSIVAMENTE na linha fornecida pelo motor",
            prompt,
        )

    def test_prompt_trata_linha_principal_vazia(self) -> None:
        avaliacao = AvaliacaoLance(
            lance_jogado="e4", melhor_lance="e4", queda_win_percent=0.5, linha_principal=[]
        )

        prompt = build_prompt("Abro no centro.", avaliacao, "BOM")

        self.assertIn("linha principal indisponível", prompt)


class RevisaoRaciocinioSchemaTest(unittest.TestCase):
    def test_exige_analise_mestre(self) -> None:
        with self.assertRaises(ValidationError):
            RevisaoRaciocinio(qualidade_raciocinio="SOLIDO", feedback_texto="ok")

    def test_aceita_os_tres_campos(self) -> None:
        revisao = RevisaoRaciocinio(
            qualidade_raciocinio="FALHO",
            feedback_texto="Considere reforçar o cálculo de variantes forçadas.",
            analise_mestre="Um jogador forte jogaria Rb1 para dobrar na coluna aberta.",
        )

        self.assertEqual(revisao.qualidade_raciocinio, "FALHO")
        self.assertTrue(revisao.analise_mestre.startswith("Um jogador forte"))


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def __init__(self, textos: list[str]) -> None:
        self._textos = list(textos)
        self.prompts: list[str] = []

    def generate_content(self, model: str, contents: str) -> _FakeResponse:
        self.prompts.append(contents)
        return _FakeResponse(self._textos.pop(0))


class _FakeGeminiClient:
    def __init__(self, textos: list[str]) -> None:
        self.models = _FakeModels(textos)


def _revisao_json(analise_mestre: str) -> str:
    return json.dumps(
        {
            "qualidade_raciocinio": "SOLIDO",
            "feedback_texto": "Bom cálculo, siga assim.",
            "analise_mestre": analise_mestre,
        }
    )


class ExtrairLancesSanTest(unittest.TestCase):
    def test_extrai_lances_variados(self) -> None:
        texto = "Depois de Rb1 e Nc5, o plano segue com Qe3, O-O e exd5+."
        lances = extrair_lances_san(texto)

        self.assertIn("Rb1", lances)
        self.assertIn("Nc5", lances)
        self.assertIn("Qe3", lances)
        self.assertIn("O-O", lances)
        self.assertIn("exd5+", lances)

    def test_lances_faltantes_detecta_troca(self) -> None:
        analise = "O plano é Rb1 seguido de Qc2 pressionando a coluna."
        faltantes = lances_faltantes(analise, ["Rb1", "Nc5"])

        self.assertEqual(faltantes, ["Nc5"])


class GerarRevisaoValidacaoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("test_revisar_pensamento")
        self.logger.addHandler(logging.NullHandler())
        self.linha_principal = ["Rb1", "Nc5", "Qe3", "Nxa4", "Nxa4", "Rb7"]

    def test_retry_corrige_lance_trocado(self) -> None:
        # 1ª resposta cita "Qc2" (errado); retry cita a linha correta.
        errada = _revisao_json("O plano é Rb1 e depois Qc2 na coluna aberta.")
        certa = _revisao_json("O plano é Rb1 seguido de Nc5 e Qe3.")
        client = _FakeGeminiClient([errada, certa])

        revisao = gerar_revisao(
            client, "PROMPT", self.logger, self.linha_principal
        )

        self.assertEqual(len(client.models.prompts), 2)
        self.assertIn("Rb1", revisao.analise_mestre)
        self.assertIn("Nc5", revisao.analise_mestre)
        self.assertNotIn("Qc2", revisao.analise_mestre)

    def test_fallback_quando_retry_tambem_falha(self) -> None:
        # Ambas as respostas erram; deve cair no fallback não-LLM literal.
        errada = _revisao_json("O plano é Rb1 e depois Qc2 na coluna aberta.")
        ainda_errada = _revisao_json("Continua Rb1 e Qd2, mantendo a pressão.")
        client = _FakeGeminiClient([errada, ainda_errada])

        revisao = gerar_revisao(
            client, "PROMPT", self.logger, self.linha_principal
        )

        self.assertEqual(len(client.models.prompts), 2)
        self.assertEqual(
            revisao.analise_mestre, fallback_analise_mestre(self.linha_principal)
        )
        self.assertIn("Rb1 Nc5 Qe3 Nxa4 Nxa4 Rb7", revisao.analise_mestre)

    def test_sem_retry_quando_linha_ja_citada(self) -> None:
        certa = _revisao_json("O plano é Rb1 seguido de Nc5 pressionando a coluna.")
        client = _FakeGeminiClient([certa])

        revisao = gerar_revisao(
            client, "PROMPT", self.logger, self.linha_principal
        )

        self.assertEqual(len(client.models.prompts), 1)
        self.assertIn("Rb1", revisao.analise_mestre)


if __name__ == "__main__":
    unittest.main()
