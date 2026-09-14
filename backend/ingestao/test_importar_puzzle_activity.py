"""Testes do script de importação de atividade de puzzles via OAuth (D-34)."""

from __future__ import annotations

import json
import logging
import unittest
from unittest.mock import MagicMock, patch

from backend.ingestao.importar_puzzle_activity import (
    TokenRevogadoError,
    fetch_puzzle_activity_lines,
    importar_para_usuario,
    imprimir_resumo,
    parse_puzzle_activity_line,
    upsert_puzzle_atividade,
)

USER_ID = "bfde845a-8e2e-4885-801f-0fed2dd3b426"

EXEMPLO_NDJSON_LINHA = (
    b'{"date":1788790574929,"win":false,"puzzle":'
    b'{"id":"5yuro","rating":2242,"plays":2944,'
    b'"solution":["d4f5","g7f7"],"themes":["fork","sacrifice"],"fen":"4n3/...",'
    b'"lastMove":"f6e8"}}'
)


class ParsePuzzleActivityLineTest(unittest.TestCase):
    def test_parseia_campos_corretamente(self) -> None:
        resultado = parse_puzzle_activity_line(EXEMPLO_NDJSON_LINHA)

        self.assertEqual(resultado["puzzle_id"], "5yuro")
        self.assertEqual(resultado["rating_puzzle"], 2242)
        self.assertEqual(resultado["acertou"], False)
        self.assertEqual(resultado["temas"], ["fork", "sacrifice"])
        self.assertIn("2026-", resultado["data"])

    def test_linha_invalida_lanca_excecao(self) -> None:
        with self.assertRaises(Exception):
            parse_puzzle_activity_line(b"json invalido")


class UpsertPuzzleAtividadeTest(unittest.TestCase):
    def test_grava_com_o_user_id_recebido(self) -> None:
        client = MagicMock()
        registro = {
            "puzzle_id": "5yuro",
            "data": "2026-09-08T03:36:14+00:00",
            "acertou": False,
            "temas": ["fork"],
            "rating_puzzle": 2242,
        }

        upsert_puzzle_atividade(client, registro, USER_ID)

        client.table.assert_called_once_with("puzzle_atividade")
        upsert_call = client.table.return_value.upsert
        self.assertTrue(upsert_call.called)
        payload = upsert_call.call_args[0][0]
        self.assertEqual(payload["user_id"], USER_ID)
        self.assertEqual(payload["puzzle_id"], "5yuro")
        self.assertEqual(upsert_call.call_args[1]["on_conflict"], "puzzle_id,data")


class FetchPuzzleActivityLinesTest(unittest.TestCase):
    @patch("backend.ingestao.importar_puzzle_activity.requests.get")
    def test_status_401_lanca_token_revogado(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value.__enter__.return_value = mock_resp

        logger = logging.getLogger("test")
        with self.assertRaises(TokenRevogadoError):
            fetch_puzzle_activity_lines("token-revogado", logger)

    @patch("backend.ingestao.importar_puzzle_activity.requests.get")
    def test_sucesso_devolve_linhas(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_lines.return_value = [EXEMPLO_NDJSON_LINHA, b"", EXEMPLO_NDJSON_LINHA]
        mock_get.return_value.__enter__.return_value = mock_resp

        logger = logging.getLogger("test")
        linhas = fetch_puzzle_activity_lines("token-valido", logger)

        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[0], EXEMPLO_NDJSON_LINHA)


class ImportarParaUsuarioTest(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("test")
        self.client = MagicMock()

    @patch("backend.ingestao.importar_puzzle_activity.obter_access_token_lichess")
    def test_usuario_sem_token_valido_e_pulado_sem_erro(
        self, mock_obter_token: MagicMock
    ) -> None:
        mock_obter_token.return_value = None

        registros, falhas_parse, falhas_upsert = importar_para_usuario(
            self.client, USER_ID, self.logger
        )

        self.assertEqual(registros, [])
        self.assertEqual(falhas_parse, 0)
        self.assertEqual(falhas_upsert, 0)

    @patch("backend.ingestao.importar_puzzle_activity.fetch_puzzle_activity_lines")
    @patch("backend.ingestao.importar_puzzle_activity.obter_access_token_lichess")
    def test_token_revogado_401_loga_e_isola_erro(
        self, mock_obter_token: MagicMock, mock_fetch: MagicMock
    ) -> None:
        mock_obter_token.return_value = "token-revogado"
        mock_fetch.side_effect = TokenRevogadoError("401")

        registros, falhas_parse, falhas_upsert = importar_para_usuario(
            self.client, USER_ID, self.logger
        )

        self.assertEqual(registros, [])
        self.assertEqual(falhas_parse, 0)
        self.assertEqual(falhas_upsert, 0)

    @patch("backend.ingestao.importar_puzzle_activity.upsert_puzzle_atividade")
    @patch("backend.ingestao.importar_puzzle_activity.fetch_puzzle_activity_lines")
    @patch("backend.ingestao.importar_puzzle_activity.obter_access_token_lichess")
    def test_sucesso_importa_com_user_id(
        self,
        mock_obter_token: MagicMock,
        mock_fetch: MagicMock,
        mock_upsert: MagicMock,
    ) -> None:
        mock_obter_token.return_value = "token-valido"
        mock_fetch.return_value = [EXEMPLO_NDJSON_LINHA]

        registros, falhas_parse, falhas_upsert = importar_para_usuario(
            self.client, USER_ID, self.logger
        )

        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["puzzle_id"], "5yuro")
        self.assertEqual(falhas_parse, 0)
        self.assertEqual(falhas_upsert, 0)
        mock_upsert.assert_called_once()
        self.assertEqual(mock_upsert.call_args[0][2], USER_ID)

    @patch("backend.ingestao.importar_puzzle_activity.upsert_puzzle_atividade")
    @patch("backend.ingestao.importar_puzzle_activity.fetch_puzzle_activity_lines")
    @patch("backend.ingestao.importar_puzzle_activity.obter_access_token_lichess")
    def test_linha_com_erro_de_parsing_nao_aborta_as_demais(
        self,
        mock_obter_token: MagicMock,
        mock_fetch: MagicMock,
        mock_upsert: MagicMock,
    ) -> None:
        mock_obter_token.return_value = "token-valido"
        mock_fetch.return_value = [b"linha invalida", EXEMPLO_NDJSON_LINHA]

        registros, falhas_parse, falhas_upsert = importar_para_usuario(
            self.client, USER_ID, self.logger
        )

        self.assertEqual(len(registros), 1)
        self.assertEqual(falhas_parse, 1)
        self.assertEqual(falhas_upsert, 0)


class ImprimirResumoTest(unittest.TestCase):
    def test_imprime_resumo_sem_quebrar(self) -> None:
        logger = logging.getLogger("test")
        registros = [
            {"acertou": True, "temas": ["fork", "pin"]},
            {"acertou": False, "temas": ["fork"]},
        ]
        # Não deve lançar exceção
        imprimir_resumo(logger, registros, 0, 0, 1, 0)

    def test_imprime_resumo_vazio(self) -> None:
        logger = logging.getLogger("test")
        imprimir_resumo(logger, [], 0, 0, 0, 1)


if __name__ == "__main__":
    unittest.main()
