"""Testes unitários da montagem de prompts do agente linter."""

import unittest

from backend.agentes.agente1_linter import (
    DiagnosticoLance,
    assegurar_tag_apuro_de_tempo,
    build_prompt,
    montar_prompt,
    montar_thought_note,
)

PGN = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5"


class MontarPromptTest(unittest.TestCase):
    def _lance(self, tipo_evento: str) -> dict:
        return {
            "id": 1,
            "tipo_evento": tipo_evento,
            "numero_lance": 2,
            "numero_lance_fim": 5,
            "lance_notacao": "Nf3",
            "avaliacao_antes_cp": 30,
            "avaliacao_depois_cp": -120,
            "queda_win_percent": 18.5,
        }

    def _partida(self) -> dict:
        return {"id": 10, "pgn": PGN, "cor_jogada": "BRANCAS"}

    def test_pico_e_erosao_geram_prompts_diferentes(self) -> None:
        pico = montar_prompt(self._lance("PICO"), self._partida())
        erosao = montar_prompt(self._lance("EROSAO"), self._partida())

        self.assertNotEqual(pico, erosao)

    def test_prompt_erosao_menciona_janela_e_sequencia(self) -> None:
        erosao = montar_prompt(self._lance("EROSAO"), self._partida())

        self.assertIn("EROSÃO ESTRATÉGICA", erosao)
        self.assertIn("[2, 5]", erosao)
        self.assertIn("Brancas", erosao)
        # Apenas os lances das brancas dentro de [2, 5] devem aparecer.
        self.assertIn("2. Nf3", erosao)
        self.assertIn("5. O-O", erosao)
        # Lance das brancas fora da janela não deve ser incluído.
        self.assertNotIn("Re1", erosao)

    def test_prompt_pico_permanece_sem_referencia_a_erosao(self) -> None:
        pico = montar_prompt(self._lance("PICO"), self._partida())

        self.assertNotIn("EROSÃO ESTRATÉGICA", pico)
        self.assertIn("lance_notacao", pico)


class ApuroDeTempoNoPromptTest(unittest.TestCase):
    def _lance_pico(self, **tempo_kwargs: object) -> dict:
        lance = {
            "id": 2,
            "tipo_evento": "PICO",
            "numero_lance": 2,
            "lance_notacao": "Nf3",
            "avaliacao_antes_cp": 30,
            "avaliacao_depois_cp": -120,
        }
        lance.update(tempo_kwargs)
        return lance

    def _partida(self) -> dict:
        return {"id": 10, "pgn": PGN, "cor_jogada": "BRANCAS"}

    def test_menciona_apuro_quando_tempo_restante_abaixo_do_limiar(self) -> None:
        lance = self._lance_pico(tempo_restante_seg=10.0, tempo_gasto_seg=5.0)

        prompt = montar_prompt(lance, self._partida(), limiar_apuro_tempo_seg=15.0)

        self.assertIn("apuro_de_tempo", prompt)
        self.assertIn("gestao_de_tempo_ruim", prompt)
        self.assertIn("10.0s", prompt)

    def test_menciona_apuro_quando_lance_muito_rapido_com_pouco_tempo(self) -> None:
        # Não abaixo do limiar principal (15s), mas <=30s restantes e <=2s gastos.
        lance = self._lance_pico(tempo_restante_seg=25.0, tempo_gasto_seg=1.0)

        prompt = montar_prompt(lance, self._partida(), limiar_apuro_tempo_seg=15.0)

        self.assertIn("apuro_de_tempo", prompt)

    def test_nao_menciona_tempo_quando_confortavel(self) -> None:
        lance_com_tempo = self._lance_pico(tempo_restante_seg=120.0, tempo_gasto_seg=30.0)
        lance_sem_tempo = self._lance_pico()

        prompt_com_tempo = montar_prompt(
            lance_com_tempo, self._partida(), limiar_apuro_tempo_seg=15.0
        )
        prompt_sem_tempo = montar_prompt(
            lance_sem_tempo, self._partida(), limiar_apuro_tempo_seg=15.0
        )

        self.assertNotIn("apuro_de_tempo", prompt_com_tempo)
        self.assertNotIn("apuro_de_tempo", prompt_sem_tempo)
        # Comportamento atual preservado: prompt idêntico ao build_prompt sem nota.
        context = "1. e4 e5"
        self.assertEqual(
            build_prompt(lance_sem_tempo, context),
            build_prompt(lance_sem_tempo, context, ""),
        )


