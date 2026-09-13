"""Testes do dono dos dados (`DEFAULT_USER_ID`) — Fase A do multi-tenant."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.common.tenant import DEFAULT_USER_ID_ENV, obter_default_user_id


class ObterDefaultUserIdTest(unittest.TestCase):
    def test_devolve_o_valor_do_ambiente(self) -> None:
        with patch.dict(os.environ, {DEFAULT_USER_ID_ENV: "abc-123"}):
            self.assertEqual(obter_default_user_id(), "abc-123")

    def test_erro_explicito_quando_a_variavel_falta(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as contexto:
                obter_default_user_id()

        self.assertIn(DEFAULT_USER_ID_ENV, str(contexto.exception))

    def test_erro_explicito_quando_a_variavel_esta_vazia(self) -> None:
        # String vazia no .env é tão inválida quanto ausência: sem esse guarda,
        # o insert iria ao banco com user_id vazio e só quebraria no NOT NULL.
        with patch.dict(os.environ, {DEFAULT_USER_ID_ENV: ""}):
            with self.assertRaises(ValueError):
                obter_default_user_id()

    def test_le_o_ambiente_a_cada_chamada(self) -> None:
        # O valor não pode ser capturado no import: os scripts só chamam
        # load_dotenv() dentro do load_settings(), depois do import.
        with patch.dict(os.environ, {DEFAULT_USER_ID_ENV: "primeiro"}):
            self.assertEqual(obter_default_user_id(), "primeiro")
        with patch.dict(os.environ, {DEFAULT_USER_ID_ENV: "segundo"}):
            self.assertEqual(obter_default_user_id(), "segundo")


if __name__ == "__main__":
    unittest.main()
