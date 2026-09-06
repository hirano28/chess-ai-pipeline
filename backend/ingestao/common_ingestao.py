"""Funções compartilhadas pelos coletores de partidas."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import requests
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "ingestao.log"
MAX_RETRIES = 3
T = TypeVar("T")


def create_supabase_client(url: str, service_role_key: str) -> Client:
    """Cria um cliente Supabase para os coletores."""

    return create_client(url, service_role_key)


def configure_logging(
    log_path: Path = DEFAULT_LOG_PATH,
    logger_name: str = "ingestao",
) -> logging.Logger:
    """Configura logging em arquivo e mantém o logger compartilhável."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


def with_retry(
    operation: Callable[[], T], logger: logging.Logger, description: str
) -> T:
    """Executa uma operação de rede até três vezes com backoff exponencial."""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return operation()
        except (requests.RequestException, requests.Timeout) as error:
            if attempt == MAX_RETRIES:
                logger.error(
                    "%s falhou após %d tentativas: %s", description, attempt, error
                )
                raise
            delay = 2 ** (attempt - 1)
            logger.warning(
                "%s falhou na tentativa %d/%d; nova tentativa em %ds: %s",
                description,
                attempt,
                MAX_RETRIES,
                delay,
                error,
            )
            time.sleep(delay)
    raise RuntimeError("Operação encerrada sem resultado")


def already_exists(client: Client, external_id: str) -> bool:
    """Verifica se o identificador externo já está cadastrado."""

    result = (
        client.table("partidas")
        .select("external_id")
        .eq("external_id", external_id)
        .limit(1)
        .execute()
    )
    return bool(result.data)


def insert_game(client: Client, record: dict[str, Any]) -> None:
    """Insere um registro de partida na tabela partidas."""

    client.table("partidas").insert(record).execute()
