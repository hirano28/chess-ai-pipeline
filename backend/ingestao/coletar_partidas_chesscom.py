"""Coleta partidas públicas do Chess.com e as insere em partidas."""

from __future__ import annotations

import logging
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import (  # noqa: E402
    configurar_encoding_utf8,
    format_progress,
    log_and_print,
)
from backend.ingestao.common_ingestao import (  # noqa: E402
    already_exists,
    configure_logging,
    create_supabase_client,
    insert_game,
    with_retry,
)

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "ingestao_chesscom.log"
ARCHIVES_URL = "https://api.chess.com/pub/player/{username}/games/archives"
USER_AGENT = "chess-ai-pipeline contact: seu-email-aqui"


@dataclass(frozen=True)
class Settings:
    """Configurações da coleta Chess.com."""

    supabase_url: str
    supabase_service_role_key: str
    username: str
    months_limit: int
    user_agent: str


def load_settings() -> Settings:
    """Carrega e valida as configurações do ambiente."""

    load_dotenv(PROJECT_ROOT / ".env")
    required = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        "CHESSCOM_USERNAME": os.getenv("CHESSCOM_USERNAME"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )

    raw_limit = os.getenv("CHESSCOM_MONTHS_LIMIT", "1")
    try:
        months_limit = int(raw_limit)
    except ValueError as error:
        raise ValueError("CHESSCOM_MONTHS_LIMIT deve ser um inteiro") from error
    if months_limit < 1:
        raise ValueError("CHESSCOM_MONTHS_LIMIT deve ser maior que zero")

    return Settings(
        supabase_url=required["SUPABASE_URL"],
        supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],
        username=required["CHESSCOM_USERNAME"],
        months_limit=months_limit,
        user_agent=os.getenv("CHESSCOM_USER_AGENT", USER_AGENT),
    )


def request_json(
    url: str, headers: dict[str, str], logger: logging.Logger, description: str
) -> Any:
    """Faz GET JSON com retry para falhas de rede e HTTP."""

    def request() -> Any:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    return with_retry(request, logger, description)


def fetch_archive_urls(
    settings: Settings, logger: logging.Logger
) -> list[str]:
    """Busca os URLs mensais e retorna os meses mais recentes."""

    url = ARCHIVES_URL.format(username=settings.username)
    data = request_json(
        url,
        {"User-Agent": settings.user_agent},
        logger,
        "Busca dos arquivos mensais do Chess.com",
    )
    archives = data.get("archives", []) if isinstance(data, dict) else []
    return list(archives[-settings.months_limit :])


def fetch_games_from_archives(
    archive_urls: list[str], settings: Settings, logger: logging.Logger
) -> list[dict[str, Any]]:
    """Baixa e concatena as partidas dos arquivos mensais selecionados."""

    games: list[dict[str, Any]] = []
    headers = {"User-Agent": settings.user_agent}
    for archive_url in archive_urls:
        data = request_json(
            archive_url,
            headers,
            logger,
            f"Busca do arquivo Chess.com {archive_url}",
        )
        month_games = data.get("games", []) if isinstance(data, dict) else []
        if isinstance(month_games, list):
            games.extend(game for game in month_games if isinstance(game, dict))
    return games


def result_from_chesscom(result: str | None) -> str:
    """Converte o resultado Chess.com para o contrato da tabela partidas."""

    normalized = (result or "").strip().lower()
    if normalized in {"win", "kingofthehill", "threecheck"}:
        return "VITORIA"
    if normalized in {
        "checkmated",
        "resigned",
        "timeout",
        "lose",
        "abandoned",
        "bughousepartnerlose",
    }:
        return "DERROTA"
    if normalized in {
        "agreed",
        "stalemate",
        "repetition",
        "insufficient",
        "50move",
        "timevsinsufficient",
    }:
        return "EMPATE"
    raise ValueError(f"Resultado Chess.com desconhecido: {result}")


def player_color(game: dict[str, Any], username: str) -> str:
    """Retorna BRANCAS ou PRETAS conforme o usuário Chess.com."""

    white = game.get("white", {}) or {}
    black = game.get("black", {}) or {}
    if str(white.get("username", "")).lower() == username.lower():
        return "BRANCAS"
    if str(black.get("username", "")).lower() == username.lower():
        return "PRETAS"
    raise ValueError(f"Usuário {username} não encontrado na partida")


def eco_from_url(eco_url: str | None) -> str | None:
    """Extrai o código ECO no final de ECOUrl, quando disponível."""

    if not eco_url:
        return None
    match = re.search(r"[/_-]([A-Ea-e][0-9]{2})/?$", str(eco_url))
    return match.group(1).upper() if match else None


def game_timestamp(game: dict[str, Any]) -> str | None:
    """Converte end_time Unix do Chess.com em ISO 8601."""

    value = game.get("end_time") or game.get("start_time")
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def to_record(game: dict[str, Any], username: str) -> dict[str, Any]:
    """Mapeia uma partida Chess.com para o formato de partidas."""

    color = player_color(game, username)
    own = game["white"] if color == "BRANCAS" else game["black"]
    opponent = game["black"] if color == "BRANCAS" else game["white"]
    external_id = game.get("url") or game.get("uuid")
    if not external_id:
        raise ValueError("Partida Chess.com sem url ou uuid")

    return {
        "plataforma": "CHESSCOM",
        "external_id": str(external_id),
        "pgn": game.get("pgn", ""),
        "data_partida": game_timestamp(game),
        "resultado": result_from_chesscom(own.get("result")),
        "cor_jogada": color,
        "rating_proprio": own.get("rating"),
        "rating_oponente": opponent.get("rating"),
        "eco_abertura": eco_from_url(game.get("ECOUrl")),
        "status_processamento": "pendente",
    }


def main() -> None:
    """Coleta as partidas e imprime o resumo."""

    logger = configure_logging(LOG_PATH, "ingestao_chesscom")
    inserted = existing = failed = 0
    try:
        settings = load_settings()
        client = create_supabase_client(
            settings.supabase_url, settings.supabase_service_role_key
        )
        archive_urls = fetch_archive_urls(settings, logger)
        games = fetch_games_from_archives(archive_urls, settings, logger)
        total = len(games)
        start_time = time.time()
        for index, game in enumerate(games, start=1):
            try:
                record = to_record(game, settings.username)
                if already_exists(client, record["external_id"]):
                    existing += 1
                else:
                    insert_game(client, record)
                    inserted += 1
            except Exception:
                failed += 1
                logger.error(
                    "Falha completa na partida Chess.com %s:\n%s",
                    game.get("url", game.get("uuid", "desconhecida")),
                    traceback.format_exc(),
                )
            log_and_print(
                logger,
                format_progress(
                    "Chess.com", "partidas", index, total, time.time() - start_time
                ),
            )
    except Exception:
        failed += 1
        logger.error("Falha geral na coleta Chess.com:\n%s", traceback.format_exc())

    print(f"Partidas novas inseridas: {inserted}")
    print(f"Partidas já existentes: {existing}")
    print(f"Partidas com falha: {failed}")


if __name__ == "__main__":
    main()
