"""Testes unitários da montagem de prompt e do schema de revisão de pensamento."""

import json
import logging
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from backend.agentes.revisar_pensamento import (
    CHECKLIST_KEYS,
    AvaliacaoLance,
    RevisaoRaciocinio,
    build_prompt,
    candidatos_proximos,
    carregar_checklist_guia,
    carregar_passos_guia,
    extrair_lances_san,
    fallback_analise_mestre,
    fallback_top_candidatos,
    gerar_revisao,
    lances_faltantes,
)


def _checklist_valido() -> dict[str, str]:
    return {chave: "INDETERMINADO" for chave in CHECKLIST_KEYS}


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
            RevisaoRaciocinio(
                qualidade_raciocinio="SOLIDO",
                feedback_texto="ok",
                checklist_rotina=_checklist_valido(),
            )

    def test_aceita_os_campos_obrigatorios(self) -> None:
        revisao = RevisaoRaciocinio(
            qualidade_raciocinio="FALHO",
            feedback_texto="Considere reforçar o cálculo de variantes forçadas.",
            analise_mestre="Um jogador forte jogaria Rb1 para dobrar na coluna aberta.",
            checklist_rotina=_checklist_valido(),
        )

        self.assertEqual(revisao.qualidade_raciocinio, "FALHO")
        self.assertTrue(revisao.analise_mestre.startswith("Um jogador forte"))
        # top_candidatos é opcional (default vazio): Gemini não o gera.
        self.assertEqual(revisao.top_candidatos, [])

    def test_checklist_exige_as_oito_chaves(self) -> None:
        incompleto = {chave: "SIM" for chave in list(CHECKLIST_KEYS)[:-1]}
        with self.assertRaises(ValidationError):
            RevisaoRaciocinio(
                qualidade_raciocinio="SOLIDO",
                feedback_texto="ok",
                analise_mestre="ok",
                checklist_rotina=incompleto,
            )

    def test_checklist_rejeita_chave_estranha(self) -> None:
        estranho = _checklist_valido()
        estranho.pop("blundercheck")
        estranho["passo_inexistente"] = "SIM"
        with self.assertRaises(ValidationError):
            RevisaoRaciocinio(
                qualidade_raciocinio="SOLIDO",
                feedback_texto="ok",
                analise_mestre="ok",
                checklist_rotina=estranho,
            )

    def test_checklist_rejeita_valor_invalido(self) -> None:
        invalido = _checklist_valido()
        invalido["blundercheck"] = "TALVEZ"
        with self.assertRaises(ValidationError):
            RevisaoRaciocinio(
                qualidade_raciocinio="SOLIDO",
                feedback_texto="ok",
                analise_mestre="ok",
                checklist_rotina=invalido,
            )

    def test_exige_analise_mestre_antigo(self) -> None:
        with self.assertRaises(ValidationError):
            RevisaoRaciocinio(qualidade_raciocinio="SOLIDO", feedback_texto="ok")

    def test_aceita_top_candidatos(self) -> None:
        revisao = RevisaoRaciocinio(
            qualidade_raciocinio="SOLIDO",
            feedback_texto="ok",
            analise_mestre="ok",
            checklist_rotina=_checklist_valido(),
            top_candidatos=[{"lance": "Rb1", "avaliacao": "+120"}],
        )

        self.assertEqual(revisao.top_candidatos[0]["lance"], "Rb1")


