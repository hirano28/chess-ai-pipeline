"""Testes da leitura de tokens OAuth do Lichess por usuário (D-33/D-34)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from backend.common.lichess_oauth import (
    obter_access_token_lichess,
    listar_usuarios_com_token_lichess_valido,
)

USER_ID = "11111111-2222-3333-4444-555555555555"


def _resp(data: list) -> MagicMock:
    resposta = MagicMock()
    resposta.data = data
    return resposta


class ObterAccessTokenLichessTest(unittest.TestCase):
    def test_token_valido_e_devolvido(self) -> None:
        client = MagicMock()
        futuro = (datetime.now(timezone.utc) + timedelta(days=300)).isoformat()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = _resp(
            [{"access_token": "token-valido", "expires_at": futuro}]
        )

        token = obter_access_token_lichess(client, USER_ID)

        self.assertEqual(token, "token-valido")

    def test_token_expirado_devolve_none(self) -> None:
        client = MagicMock()
        passado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = _resp(
            [{"access_token": "token-morto", "expires_at": passado}]
        )

        token = obter_access_token_lichess(client, USER_ID)

        self.assertIsNone(token)

    def test_conta_sem_lichess_conectado_devolve_none(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = _resp([])

        token = obter_access_token_lichess(client, USER_ID)

        self.assertIsNone(token)

    def test_filtra_pelo_user_id_certo(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = _resp([])

        obter_access_token_lichess(client, USER_ID)

        client.table.return_value.select.return_value.eq.assert_called_once_with(
            "user_id", USER_ID
        )


class ListarUsuariosComTokenLichessValidoTest(unittest.TestCase):
    def test_filtra_por_expires_at_maior_que_agora(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.gt.return_value.execute.return_value = _resp(
            [{"user_id": USER_ID, "expires_at": "2027-01-01T00:00:00+00:00"}]
        )

        usuarios = listar_usuarios_com_token_lichess_valido(client)

        self.assertEqual(usuarios, [{"user_id": USER_ID, "expires_at": "2027-01-01T00:00:00+00:00"}])
        chamada = client.table.return_value.select.return_value.gt.call_args[0]
        self.assertEqual(chamada[0], "expires_at")

    def test_sem_ninguem_conectado_devolve_lista_vazia(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.gt.return_value.execute.return_value = _resp([])

        usuarios = listar_usuarios_com_token_lichess_valido(client)

        self.assertEqual(usuarios, [])


if __name__ == "__main__":
    unittest.main()
