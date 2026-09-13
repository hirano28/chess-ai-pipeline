"""Testes do agrupamento de aberturas por família e da extração por plataforma."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.agentes.normalizar_aberturas import (
    SEM_NOME,
    atualizar_abertura,
    extrair_nome_de_ecourl,
    extrair_nome_do_pgn,
    normalizar_abertura,
    resolver_nome_abertura,
)


class NormalizarAberturaTest(unittest.TestCase):
    """O dicionário de famílias precisa reconhecer os nomes mais comuns."""

    def test_reconhece_sistema_londres(self) -> None:
        self.assertEqual(
            normalizar_abertura("Queen's Pawn Game: London System, with e6"),
            "Sistema Londres",
        )

    def test_reconhece_italiana_via_giuoco_piano(self) -> None:
        self.assertEqual(
            normalizar_abertura("Giuoco Piano Game Giuoco Pianissimo Variation"),
            "Italiana",
        )

    def test_reconhece_espanhola_via_ruy_lopez(self) -> None:
        self.assertEqual(normalizar_abertura("Ruy Lopez: Morphy Defense"), "Espanhola")

    def test_reconhece_siciliana(self) -> None:
        self.assertEqual(
            normalizar_abertura("Sicilian Defense Open Dragon Main Line"), "Siciliana"
        )

    def test_reconhece_francesa(self) -> None:
        self.assertEqual(
            normalizar_abertura("French Defense Exchange Variation"), "Francesa"
        )

    def test_gambito_da_dama_nao_colide_com_peao_de_dama(self) -> None:
        self.assertEqual(
            normalizar_abertura("Queens Gambit Declined Chigorin Janowski Variation"),
            "Gambito da Dama",
        )
        self.assertEqual(
            normalizar_abertura("Queens Pawn Opening Tartakower Variation"),
            "Peão de Dama",
        )

    def test_reconhece_jogo_do_centro_grafia_americana(self) -> None:
        self.assertEqual(
            normalizar_abertura("Center Game Accepted Normal Variation"),
            "Jogo do Centro",
        )

    def test_fallback_mantem_nome_original_quando_nao_reconhecido(self) -> None:
        self.assertEqual(
            normalizar_abertura("Van't Kruijs Opening"), "Van't Kruijs Opening"
        )

    def test_fallback_desconhecida_quando_nao_ha_nome(self) -> None:
        self.assertEqual(normalizar_abertura(None), SEM_NOME)
        self.assertEqual(normalizar_abertura("   "), SEM_NOME)


class ExtrairNomeDoPgnTest(unittest.TestCase):
    """Tag [Opening] do PGN, quando presente (avulsas/MANUAL)."""

    def test_le_a_tag_opening(self) -> None:
        pgn = (
            '[Event "?"]\n[Opening "Sicilian Defense"]\n\n1. e4 c5 *'
        )
        self.assertEqual(extrair_nome_do_pgn(pgn), "Sicilian Defense")

    def test_devolve_none_sem_a_tag(self) -> None:
        pgn = '[Event "?"]\n\n1. e4 e5 *'
        self.assertIsNone(extrair_nome_do_pgn(pgn))


class ExtrairNomeDeEcourlTest(unittest.TestCase):
    """Tag [ECOUrl] do Chess.com, com o nome embutido na própria URL."""

    def test_extrai_e_converte_hifens_em_espacos(self) -> None:
        pgn = (
            '[ECOUrl "https://www.chess.com/openings/'
            'French-Defense-Steinitz-Attack"]\n\n1. e4 e6 *'
        )
        self.assertEqual(extrair_nome_de_ecourl(pgn), "French Defense Steinitz Attack")

    def test_devolve_none_sem_a_tag(self) -> None:
        self.assertIsNone(extrair_nome_de_ecourl('[Event "?"]\n\n1. e4 *'))


class ResolverNomeAberturaTest(unittest.TestCase):
    """Ordem de resolução: tag Opening > ECOUrl > API do Lichess (só Lichess)."""

    def test_prefere_a_tag_opening_quando_presente(self) -> None:
        pgn = '[Opening "Ruy Lopez"]\n\n1. e4 e5 *'
        logger = MagicMock()
        with patch(
            "backend.agentes.normalizar_aberturas.buscar_nome_via_lichess"
        ) as mock_busca:
            nome = resolver_nome_abertura("LICHESS", pgn, "abc123", logger)
        self.assertEqual(nome, "Ruy Lopez")
        mock_busca.assert_not_called()

    def test_usa_ecourl_para_chesscom_sem_tag_opening(self) -> None:
        pgn = (
            '[ECOUrl "https://www.chess.com/openings/Italian-Game"]\n\n1. e4 e5 *'
        )
        logger = MagicMock()
        nome = resolver_nome_abertura("CHESSCOM", pgn, None, logger)
        self.assertEqual(nome, "Italian Game")

    def test_busca_na_api_do_lichess_quando_pgn_nao_tem_nada(self) -> None:
        pgn = '[Event "Lichess game"]\n\n1. e4 e5 *'
        logger = MagicMock()
        with patch(
            "backend.agentes.normalizar_aberturas.buscar_nome_via_lichess",
            return_value="Ruy Lopez: Morphy Defense",
        ) as mock_busca:
            nome = resolver_nome_abertura("LICHESS", pgn, "abc123", logger)
        self.assertEqual(nome, "Ruy Lopez: Morphy Defense")
        mock_busca.assert_called_once_with("abc123", logger)

    def test_nao_chama_api_para_plataformas_que_nao_sao_lichess(self) -> None:
        pgn = '[Event "?"]\n\n1. e4 e5 *'
        logger = MagicMock()
        with patch(
            "backend.agentes.normalizar_aberturas.buscar_nome_via_lichess"
        ) as mock_busca:
            nome = resolver_nome_abertura("MANUAL", pgn, None, logger)
        self.assertIsNone(nome)
        mock_busca.assert_not_called()


class AtualizarAberturaTest(unittest.TestCase):
    """Grava só a coluna abertura_normalizada, filtrando pelo id da partida."""

    def test_grava_via_update_filtrando_por_id(self) -> None:
        client = MagicMock()
        atualizar_abertura(client, "partida-1", "Siciliana")

        client.table.assert_called_once_with("partidas")
        client.table.return_value.update.assert_called_once_with(
            {"abertura_normalizada": "Siciliana"}
        )
        client.table.return_value.update.return_value.eq.assert_called_once_with(
            "id", "partida-1"
        )


if __name__ == "__main__":
    unittest.main()
