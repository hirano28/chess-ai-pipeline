"""Utilitários de log de progresso compartilhados pelo pipeline."""

from __future__ import annotations

import logging
import sys


def configurar_encoding_utf8() -> None:
    """Reconfigura stdout/stderr para UTF-8, evitando UnicodeEncodeError.

    No console padrão do Windows (code page cp1252), print()/logging com
    emojis quebram com UnicodeEncodeError. `TextIOWrapper.reconfigure` existe
    em qualquer plataforma (Python 3.7+) e mutar o stream in-place mantém
    válidas referências já capturadas por handlers (ex.: logging.StreamHandler
    guarda sys.stderr no momento da criação). Em sistemas onde o stream já é
    UTF-8 (Linux/GitHub Actions) ou não suporta reconfigure (ex.: stdout
    capturado por um test runner), a chamada é inócua.
    """

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def format_duration(seconds: float) -> str:
    """Formata uma duração em segundos como texto curto (min/s)."""

    seconds = max(0, int(round(seconds)))
    if seconds >= 60:
        return f"{round(seconds / 60)}min"
    return f"{seconds}s"


def format_progress(
    prefix: str, unit: str, processed: int, total: int, elapsed: float
) -> str:
    """Monta a mensagem de progresso com porcentagem e ETA."""

    percent = int(processed / total * 100) if total else 0
    average = elapsed / processed if processed else 0.0
    remaining = average * (total - processed)
    return (
        f"{prefix}: {processed}/{total} {unit} ({percent}%) "
        f"- tempo estimado restante: {format_duration(remaining)}"
    )


def log_and_print(logger: logging.Logger, message: str) -> None:
    """Registra a mensagem no arquivo de log e também no terminal."""

    logger.info(message)
    print(message)
