"""Testes unitários para analisar_pgn_avulso.py."""

from __future__ import annotations

import io
import os
import unittest
from unittest.mock import MagicMock, patch

import chess.pgn

from backend.agentes.analisar_pgn_avulso import (
    determinar_cor,
    executar_pipeline_partida,
    extrair_data,
    extrair_rating,
    extrair_resultado,
    gerar_external_id,
    inferir_cor_jogador,
    inserir_partida,
    ler_pgn_de_arquivo,
    parse_pgn,
    resolver_cor,
)


# ---------------------------------------------------------------------------
# PGN de teste
# ---------------------------------------------------------------------------

PGN_VALIDO = """[Event "Rated Blitz game"]
[Site "https://lichess.org/AmxiZxvj"]
[Date "2024.06.15"]
[White "hirano28"]
[Black "opponent123"]
[Result "0-1"]
[WhiteElo "1500"]
[BlackElo "1600"]
[ECO "B90"]

1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 0-1"""

PGN_SEM_HEADERS = """1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1/2-1/2"""

PGN_VAZIO_LANCES = """[Event "Test"]
[Result "*"]

*"""


def _game_from_pgn(pgn_text: str) -> chess.pgn.Game:
    return chess.pgn.read_game(io.StringIO(pgn_text))


# ---------------------------------------------------------------------------
# Testes: parse_pgn
# ---------------------------------------------------------------------------

class TestParsePgn(unittest.TestCase):
    """Testes para a leitura e validação do PGN."""

    def test_pgn_valido(self):
        game = parse_pgn(PGN_VALIDO)
        self.assertEqual(game.headers.get("White"), "hirano28")

    def test_pgn_invalido_raises(self):
        with self.assertRaises(ValueError):
            parse_pgn("não é um PGN")

    def test_pgn_sem_lances_raises(self):
        with self.assertRaises(ValueError):
            parse_pgn(PGN_VAZIO_LANCES)


# ---------------------------------------------------------------------------
# Testes: inferir_cor_jogador
# ---------------------------------------------------------------------------

class TestInferirCorJogador(unittest.TestCase):
    """Testes para a inferência automática da cor."""

    @patch("backend.agentes.analisar_pgn_avulso.load_dotenv")
    @patch("backend.agentes.analisar_pgn_avulso.os.getenv")
    def test_detecta_brancas(self, mock_getenv, mock_dotenv):
        mock_getenv.side_effect = lambda k, d=None: {"LICHESS_USERNAME": "hirano28"}.get(k, d)
        game = _game_from_pgn(PGN_VALIDO)
        self.assertEqual(inferir_cor_jogador(game), "BRANCAS")

    @patch("backend.agentes.analisar_pgn_avulso.load_dotenv")
    @patch("backend.agentes.analisar_pgn_avulso.os.getenv")
    def test_detecta_pretas(self, mock_getenv, mock_dotenv):
        mock_getenv.side_effect = lambda k, d=None: {"LICHESS_USERNAME": "opponent123"}.get(k, d)
        game = _game_from_pgn(PGN_VALIDO)
        self.assertEqual(inferir_cor_jogador(game), "PRETAS")

    @patch("backend.agentes.analisar_pgn_avulso.load_dotenv")
    @patch("backend.agentes.analisar_pgn_avulso.os.getenv")
    def test_nao_detecta_retorna_none(self, mock_getenv, mock_dotenv):
        mock_getenv.side_effect = lambda k, d=None: {"LICHESS_USERNAME": "outro_usuario"}.get(k, d)
        game = _game_from_pgn(PGN_VALIDO)
        self.assertIsNone(inferir_cor_jogador(game))

    @patch("backend.agentes.analisar_pgn_avulso.load_dotenv")
    @patch("backend.agentes.analisar_pgn_avulso.os.getenv")
    def test_sem_usernames_retorna_none(self, mock_getenv, mock_dotenv):
        mock_getenv.side_effect = lambda k, d=None: {}.get(k, d)
        game = _game_from_pgn(PGN_VALIDO)
        self.assertIsNone(inferir_cor_jogador(game))


# ---------------------------------------------------------------------------
# Testes: resolver_cor
# ---------------------------------------------------------------------------

