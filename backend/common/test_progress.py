"""Testes de backend/common/progress.py — utilitário compartilhado por todo
o pipeline (loop de ingestão/agentes), sem teste próprio até uma auditoria
de qualidade pós-D-49."""

from __future__ import annotations

import io
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.progress import (  # noqa: E402
    configurar_encoding_utf8,
    format_duration,
    format_progress,
    log_and_print,
)


class FormatDurationTest(unittest.TestCase):
    def test_menos_de_um_minuto_devolve_segundos(self) -> None:
        self.assertEqual(format_duration(45), "45s")

    def test_um_minuto_exato_devolve_minutos(self) -> None:
        self.assertEqual(format_duration(60), "1min")

    def test_arredonda_para_o_minuto_mais_proximo(self) -> None:
        self.assertEqual(format_duration(170), "3min")

    def test_negativo_vira_zero_segundos(self) -> None:
        self.assertEqual(format_duration(-5), "0s")

    def test_arredonda_segundos_fracionarios(self) -> None:
        self.assertEqual(format_duration(44.6), "45s")


class FormatProgressTest(unittest.TestCase):
    def test_monta_mensagem_com_percentual_e_eta(self) -> None:
        mensagem = format_progress("Coleta", "partidas", 5, 10, elapsed=50.0)

        self.assertIn("Coleta: 5/10 partidas (50%)", mensagem)
        self.assertIn("tempo estimado restante: 50s", mensagem)

    def test_total_zero_nao_divide_por_zero(self) -> None:
        mensagem = format_progress("Coleta", "partidas", 0, 0, elapsed=0.0)

        self.assertIn("(0%)", mensagem)
        self.assertIn("0s", mensagem)

    def test_processed_zero_nao_divide_por_zero_no_eta(self) -> None:
        mensagem = format_progress("Coleta", "partidas", 0, 10, elapsed=0.0)

        self.assertIn("(0%)", mensagem)
        self.assertIn("0s", mensagem)


class LogAndPrintTest(unittest.TestCase):
    def test_registra_no_logger_e_imprime_no_terminal(self) -> None:
        logger = MagicMock(spec=logging.Logger)
        buffer = io.StringIO()
        stdout_original = sys.stdout
        sys.stdout = buffer
        try:
            log_and_print(logger, "mensagem de teste")
        finally:
            sys.stdout = stdout_original

        logger.info.assert_called_once_with("mensagem de teste")
        self.assertIn("mensagem de teste", buffer.getvalue())


class ConfigurarEncodingUtf8Test(unittest.TestCase):
    def test_reconfigura_stdout_e_stderr_quando_suportado(self) -> None:
        stdout_fake = MagicMock()
        stderr_fake = MagicMock()
        stdout_original, stderr_original = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout_fake, stderr_fake
        try:
            configurar_encoding_utf8()
        finally:
            sys.stdout, sys.stderr = stdout_original, stderr_original

        stdout_fake.reconfigure.assert_called_once_with(encoding="utf-8")
        stderr_fake.reconfigure.assert_called_once_with(encoding="utf-8")

    def test_stream_sem_reconfigure_nao_lanca(self) -> None:
        class StreamSemReconfigure:
            pass

        stdout_original, stderr_original = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = StreamSemReconfigure(), StreamSemReconfigure()
        try:
            configurar_encoding_utf8()  # não deve lançar
        finally:
            sys.stdout, sys.stderr = stdout_original, stderr_original

    def test_reconfigure_que_lanca_e_engolido(self) -> None:
        stdout_fake = MagicMock()
        stdout_fake.reconfigure.side_effect = ValueError("stream fechado")
        stdout_original = sys.stdout
        sys.stdout = stdout_fake
        try:
            configurar_encoding_utf8()  # não deve propagar a exceção
        finally:
            sys.stdout = stdout_original


if __name__ == "__main__":
    unittest.main()
