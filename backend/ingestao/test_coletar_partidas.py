"""Testes unitários do loop multi-perfil de coletar_partidas.py (D-28)."""

import unittest
from unittest.mock import MagicMock, patch

from backend.ingestao.coletar_partidas import Settings, coletar_para_perfil


class ColetarParaPerfilTest(unittest.TestCase):
    def _settings(self) -> Settings:
        return Settings(
            supabase_url="https://x.supabase.co",
            supabase_service_role_key="chave",
            lichess_token="token",
            limit=20,
        )

    @patch("backend.ingestao.coletar_partidas.insert_game")
    @patch("backend.ingestao.coletar_partidas.already_exists", return_value=False)
    @patch("backend.ingestao.coletar_partidas.fetch_games")
    def test_grava_com_o_user_id_do_perfil(
        self, fetch_mock, already_exists_mock, insert_mock
    ) -> None:
        fetch_mock.return_value = [
            {
                "id": "jogo-1",
                "players": {"white": {"user": {"name": "laisxadrez"}}, "black": {}},
                "winner": "white",
                "moves": "e4 e5",
            }
        ]
        client = MagicMock()
        logger = MagicMock()
        settings = self._settings()

        inserted, existing, failed = coletar_para_perfil(
            client, settings, logger, "user-lais", "laisxadrez"
        )

        self.assertEqual((inserted, existing, failed), (1, 0, 0))
        fetch_mock.assert_called_once_with(settings, logger, "laisxadrez")
        insert_mock.assert_called_once()
        _record_arg, user_id_arg = insert_mock.call_args[0][1:]
        self.assertEqual(user_id_arg, "user-lais")

    @patch("backend.ingestao.coletar_partidas.insert_game")
    @patch("backend.ingestao.coletar_partidas.already_exists", return_value=False)
    @patch("backend.ingestao.coletar_partidas.fetch_games")
    def test_uma_partida_com_falha_nao_impede_as_demais(
        self, fetch_mock, already_exists_mock, insert_mock
    ) -> None:
        fetch_mock.return_value = [
            {},  # sem "id" -> game["id"] explode antes de chegar em to_record
            {
                "id": "jogo-2",
                "players": {"white": {"user": {"name": "laisxadrez"}}, "black": {}},
                "winner": "white",
                "moves": "e4 e5",
            },
        ]
        client = MagicMock()

        inserted, existing, failed = coletar_para_perfil(
            client, self._settings(), MagicMock(), "user-lais", "laisxadrez"
        )

        self.assertEqual((inserted, existing, failed), (1, 0, 1))


if __name__ == "__main__":
    unittest.main()
