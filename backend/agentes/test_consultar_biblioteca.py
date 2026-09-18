"""Testes unitários da Biblioteca (busca livre no corpus de livros, D-81)."""

import unittest
from unittest.mock import MagicMock, patch

from backend.agentes.consultar_biblioteca import (
    FonteBiblioteca,
    FonteBibliotecaError,
    PerguntaInvalidaError,
    RespostaBiblioteca,
    buscar_trechos,
    consultar_biblioteca,
    gerar_resposta,
    normalizar_pergunta,
    resposta_de_fallback,
    validar_fontes,
)

TRECHOS = [
    {
        "livro": "Meu Sistema - Aaron Nimzowitsch",
        "capitulo": "Capítulo VII — A Peça Cravada",
        "pagina_aprox": 111,
        "conteudo": "A peça cravada não é, a rigor, uma peça: é um alvo.",
    },
    {
        "livro": "Arte do Ataque no Xadrez",
        "capitulo": "Capítulo 1 — O ataque contra o rei não rocado",
        "pagina_aprox": 18,
        "conteudo": "O rei que não rocou costuma ficar preso no centro.",
    },
]


class NormalizarPerguntaTest(unittest.TestCase):
    def test_rejeita_pergunta_vazia(self) -> None:
        with self.assertRaises(PerguntaInvalidaError):
            normalizar_pergunta("   ")

    def test_rejeita_pergunta_longa_demais(self) -> None:
        with self.assertRaises(PerguntaInvalidaError):
            normalizar_pergunta("a" * 501)

    def test_remove_espacos_das_pontas(self) -> None:
        self.assertEqual(normalizar_pergunta("  o que é cravada?  "), "o que é cravada?")


class ValidarFontesTest(unittest.TestCase):
    def test_aceita_fonte_identica_ao_trecho(self) -> None:
        resposta = RespostaBiblioteca(
            resposta="A cravada imobiliza a peça.",
            fontes=[
                FonteBiblioteca(
                    livro="Meu Sistema - Aaron Nimzowitsch",
                    capitulo="Capítulo VII — A Peça Cravada",
                    pagina_aprox=111,
                )
            ],
        )
        validar_fontes(resposta, TRECHOS)

    def test_aceita_pagina_dentro_da_tolerancia(self) -> None:
        resposta = RespostaBiblioteca(
            resposta="A cravada imobiliza a peça.",
            fontes=[
                FonteBiblioteca(
                    livro="Meu Sistema - Aaron Nimzowitsch",
                    capitulo="Capítulo VII — A Peça Cravada",
                    pagina_aprox=113,
                )
            ],
        )
        validar_fontes(resposta, TRECHOS)

    def test_rejeita_capitulo_de_outro_livro(self) -> None:
        """O risco real: misturar o capítulo de um livro com o nome de outro."""

        resposta = RespostaBiblioteca(
            resposta="...",
            fontes=[
                FonteBiblioteca(
                    livro="Meu Sistema - Aaron Nimzowitsch",
                    capitulo="Capítulo 1 — O ataque contra o rei não rocado",
                    pagina_aprox=111,
                )
            ],
        )
        with self.assertRaises(FonteBibliotecaError):
            validar_fontes(resposta, TRECHOS)

    def test_rejeita_livro_inventado(self) -> None:
        resposta = RespostaBiblioteca(
            resposta="...",
            fontes=[
                FonteBiblioteca(
                    livro="A Lógica do Xadrez Moderno",
                    capitulo="Capítulo 3",
                    pagina_aprox=44,
                )
            ],
        )
        with self.assertRaises(FonteBibliotecaError):
            validar_fontes(resposta, TRECHOS)

    def test_rejeita_pagina_longe_demais(self) -> None:
        resposta = RespostaBiblioteca(
            resposta="...",
            fontes=[
                FonteBiblioteca(
                    livro="Meu Sistema - Aaron Nimzowitsch",
                    capitulo="Capítulo VII — A Peça Cravada",
                    pagina_aprox=140,
                )
            ],
        )
        with self.assertRaises(FonteBibliotecaError):
            validar_fontes(resposta, TRECHOS)


class RespostaDeFallbackTest(unittest.TestCase):
    def test_usa_apenas_dado_real_dos_trechos(self) -> None:
        fallback = resposta_de_fallback(TRECHOS)
        self.assertEqual(len(fallback.fontes), 2)
        self.assertIn("Meu Sistema - Aaron Nimzowitsch", fallback.resposta)
        self.assertIn("pág. 18", fallback.resposta)
        validar_fontes(fallback, TRECHOS)


class GerarRespostaTest(unittest.TestCase):
    def test_cai_no_fallback_quando_o_modelo_erra_duas_vezes(self) -> None:
        """R2: duas citações inválidas seguidas viram dado real formatado."""

        invalida = (
            '{"resposta": "Veja o livro X.", "fontes": '
            '[{"livro": "Livro Que Não Existe", "capitulo": "I", '
            '"pagina_aprox": 5}]}'
        )
        with patch(
            "backend.agentes.consultar_biblioteca.call_gemini",
            side_effect=[invalida, invalida],
        ) as chamada:
            resultado = gerar_resposta(MagicMock(), "o que é cravada?", TRECHOS)

        self.assertEqual(chamada.call_count, 2)
        self.assertNotIn("Livro Que Não Existe", resultado.resposta)
        validar_fontes(resultado, TRECHOS)

    def test_aceita_resposta_valida_na_primeira_tentativa(self) -> None:
        valida = (
            '{"resposta": "A cravada imobiliza.", "fontes": '
            '[{"livro": "Meu Sistema - Aaron Nimzowitsch", '
            '"capitulo": "Capítulo VII — A Peça Cravada", "pagina_aprox": 111}]}'
        )
        with patch(
            "backend.agentes.consultar_biblioteca.call_gemini", return_value=valida
        ) as chamada:
            resultado = gerar_resposta(MagicMock(), "o que é cravada?", TRECHOS)

        self.assertEqual(chamada.call_count, 1)
        self.assertEqual(resultado.resposta, "A cravada imobiliza.")


class BuscarTrechosTest(unittest.TestCase):
    def test_busca_no_corpus_inteiro_sem_filtro_de_livro(self) -> None:
        """A diferença para o Agente 3: aqui nenhum livro é excluído."""

        client = MagicMock()
        client.rpc.return_value.execute.return_value.data = TRECHOS

        trechos = buscar_trechos(client, [0.1] * 768)

        self.assertEqual(trechos, TRECHOS)
        _, parametros = client.rpc.call_args[0]
        self.assertIsNone(parametros["filtro_livros"])
        self.assertIsNone(parametros["filtro_capitulos"])


class ConsultarBibliotecaTest(unittest.TestCase):
    def test_sem_trecho_algum_nao_chama_o_modelo(self) -> None:
        client = MagicMock()
        client.rpc.return_value.execute.return_value.data = []

        with patch(
            "backend.agentes.consultar_biblioteca.gerar_embedding_consulta",
            return_value=[0.1] * 768,
        ), patch("backend.agentes.consultar_biblioteca.call_gemini") as gemini:
            resultado = consultar_biblioteca(client, MagicMock(), "pergunta qualquer")

        gemini.assert_not_called()
        self.assertEqual(resultado["fontes"], [])


if __name__ == "__main__":
    unittest.main()
