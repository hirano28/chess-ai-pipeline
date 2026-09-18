"""Testes unitários da validação de referências do agente prescritor."""

import unittest
from unittest.mock import MagicMock

from backend.agentes.agente3_prescritor import (
    ModuloTreino,
    ReferenciaFonteError,
    SprintTreino,
    buscar_conceitos,
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


class BuscarConceitosTest(unittest.TestCase):
    """D-74: conceito sem acento/com underscore precisa ser encontrado."""

    def test_encontra_conceito_sem_acento_e_com_underscore(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.execute.return_value.data = [
            {"id": "1", "conceito": "fraqueza_estrutural_de_peoes"},
            {"id": "2", "conceito": "seguranca_do_rei"},
            {"id": "3", "conceito": "sacrifício de qualidade"},
        ]

        conceitos = buscar_conceitos(client, "TATICA")

        ids = {row["id"] for row in conceitos}
        self.assertIn("2", ids)  # "segurança do rei" bate em "seguranca_do_rei"
        self.assertNotIn("3", ids)  # não tem nenhum termo de TATICA

    def test_categoria_desconhecida_nao_encontra_nada(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.execute.return_value.data = [
            {"id": "1", "conceito": "avaliacao_posicional_incorreta"},
        ]

        conceitos = buscar_conceitos(client, "CATEGORIA_INEXISTENTE")

        self.assertEqual(conceitos, [])

    def test_estrutura_de_peoes_encontra_variantes_reais(self) -> None:
        """D-79: achado em produção — "fraqueza_estrutural_de_peoes" (25
        ocorrências, 4 livros) e "peão da dama isolado" não batiam nos
        termos antigos ("estrutura de peões", "peão isolado")."""
        client = MagicMock()
        client.table.return_value.select.return_value.execute.return_value.data = [
            {"id": "1", "conceito": "fraqueza_estrutural_de_peoes"},
            {"id": "2", "conceito": "transição estrutural de peões"},
            {"id": "3", "conceito": "peão da dama isolado"},
            {"id": "4", "conceito": "peão envenenado"},
        ]

        conceitos = buscar_conceitos(client, "ESTRUTURA_DE_PEOES")

        ids = {row["id"] for row in conceitos}
        self.assertEqual(ids, {"1", "2", "3"})

    def test_nao_duplica_quando_conceito_bate_em_mais_de_um_termo(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.execute.return_value.data = [
            {"id": "1", "conceito": "avaliacao_posicional_incorreta com centro"},
        ]

        conceitos = buscar_conceitos(client, "ESTRATEGIA")

        self.assertEqual(len(conceitos), 1)


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