class CarregarGuiaTest(unittest.TestCase):
    def test_extrai_oito_passos_do_guia_real(self) -> None:
        passos = carregar_passos_guia()

        self.assertEqual(len(passos), 8)
        self.assertEqual([p["numero"] for p in passos], list(range(1, 9)))
        # Títulos-chave presentes (independente da redação exata).
        titulos = " ".join(p["titulo"].lower() for p in passos)
        self.assertIn("varredura", titulos)
        self.assertIn("blundercheck", titulos)

    def test_parsing_robusto_a_mudanca_de_redacao(self) -> None:
        conteudo = (
            "# Guia\n\nIntro qualquer.\n\n---\n\n"
            "## 1. Primeiro passo reescrito\nCorpo A.\n\n"
            "## 2. Segundo passo diferente\nCorpo B.\n\n"
            "## 3. Terceiro\nCorpo C.\n\n"
            "## 4. Quarto\nCorpo D.\n\n"
            "## 5. Quinto\nCorpo E.\n\n"
            "## 6. Sexto\nCorpo F.\n\n"
            "## 7. Sétimo\nCorpo G.\n\n"
            "## 8. Oitavo\nCorpo H.\n\n"
            "---\n\n## Progressão sugerida\nNão é um passo numerado.\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "guia.md"
            caminho.write_text(conteudo, encoding="utf-8")

            passos = carregar_passos_guia(caminho)

        self.assertEqual(len(passos), 8)
        self.assertEqual(passos[0]["titulo"], "Primeiro passo reescrito")
        self.assertEqual(passos[7]["titulo"], "Oitavo")
        # A seção "## Progressão sugerida" (sem número) não entra e não vaza no
        # corpo do passo 8.
        self.assertNotIn("Progressão", passos[7]["corpo"])

    def test_checklist_pareia_chaves_canonicas_com_passos(self) -> None:
        checklist = carregar_checklist_guia()

        self.assertEqual([c["chave"] for c in checklist], list(CHECKLIST_KEYS))
        self.assertEqual(len(checklist), 8)

    def test_guia_com_numero_errado_de_passos_levanta_erro(self) -> None:
        conteudo = "## 1. Um\nA.\n\n## 2. Dois\nB.\n"
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "guia.md"
            caminho.write_text(conteudo, encoding="utf-8")
            with self.assertRaises(ValueError):
                carregar_checklist_guia(caminho)


class BuildPromptChecklistTest(unittest.TestCase):
    def test_prompt_inclui_rubrica_e_chaves(self) -> None:
        avaliacao = AvaliacaoLance(
            lance_jogado="Nd5",
            melhor_lance="g3",
            queda_win_percent=5.5,
            linha_principal=["g3", "Kd8"],
            top_candidatos=[{"lance": "g3", "avaliacao": "-254"}],
        )

        prompt = build_prompt("Centralizei o cavalo.", avaliacao, "SUBOTIMO")

        self.assertIn("RUBRICA DE ROTINA", prompt)
        self.assertIn("checklist_rotina", prompt)
        self.assertIn("só marque SIM se houver evidência textual", prompt)
        for chave in CHECKLIST_KEYS:
            self.assertIn(chave, prompt)

    def test_prompt_inclui_instrucao_de_causalidade(self) -> None:
        avaliacao = AvaliacaoLance(
            lance_jogado="Nd5",
            melhor_lance="g3",
            queda_win_percent=5.5,
            linha_principal=["g3", "Kd8"],
            top_candidatos=[{"lance": "g3", "avaliacao": "-254"}],
        )

        prompt = build_prompt("Centralizei o cavalo.", avaliacao, "SUBOTIMO")

        self.assertIn("conecte EXPLICITAMENTE", prompt)
        self.assertIn("[candidato real]", prompt)
        self.assertIn("top_candidatos_do_motor REAIS", prompt)
        # Exceção para lance BOM: não força a conexão.
        self.assertIn("Se qualidade_lance for BOM, não force essa conexão", prompt)



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
            "checklist_rotina": _checklist_valido(),
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

    def test_retry_quando_feedback_cita_candidato_inventado(self) -> None:
        # 1ª resposta cita os candidatos reais MAS também inventa "Qd7"; retry limpo.
        inventado = _revisao_json(
            "Plano com Bxa6.",
            feedback_texto="Bxa6 e Nc4 são fortes, e você ignorou Qd7 também.",
        )
        limpo = _revisao_json(
            "Plano com Bxa6.",
            feedback_texto="Os candidatos Bxa6 e Nc4 superam seu lance.",
        )
        client = _FakeGeminiClient([inventado, limpo])

        revisao = gerar_revisao(
            client, "PROMPT", self.logger, top_candidatos=self.top_candidatos
        )

        self.assertEqual(len(client.models.prompts), 2)
        self.assertIn("Bxa6", revisao.feedback_texto)
        self.assertNotIn("Qd7", revisao.feedback_texto)

    def test_fallback_quando_candidato_inventado_persiste(self) -> None:
        inventado = _revisao_json(
            "Plano com Bxa6.",
            feedback_texto="Bxa6 e Nc4 são fortes, mas Qd7 seria melhor.",
        )
        ainda_inventado = _revisao_json(
            "Plano com Bxa6.",
            feedback_texto="Bxa6 e Nc4 são boas, porém Rd8 vencia.",
        )
        client = _FakeGeminiClient([inventado, ainda_inventado])

        revisao = gerar_revisao(
            client, "PROMPT", self.logger, top_candidatos=self.top_candidatos
        )

        self.assertEqual(len(client.models.prompts), 2)
        self.assertEqual(
            revisao.feedback_texto, fallback_top_candidatos(self.top_candidatos)
        )

    def test_lance_jogado_nao_conta_como_inventado(self) -> None:
        # feedback cita o lance jogado (Nb5) além dos candidatos reais: OK, sem retry.
        certa = _revisao_json(
            "Plano com Bxa6.",
            feedback_texto="Seu Nb5 perde tempo; Bxa6 e Nc4 eram superiores.",
        )
        client = _FakeGeminiClient([certa])

        revisao = gerar_revisao(
            client,
            "PROMPT",
            self.logger,
            top_candidatos=self.top_candidatos,
            lance_jogado="Nb5",
        )

        self.assertEqual(len(client.models.prompts), 1)
        self.assertIn("Nb5", revisao.feedback_texto)


if __name__ == "__main__":
    unittest.main()
