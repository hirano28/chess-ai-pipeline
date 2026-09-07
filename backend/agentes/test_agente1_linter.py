"""Testes unitários da montagem de prompts do agente linter."""

import unittest

from backend.agentes.agente1_linter import build_prompt, montar_prompt

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


if __name__ == "__main__":
    unittest.main()
