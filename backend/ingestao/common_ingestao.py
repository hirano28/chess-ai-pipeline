"""Funções compartilhadas pelos coletores de partidas."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import requests
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
# Mesmo padrão dos outros módulos do repo: o sys.path tem que ser ajustado
# antes do import do pacote `backend`, daí o noqa (namespace packages, sem
# __init__.py — ver AGENTS.md).
from backend.common.cadencia import (  # noqa: E402
    campos_de_cadencia,
    time_control_do_pgn,
)

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


def insert_game(
    client: Client, record: dict[str, Any], user_id: str
) -> dict[str, Any] | None:
    """Insere um registro de partida na tabela partidas, atribuída a `user_id`.

    Sem fallback (D-28): desde que a coleta passou a percorrer `perfis_usuario`
    e atender mais de uma pessoa, gravar sem saber de quem é a partida seria
    silenciosamente atribuí-la a quem quer que seja o dono padrão.

    A cadência (D-57) é derivada aqui, e não em cada script de coleta: os dois
    coletores passam por esta função, então classificar num lugar só garante
    que nenhuma partida nova volte a nascer sem ritmo de jogo.
    """

    if "cadencia" not in record:
        record = {**record, **campos_de_cadencia(time_control_do_pgn(record.get("pgn")))}
    resp = client.table("partidas").insert({**record, "user_id": user_id}).execute()
    data = resp.data or []
    return data[0] if data else None


def carregar_perfis(client: Client, coluna_username: str) -> list[dict[str, Any]]:
    """Busca em perfis_usuario os perfis com a conta desta plataforma preenchida.

    `coluna_username` é ``"lichess_username"`` ou ``"chesscom_username"``.
    Cada perfil vira uma rodada de coleta independente (ver D-28).
    """

    result = (
        client.table("perfis_usuario")
        .select(f"user_id, {coluna_username}")
        .not_.is_(coluna_username, "null")
        .execute()
    )
    return result.data or []
