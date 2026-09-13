"""Testes unitários do loop multi-perfil de coletar_partidas_chesscom.py (D-28)."""

import unittest
from unittest.mock import MagicMock, patch

from backend.ingestao.coletar_partidas_chesscom import Settings, coletar_para_perfil


class ColetarParaPerfilTest(unittest.TestCase):
    def _settings(self) -> Settings:
        return Settings(
            supabase_url="https://x.supabase.co",
            supabase_service_role_key="chave",
            months_limit=1,
            user_agent="teste",
        )

    @patch("backend.ingestao.coletar_partidas_chesscom.insert_game")
    @patch("backend.ingestao.coletar_partidas_chesscom.already_exists", return_value=False)
    @patch("backend.ingestao.coletar_partidas_chesscom.fetch_games_from_archives")
    @patch("backend.ingestao.coletar_partidas_chesscom.fetch_archive_urls")
    def test_grava_com_o_user_id_do_perfil(
        self, archive_urls_mock, games_mock, already_exists_mock, insert_mock
    ) -> None:
        archive_urls_mock.return_value = ["https://api.chess.com/pub/player/laisxadrez/games/2026/09"]
        games_mock.return_value = [
            {
                "url": "https://www.chess.com/game/live/1",
                "white": {"username": "laisxadrez", "result": "win"},
                "black": {"username": "oponente", "result": "checkmated"},
                "pgn": "1. e4 e5",
            }
        ]
        client = MagicMock()
        logger = MagicMock()
        settings = self._settings()

        inserted, existing, failed = coletar_para_perfil(
            client, settings, logger, "user-lais", "laisxadrez"
        )

        self.assertEqual((inserted, existing, failed), (1, 0, 0))
        archive_urls_mock.assert_called_once_with(settings, logger, "laisxadrez")
        insert_mock.assert_called_once()
        _record_arg, user_id_arg = insert_mock.call_args[0][1:]
        self.assertEqual(user_id_arg, "user-lais")

    @patch("backend.ingestao.coletar_partidas_chesscom.insert_game")
    @patch("backend.ingestao.coletar_partidas_chesscom.already_exists", return_value=False)
    @patch("backend.ingestao.coletar_partidas_chesscom.fetch_games_from_archives")
    @patch("backend.ingestao.coletar_partidas_chesscom.fetch_archive_urls")
    def test_uma_partida_com_falha_nao_impede_as_demais(
        self, archive_urls_mock, games_mock, already_exists_mock, insert_mock
    ) -> None:
        archive_urls_mock.return_value = ["https://api.chess.com/pub/player/laisxadrez/games/2026/09"]
        games_mock.return_value = [
            {"pgn": "1. e4 e5"},  # sem url/uuid nem white/black -> to_record explode
            {
                "url": "https://www.chess.com/game/live/2",
                "white": {"username": "laisxadrez", "result": "win"},
                "black": {"username": "oponente", "result": "resigned"},
                "pgn": "1. d4 d5",
            },
        ]
        client = MagicMock()

        inserted, existing, failed = coletar_para_perfil(
            client, self._settings(), MagicMock(), "user-lais", "laisxadrez"
        )

        self.assertEqual((inserted, existing, failed), (1, 0, 1))


if __name__ == "__main__":
    unittest.main()
