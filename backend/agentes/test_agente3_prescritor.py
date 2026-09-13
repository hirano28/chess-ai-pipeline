"""Testes unitários da validação de referências do agente prescritor."""

import unittest
from unittest.mock import MagicMock

from backend.agentes.agente3_prescritor import (
    ModuloTreino,
    ReferenciaFonteError,
    SprintTreino,
    fetch_latest_analysis,
    listar_usuarios_com_analise,
    salvar_sessao,
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


class ListarUsuariosComAnaliseTest(unittest.TestCase):
    """D-28: quem entra no loop de prescrição por usuário."""

    def test_deduplica_e_ignora_user_id_nulo(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.execute.return_value.data = [
            {"user_id": "user-b"},
            {"user_id": "user-a"},
            {"user_id": None},
        ]

        usuarios = listar_usuarios_com_analise(client)

        self.assertEqual(usuarios, ["user-a", "user-b"])


class FetchLatestAnalysisTest(unittest.TestCase):
    """D-28: a sprint de cada usuário parte SÓ do próprio gargalo mais recente."""

    def test_filtra_pelo_dono(self) -> None:
        client = MagicMock()
        chain = client.table.return_value.select.return_value.eq.return_value
        chain.order.return_value.limit.return_value.execute.return_value.data = [
            {"gargalo_sistemico_atual": "TATICA"}
        ]

        resultado = fetch_latest_analysis(client, "user-a")

        client.table.return_value.select.return_value.eq.assert_called_once_with(
            "user_id", "user-a"
        )
        self.assertEqual(resultado, {"gargalo_sistemico_atual": "TATICA"})


class SalvarSessaoTest(unittest.TestCase):
    """D-28: a sprint é gravada com o user_id de quem a recebeu, não um default."""

    def test_grava_com_user_id_explicito(self) -> None:
        client = MagicMock()
        sprint = SprintTreino(titulo="Sprint", duracao_total_min=45, modulos=[])

        salvar_sessao(client, "TATICA", sprint, "user-a")

        payload = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(payload["user_id"], "user-a")


if __name__ == "__main__":
    unittest.main()