class TestResolverCor(unittest.TestCase):
    """Testes para a resolução de cor com ou sem inferência automática."""

    def test_cor_explicita_brancas(self):
        game = _game_from_pgn(PGN_SEM_HEADERS)
        self.assertEqual(resolver_cor(game, "BRANCAS"), "BRANCAS")
        self.assertEqual(resolver_cor(game, "brancas"), "BRANCAS")
        self.assertEqual(resolver_cor(game, "B"), "BRANCAS")

    def test_cor_explicita_pretas(self):
        game = _game_from_pgn(PGN_SEM_HEADERS)
        self.assertEqual(resolver_cor(game, "PRETAS"), "PRETAS")
        self.assertEqual(resolver_cor(game, "pretas"), "PRETAS")
        self.assertEqual(resolver_cor(game, "P"), "PRETAS")

    def test_cor_invalida_raises(self):
        game = _game_from_pgn(PGN_SEM_HEADERS)
        with self.assertRaises(ValueError) as ctx:
            resolver_cor(game, "AZUL")
        self.assertIn("Cor inválida", str(ctx.exception))

    @patch("backend.agentes.analisar_pgn_avulso.load_dotenv")
    @patch("backend.agentes.analisar_pgn_avulso.os.getenv")
    def test_cor_none_com_inferencia_sucesso(self, mock_getenv, mock_dotenv):
        mock_getenv.side_effect = lambda k, d=None: {"LICHESS_USERNAME": "hirano28"}.get(k, d)
        game = _game_from_pgn(PGN_VALIDO)
        self.assertEqual(resolver_cor(game, None), "BRANCAS")

    @patch("backend.agentes.analisar_pgn_avulso.load_dotenv")
    @patch("backend.agentes.analisar_pgn_avulso.os.getenv")
    def test_cor_none_sem_inferencia_raises_value_error(self, mock_getenv, mock_dotenv):
        mock_getenv.side_effect = lambda k, d=None: {"LICHESS_USERNAME": "outro"}.get(k, d)
        game = _game_from_pgn(PGN_VALIDO)
        with self.assertRaises(ValueError) as ctx:
            resolver_cor(game, None)
        self.assertIn("informe a cor explicitamente", str(ctx.exception))


# ---------------------------------------------------------------------------
# Testes: extrair_resultado
# ---------------------------------------------------------------------------

class TestExtrairResultado(unittest.TestCase):
    """Testes para a normalização do resultado."""

    def test_vitoria_brancas(self):
        game = _game_from_pgn(PGN_VALIDO)
        self.assertEqual(extrair_resultado(game, "BRANCAS"), "DERROTA")

    def test_vitoria_pretas(self):
        game = _game_from_pgn(PGN_VALIDO)
        self.assertEqual(extrair_resultado(game, "PRETAS"), "VITORIA")

    def test_empate(self):
        game = _game_from_pgn(PGN_SEM_HEADERS)
        self.assertEqual(extrair_resultado(game, "BRANCAS"), "EMPATE")

    def test_resultado_desconhecido(self):
        game = _game_from_pgn(PGN_VAZIO_LANCES)
        self.assertIsNone(extrair_resultado(game, "BRANCAS"))


# ---------------------------------------------------------------------------
# Testes: extrair_rating
# ---------------------------------------------------------------------------

class TestExtrairRating(unittest.TestCase):
    """Testes para a extração de ratings do PGN."""

    def test_ratings_presentes(self):
        game = _game_from_pgn(PGN_VALIDO)
        proprio, oponente = extrair_rating(game, "BRANCAS")
        self.assertEqual(proprio, 1500)
        self.assertEqual(oponente, 1600)

    def test_ratings_invertidos_pretas(self):
        game = _game_from_pgn(PGN_VALIDO)
        proprio, oponente = extrair_rating(game, "PRETAS")
        self.assertEqual(proprio, 1600)
        self.assertEqual(oponente, 1500)

    def test_ratings_ausentes(self):
        game = _game_from_pgn(PGN_SEM_HEADERS)
        proprio, oponente = extrair_rating(game, "BRANCAS")
        self.assertIsNone(proprio)
        self.assertIsNone(oponente)


