"""Testes unitários da montagem de prompt e do schema de revisão de pensamento."""

import json
import logging
import unittest

from pydantic import ValidationError

from backend.agentes.revisar_pensamento import (
    AvaliacaoLance,
    RevisaoRaciocinio,
    build_prompt,
    candidatos_proximos,
    extrair_lances_san,
    fallback_analise_mestre,
    fallback_top_candidatos,
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
            top_candidatos=[
                {"lance": "Rb1", "avaliacao": "+120"},
                {"lance": "Nc4", "avaliacao": "+40"},
            ],
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

    def test_prompt_inclui_top_candidatos(self) -> None:
        avaliacao = AvaliacaoLance(
            lance_jogado="Nb5",
            melhor_lance="Bxa6",
            queda_win_percent=12.0,
            linha_principal=["Bxa6", "Qxa6", "Nc4"],
            top_candidatos=[
                {"lance": "Bxa6", "avaliacao": "+210"},
                {"lance": "Nc4", "avaliacao": "+150"},
                {"lance": "a4", "avaliacao": "+90"},
            ],
        )

        prompt = build_prompt("Achei Nb5 forte.", avaliacao, "RUIM")

        self.assertIn("top_candidatos_do_motor", prompt)
        self.assertIn("Bxa6 (+210)", prompt)
        self.assertIn("Nc4 (+150)", prompt)
        self.assertIn("a4 (+90)", prompt)
        self.assertIn("NÃO invente candidatos além dos fornecidos", prompt)
        # Diferença 60cp entre 1º e 2º: NÃO é para marcar como opções próximas.
        self.assertNotIn("opções PRÓXIMAS em qualidade", prompt)

    def test_prompt_marca_candidatos_proximos(self) -> None:
        avaliacao = AvaliacaoLance(
            lance_jogado="Nf3",
            melhor_lance="e4",
            queda_win_percent=3.0,
            linha_principal=["e4", "e5", "Nf3"],
            top_candidatos=[
                {"lance": "e4", "avaliacao": "+25"},
                {"lance": "d4", "avaliacao": "+15"},
                {"lance": "Nf3", "avaliacao": "+10"},
            ],
        )

        prompt = build_prompt("Fico entre e4 e d4.", avaliacao, "BOM")

        self.assertIn("opções PRÓXIMAS em qualidade", prompt)
        self.assertIn("única resposta certa", prompt)


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
        # top_candidatos é opcional (default vazio): Gemini não o gera.
        self.assertEqual(revisao.top_candidatos, [])

    def test_aceita_top_candidatos(self) -> None:
        revisao = RevisaoRaciocinio(
            qualidade_raciocinio="SOLIDO",
            feedback_texto="ok",
            analise_mestre="ok",
            top_candidatos=[{"lance": "Rb1", "avaliacao": "+120"}],
        )

        self.assertEqual(revisao.top_candidatos[0]["lance"], "Rb1")


class CandidatosProximosTest(unittest.TestCase):
    def test_diferenca_pequena_e_proxima(self) -> None:
        candidatos = [
            {"lance": "e4", "avaliacao": "+25"},
            {"lance": "d4", "avaliacao": "+10"},
        ]
        self.assertTrue(candidatos_proximos(candidatos))

    def test_diferenca_grande_nao_e_proxima(self) -> None:
        candidatos = [
            {"lance": "Bxa6", "avaliacao": "+210"},
            {"lance": "Nc4", "avaliacao": "+150"},
        ]
        self.assertFalse(candidatos_proximos(candidatos))

    def test_mate_nao_e_tratado_como_proximo(self) -> None:
        candidatos = [
            {"lance": "Qh7", "avaliacao": "M1"},
            {"lance": "Qh8", "avaliacao": "+300"},
        ]
        self.assertFalse(candidatos_proximos(candidatos))

    def test_um_unico_candidato_nao_e_proximo(self) -> None:
        self.assertFalse(candidatos_proximos([{"lance": "e4", "avaliacao": "+25"}]))


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


def _revisao_json(
    analise_mestre: str, feedback_texto: str = "Bom cálculo, siga assim."
) -> str:
    return json.dumps(
        {
            "qualidade_raciocinio": "SOLIDO",
            "feedback_texto": feedback_texto,
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


class GerarRevisaoTopCandidatosTest(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("test_revisar_pensamento")
        self.logger.addHandler(logging.NullHandler())
        self.top_candidatos = [
            {"lance": "Bxa6", "avaliacao": "+210"},
            {"lance": "Nc4", "avaliacao": "+150"},
            {"lance": "a4", "avaliacao": "+90"},
        ]

    def test_injeta_candidatos_reais_na_revisao(self) -> None:
        certa = _revisao_json(
            "Plano com Bxa6.",
            feedback_texto="Os candidatos Bxa6 e Nc4 batem o seu lance.",
        )
        client = _FakeGeminiClient([certa])

        revisao = gerar_revisao(
            client, "PROMPT", self.logger, top_candidatos=self.top_candidatos
        )

        self.assertEqual(len(client.models.prompts), 1)
        self.assertEqual(revisao.top_candidatos, self.top_candidatos)

    def test_retry_corrige_feedback_sem_candidatos(self) -> None:
        # 1ª resposta não cita candidato nenhum; retry cita os dois melhores.
        sem_candidatos = _revisao_json(
            "Plano com Bxa6.", feedback_texto="Seu lance foi impreciso."
        )
        com_candidatos = _revisao_json(
            "Plano com Bxa6.",
            feedback_texto="As opções Bxa6 e Nc4 do motor são mais fortes.",
        )
        client = _FakeGeminiClient([sem_candidatos, com_candidatos])

        revisao = gerar_revisao(
            client, "PROMPT", self.logger, top_candidatos=self.top_candidatos
        )

        self.assertEqual(len(client.models.prompts), 2)
        self.assertIn("Bxa6", revisao.feedback_texto)
        self.assertIn("Nc4", revisao.feedback_texto)
        self.assertEqual(revisao.top_candidatos, self.top_candidatos)

    def test_fallback_quando_retry_tambem_falha(self) -> None:
        sem_candidatos = _revisao_json(
            "Plano com Bxa6.", feedback_texto="Seu lance foi impreciso."
        )
        ainda_sem = _revisao_json(
            "Plano com Bxa6.", feedback_texto="Havia opções melhores."
        )
        client = _FakeGeminiClient([sem_candidatos, ainda_sem])

        revisao = gerar_revisao(
            client, "PROMPT", self.logger, top_candidatos=self.top_candidatos
        )

        self.assertEqual(len(client.models.prompts), 2)
        self.assertEqual(
            revisao.feedback_texto, fallback_top_candidatos(self.top_candidatos)
        )
        self.assertIn("Bxa6 (+210)", revisao.feedback_texto)
        self.assertEqual(revisao.top_candidatos, self.top_candidatos)


if __name__ == "__main__":
    unittest.main()
