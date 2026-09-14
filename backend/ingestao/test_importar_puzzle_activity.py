"""Testes do isolamento por perfil ao importar atividade de puzzles (D-31)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from backend.ingestao.importar_puzzle_activity import (
    resolver_user_id_do_token,
    upsert_puzzle_atividade,
)


def _client_com_perfis(perfis: list[dict]) -> MagicMock:
    client = MagicMock()
    resposta = MagicMock()
    resposta.data = perfis
    client.table.return_value.select.return_value.not_.is_.return_value.execute.return_value = resposta
    return client


class ResolverUserIdDoTokenTest(unittest.TestCase):
    """O user_id gravado é sempre o do perfil dono do LICHESS_STUDY_TOKEN, nunca um default."""

    def test_encontra_o_perfil_pelo_lichess_username_case_insensitive(self) -> None:
        client = _client_com_perfis(
            [
                {"user_id": "user-a", "lichess_username": "TantoFaz123"},
                {"user_id": "user-b", "lichess_username": "outraconta"},
            ]
        )

        user_id = resolver_user_id_do_token(client, "tantofaz123")

        self.assertEqual(user_id, "user-a")

    def test_sem_perfil_correspondente_levanta_erro_em_vez_de_usar_default(self) -> None:
        client = _client_com_perfis([{"user_id": "user-b", "lichess_username": "outraconta"}])

        with self.assertRaises(ValueError):
            resolver_user_id_do_token(client, "tantofaz123")


class UpsertPuzzleAtividadeTest(unittest.TestCase):
    """O user_id gravado é o do perfil resolvido, não um default cego."""

    def test_grava_com_o_user_id_recebido(self) -> None:
        client = MagicMock()
        registro = {"puzzle_id": "abc", "data": "2026-01-01T00:00:00+00:00", "acertou": True, "temas": [], "rating_puzzle": 1500}

        upsert_puzzle_atividade(client, registro, "user-a")

        payload = client.table.return_value.upsert.call_args[0][0]
        self.assertEqual(payload["user_id"], "user-a")
        self.assertEqual(payload["puzzle_id"], "abc")


if __name__ == "__main__":
    unittest.main()