# ---------------------------------------------------------------------------
# Testes: extrair_data
# ---------------------------------------------------------------------------

class TestExtrairData(unittest.TestCase):
    """Testes para a extração da data do PGN."""

    def test_data_presente(self):
        game = _game_from_pgn(PGN_VALIDO)
        self.assertEqual(extrair_data(game), "2024-06-15")

    def test_data_ausente(self):
        game = _game_from_pgn(PGN_SEM_HEADERS)
        self.assertIsNone(extrair_data(game))


# ---------------------------------------------------------------------------
# Testes: gerar_external_id
# ---------------------------------------------------------------------------

class TestGerarExternalId(unittest.TestCase):
    """Testes para a geração de external_id determinístico."""

    def test_hash_deterministico(self):
        id1 = gerar_external_id(PGN_VALIDO)
        id2 = gerar_external_id(PGN_VALIDO)
        self.assertEqual(id1, id2)

    def test_prefixo_manual(self):
        external_id = gerar_external_id(PGN_VALIDO)
        self.assertTrue(external_id.startswith("manual_"))

    def test_pgns_diferentes_geram_ids_diferentes(self):
        id1 = gerar_external_id(PGN_VALIDO)
        id2 = gerar_external_id(PGN_SEM_HEADERS)
        self.assertNotEqual(id1, id2)

    def test_whitespace_nao_afeta(self):
        id1 = gerar_external_id("  " + PGN_VALIDO + "  ")
        id2 = gerar_external_id(PGN_VALIDO)
        self.assertEqual(id1, id2)


# ---------------------------------------------------------------------------
# Testes: ler_pgn_de_arquivo
# ---------------------------------------------------------------------------

class TestLerPgnDeArquivo(unittest.TestCase):
    """Testes para leitura de arquivo PGN."""

    def test_arquivo_inexistente_raises(self):
        with self.assertRaises(FileNotFoundError):
            ler_pgn_de_arquivo("/caminho/inexistente/partida.pgn")


# ---------------------------------------------------------------------------
# Testes: determinar_cor (com mock)
# ---------------------------------------------------------------------------

class TestDeterminarCor(unittest.TestCase):
    """Testes para a determinação de cor (automática vs interativa)."""

    @patch("backend.agentes.analisar_pgn_avulso.load_dotenv")
    @patch("backend.agentes.analisar_pgn_avulso.os.getenv")
    def test_cor_automatica(self, mock_getenv, mock_dotenv):
        mock_getenv.side_effect = lambda k, d=None: {"LICHESS_USERNAME": "hirano28"}.get(k, d)
        game = _game_from_pgn(PGN_VALIDO)
        cor = determinar_cor(game)
        self.assertEqual(cor, "BRANCAS")

    @patch("backend.agentes.analisar_pgn_avulso.load_dotenv")
    @patch("backend.agentes.analisar_pgn_avulso.os.getenv")
    @patch("builtins.input", return_value="P")
    def test_cor_interativa(self, mock_input, mock_getenv, mock_dotenv):
        mock_getenv.side_effect = lambda k, d=None: {"LICHESS_USERNAME": "outro"}.get(k, d)
        game = _game_from_pgn(PGN_VALIDO)
        cor = determinar_cor(game)
        self.assertEqual(cor, "PRETAS")


# ---------------------------------------------------------------------------
# Testes: executar_pipeline_partida
# ---------------------------------------------------------------------------

