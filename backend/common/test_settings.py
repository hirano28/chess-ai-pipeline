"""Testes de backend/common/settings.py — o helper compartilhado que
substituiu ~18 `load_settings()` quase-idênticos numa auditoria pós-D-49."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.settings import carregar_variaveis_obrigatorias  # noqa: E402


class CarregarVariaveisObrigatoriasTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _escrever_env(self, conteudo: str) -> None:
        (self.tmp_path / ".env").write_text(conteudo, encoding="utf-8")

    def test_devolve_todas_as_variaveis_presentes(self) -> None:
        self._escrever_env("FOO=valor-foo\nBAR=valor-bar\n")

        with patch.dict("os.environ", {}, clear=False):
            for chave in ("FOO", "BAR"):
                __import__("os").environ.pop(chave, None)
            resultado = carregar_variaveis_obrigatorias(self.tmp_path, "FOO", "BAR")

        self.assertEqual(resultado, {"FOO": "valor-foo", "BAR": "valor-bar"})

    def test_uma_variavel_ausente_levanta_value_error_com_o_nome(self) -> None:
        self._escrever_env("FOO=valor-foo\n")

        with patch.dict("os.environ", {}, clear=False):
            __import__("os").environ.pop("FOO", None)
            __import__("os").environ.pop("BAR", None)
            with self.assertRaises(ValueError) as ctx:
                carregar_variaveis_obrigatorias(self.tmp_path, "FOO", "BAR")

        self.assertIn("BAR", str(ctx.exception))
        self.assertNotIn("FOO", str(ctx.exception))

    def test_varias_variaveis_ausentes_lista_todas_ordenadas(self) -> None:
        self._escrever_env("")

        with patch.dict("os.environ", {}, clear=False):
            for chave in ("ZULU", "ALFA"):
                __import__("os").environ.pop(chave, None)
            with self.assertRaises(ValueError) as ctx:
                carregar_variaveis_obrigatorias(self.tmp_path, "ZULU", "ALFA")

        mensagem = str(ctx.exception)
        self.assertLess(mensagem.index("ALFA"), mensagem.index("ZULU"))

    def test_variavel_vazia_conta_como_ausente(self) -> None:
        self._escrever_env("FOO=\n")

        with patch.dict("os.environ", {}, clear=False):
            __import__("os").environ.pop("FOO", None)
            with self.assertRaises(ValueError):
                carregar_variaveis_obrigatorias(self.tmp_path, "FOO")

    def test_env_var_ja_no_ambiente_prevalece_sem_arquivo_env(self) -> None:
        with patch.dict("os.environ", {"FOO": "do-ambiente"}, clear=False):
            resultado = carregar_variaveis_obrigatorias(self.tmp_path, "FOO")

        self.assertEqual(resultado, {"FOO": "do-ambiente"})


if __name__ == "__main__":
    unittest.main()
