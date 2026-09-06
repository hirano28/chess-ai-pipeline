"""Utilitários de log de progresso compartilhados pelo pipeline."""

from __future__ import annotations

import logging


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