class TestExecutarPipelinePartida(unittest.TestCase):
    """Testes unitários para o orquestrador de pipeline das 3 etapas."""

    @patch("backend.agentes.analisar_pgn_avulso.update_status")
    @patch("backend.agentes.analisar_pgn_avulso.etapa_resumo")
    @patch("backend.agentes.analisar_pgn_avulso.etapa_diagnostico")
    @patch("backend.agentes.analisar_pgn_avulso.etapa_stockfish")
    def test_pipeline_executa_3_etapas_com_sucesso(
        self, mock_stockfish, mock_diag, mock_resumo, mock_update
    ):
        mock_stockfish.return_value = 2
        mock_resumo.return_value = {"narrativa": "Boa partida.", "pontos_criticos": []}

        fake_lock = MagicMock()
        mock_client = MagicMock()
        mock_gemini = MagicMock()
        mock_analysis_settings = MagicMock()
        mock_linter_settings = MagicMock()

        resultado = executar_pipeline_partida(
            client=mock_client,
            partida_id="partida_123",
            gemini_client=mock_gemini,
            analysis_settings=mock_analysis_settings,
            linter_settings=mock_linter_settings,
            engine_lock=fake_lock,
        )

        self.assertEqual(resultado, {"narrativa": "Boa partida.", "pontos_criticos": []})
        mock_stockfish.assert_called_once()
        mock_diag.assert_called_once()
        mock_resumo.assert_called_once()
        mock_update.assert_called_with(mock_client, "partida_123", "concluido")
        # Confirma que o engine_lock foi adquirido
        fake_lock.__enter__.assert_called()

    @patch("backend.agentes.analisar_pgn_avulso.update_status")
    @patch("backend.agentes.analisar_pgn_avulso.etapa_resumo")
    @patch("backend.agentes.analisar_pgn_avulso.etapa_diagnostico")
    @patch("backend.agentes.analisar_pgn_avulso.etapa_stockfish")
    def test_pipeline_sem_lances_criticos_retorna_none(
        self, mock_stockfish, mock_diag, mock_resumo, mock_update
    ):
        mock_stockfish.return_value = 0
        mock_client = MagicMock()

        resultado = executar_pipeline_partida(
            client=mock_client,
            partida_id="partida_sem_erros",
            gemini_client=MagicMock(),
            analysis_settings=MagicMock(),
            linter_settings=MagicMock(),
        )

        self.assertIsNone(resultado)
        mock_stockfish.assert_called_once()
        mock_diag.assert_not_called()
        mock_resumo.assert_not_called()
        mock_update.assert_called_with(mock_client, "partida_sem_erros", "concluido")

    @patch("backend.agentes.analisar_pgn_avulso.update_status")
    @patch("backend.agentes.analisar_pgn_avulso.etapa_stockfish")
    def test_pipeline_falha_marca_status_como_falhou(self, mock_stockfish, mock_update):
        mock_stockfish.side_effect = RuntimeError("Erro no Stockfish")
        mock_client = MagicMock()

        with self.assertRaises(RuntimeError):
            executar_pipeline_partida(
                client=mock_client,
                partida_id="partida_com_erro",
                gemini_client=MagicMock(),
                analysis_settings=MagicMock(),
                linter_settings=MagicMock(),
            )

        mock_update.assert_called_with(mock_client, "partida_com_erro", "falhou")


class InserirPartidaUserIdTest(unittest.TestCase):
    """user_id explícito (Fase B.2, D-17) vs. fallback DEFAULT_USER_ID (D-14)."""

    USER_ID_DEFAULT = "11111111-2222-3333-4444-555555555555"
    USER_ID_SESSAO = "99999999-8888-7777-6666-555555555555"

    def setUp(self) -> None:
        self._env = patch.dict(os.environ, {"DEFAULT_USER_ID": self.USER_ID_DEFAULT})
        self._env.start()
        self.addCleanup(self._env.stop)

    def _mock_client_com_id(self, partida_id: str) -> MagicMock:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [{"id": partida_id}]
        client.table.return_value.upsert.return_value.execute.return_value = resp
        return client

    def test_sem_user_id_explicito_usa_default_user_id(self) -> None:
        client = self._mock_client_com_id("partida-1")
        game = parse_pgn(PGN_VALIDO)

        inserir_partida(client, PGN_VALIDO, game, "BRANCAS")

        payload = client.table.return_value.upsert.call_args[0][0]
        self.assertEqual(payload["user_id"], self.USER_ID_DEFAULT)

    def test_com_user_id_explicito_usa_o_dono_da_sessao(self) -> None:
        client = self._mock_client_com_id("partida-2")
        game = parse_pgn(PGN_VALIDO)

        inserir_partida(client, PGN_VALIDO, game, "BRANCAS", user_id=self.USER_ID_SESSAO)

        payload = client.table.return_value.upsert.call_args[0][0]
        self.assertEqual(payload["user_id"], self.USER_ID_SESSAO)


if __name__ == "__main__":
    unittest.main()