class AssegurarTagApuroTempoTest(unittest.TestCase):
    def _criar_diagnostico(self, tags: list[str]) -> DiagnosticoLance:
        return DiagnosticoLance(
            fase_do_jogo="MEIO_JOGO",
            tags_falha=tags,  # type: ignore[arg-type]
            tipo_erro="INDETERMINADO",
            diagnostico_mecanico="Erro mecânico",
            raiz_conceitual_violada="Princípio violado",
            refinamento_pos_revisao="Refinamento",
            acao_corretiva_sugerida="Ação corretiva",
            confianca_diagnostico="ALTA",
        )

    def test_inclui_gestao_tempo_quando_em_apuro(self) -> None:
        diag = self._criar_diagnostico(["calculo_tatico_deficiente"])
        lance = {"tempo_restante_seg": 10.0, "tempo_gasto_seg": 2.0}

        resultado = assegurar_tag_apuro_de_tempo(diag, lance, limiar_seg=15.0)

        self.assertIn("gestao_de_tempo_ruim", resultado.tags_falha)
        self.assertIn("calculo_tatico_deficiente", resultado.tags_falha)

    def test_substitui_terceira_tag_quando_ja_atingiu_limite_de_tres(self) -> None:
        diag = self._criar_diagnostico(
            ["calculo_tatico_deficiente", "seguranca_do_rei", "visao_em_tunel"]
        )
        lance = {"tempo_restante_seg": 8.0, "tempo_gasto_seg": 3.0}

        resultado = assegurar_tag_apuro_de_tempo(diag, lance, limiar_seg=15.0)

        self.assertEqual(len(resultado.tags_falha), 3)
        self.assertIn("gestao_de_tempo_ruim", resultado.tags_falha)

    def test_nao_altera_quando_fora_de_apuro(self) -> None:
        diag = self._criar_diagnostico(["calculo_tatico_deficiente"])
        lance = {"tempo_restante_seg": 120.0, "tempo_gasto_seg": 15.0}

        resultado = assegurar_tag_apuro_de_tempo(diag, lance, limiar_seg=15.0)

        self.assertEqual(resultado.tags_falha, ["calculo_tatico_deficiente"])


class ThoughtNoteTest(unittest.TestCase):
    def test_montar_thought_note_com_anotacao(self) -> None:
        lance = {"texto_pensamento": "Achei que ele jogaria d5"}
        note = montar_thought_note(lance)

        self.assertIn("Achei que ele jogaria d5", note)
        self.assertIn("PROCESSO", note)
        self.assertIn("CONTEUDO", note)

    def test_montar_thought_note_sem_anotacao(self) -> None:
        lance = {}
        note = montar_thought_note(lance)

        self.assertIn("Nenhuma anotação registrada", note)
        self.assertIn("INDETERMINADO", note)

    def test_diagnostico_lance_valida_tipo_erro(self) -> None:
        diag = DiagnosticoLance(
            fase_do_jogo="FINAL",
            tags_falha=["erro_tecnico_de_final"],
            tipo_erro="PROCESSO",
            diagnostico_mecanico="Final de peões",
            raiz_conceitual_violada="Oposição",
            refinamento_pos_revisao="Regra do quadrado",
            acao_corretiva_sugerida="Calcular oposição",
            confianca_diagnostico="ALTA",
        )
        self.assertEqual(diag.tipo_erro, "PROCESSO")


if __name__ == "__main__":
    unittest.main()

