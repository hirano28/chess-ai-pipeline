"""Testes unitários de backend.ingestao.common_ingestao (D-28)."""

import unittest
from unittest.mock import MagicMock

from backend.ingestao.common_ingestao import carregar_perfis, insert_game


class InsertGameTest(unittest.TestCase):
    """Desde D-28, o dono vem explícito - sem fallback pra um usuário padrão."""

    def test_grava_com_user_id_explicito_do_perfil(self) -> None:
        client = MagicMock()

        insert_game(client, {"external_id": "abc"}, "user-a")

        payload = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(payload["user_id"], "user-a")
        self.assertEqual(payload["external_id"], "abc")


class CarregarPerfisTest(unittest.TestCase):
    def test_filtra_por_coluna_de_username_nao_nula(self) -> None:
        client = MagicMock()
        chain = client.table.return_value.select.return_value.not_.is_
        chain.return_value.execute.return_value.data = [
            {"user_id": "user-a", "lichess_username": "tantofaz123"}
        ]

        perfis = carregar_perfis(client, "lichess_username")

        client.table.assert_called_once_with("perfis_usuario")
        client.table.return_value.select.assert_called_once_with(
            "user_id, lichess_username"
        )
        chain.assert_called_once_with("lichess_username", "null")
        self.assertEqual(perfis, [{"user_id": "user-a", "lichess_username": "tantofaz123"}])

    def test_lista_vazia_quando_sem_dados(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.not_.is_.return_value.execute.return_value.data = None

        perfis = carregar_perfis(client, "chesscom_username")

        self.assertEqual(perfis, [])


if __name__ == "__main__":
    unittest.main()
