"""Testes unitários da validação de referências do agente prescritor."""

import unittest

from backend.agentes.agente3_prescritor import (
    ModuloTreino,
    ReferenciaFonteError,
    SprintTreino,
    validar_referencias_sprint,
)


class ValidarReferenciasSprintTest(unittest.TestCase):
    def test_rejeita_paginas_trocadas_entre_capitulos(self) -> None:
        chunks = [
            {
                "livro": "Meu Sistema",
                "capitulo": "Capítulo VII — A Peça Cravada",
                "pagina_aprox": 111,
            },
            {
                "livro": "Meu Sistema",
                "capitulo": "Capítulo VIII — O Xeque Descoberto",
                "pagina_aprox": 127,
            },
            {"livro": "Meu Sistema", "capitulo": "Capítulo V", "pagina_aprox": 93},
            {"livro": "Meu Sistema", "capitulo": "Capítulo IX", "pagina_aprox": 141},
            {"livro": "Meu Sistema", "capitulo": "Capítulo X", "pagina_aprox": 158},
        ]
        sprint = SprintTreino(
            titulo="Correção tática",
            duracao_total_min=45,
            modulos=[
                ModuloTreino(
                    nome="Teoria",
                    duracao_min=20,
                    conteudo="Estudar a peça cravada.",
                    livro="Meu Sistema",
                    capitulo="Capítulo VIII — O Xeque Descoberto",
                    pagina_aprox=111,
                ),
                ModuloTreino(
                    nome="Prática",
                    duracao_min=25,
                    conteudo="Resolver exercícios.",
                    livro="Meu Sistema",
                    capitulo="Capítulo VII — A Peça Cravada",
                    pagina_aprox=127,
                ),
            ],
        )

        with self.assertRaises(ReferenciaFonteError):
            validar_referencias_sprint(sprint, chunks)


if __name__ == "__main__":
    unittest.main()
