"""Coleta partidas do Lichess e as insere na tabela ``partidas`` do Supabase."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import chess
import chess.pgn
import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import format_progress, log_and_print  # noqa: E402
from backend.ingestao.common_ingestao import (  # noqa: E402
    already_exists,
    configure_logging,
    create_supabase_client,
    insert_game,
    with_retry,
)
LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "ingestao.log"
LICHESS_GAMES_URL = "https://lichess.org/api/games/user/{username}"


@dataclass(frozen=True)
class Settings:
    """Configurações necessárias para a coleta."""

    supabase_url: str
    supabase_service_role_key: str
    lichess_token: str
    lichess_username: str
    limit: int


def load_settings() -> Settings:
    """Carrega e valida as configurações do ambiente."""

    load_dotenv(PROJECT_ROOT / ".env")
    required = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        "LICHESS_TOKEN": os.getenv("LICHESS_TOKEN"),
        "LICHESS_USERNAME": os.getenv("LICHESS_USERNAME"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )

    raw_limit = os.getenv("LICHESS_GAMES_LIMIT", "20")
    try:
        limit = int(raw_limit)
    except ValueError as error:
        raise ValueError("LICHESS_GAMES_LIMIT deve ser um inteiro") from error
    if limit < 1:
        raise ValueError("LICHESS_GAMES_LIMIT deve ser maior que zero")

    return Settings(
        supabase_url=required["SUPABASE_URL"],
        supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],
        lichess_token=required["LICHESS_TOKEN"],
        lichess_username=required["LICHESS_USERNAME"],
        limit=limit,
    )


def fetch_games(settings: Settings, logger: logging.Logger) -> Iterator[dict[str, Any]]:
    """Busca partidas do usuário no endpoint NDJSON do Lichess."""

    url = LICHESS_GAMES_URL.format(username=settings.lichess_username)
    headers = {
        "Accept": "application/x-ndjson",
        "Authorization": f"Bearer {settings.lichess_token}",
    }
    def request_games() -> requests.Response:
        response = requests.get(
            url,
            headers=headers,
            params={"max": settings.limit, "opening": "true"},
            timeout=30,
        )
        response.raise_for_status()
        return response

    response = with_retry(
        request_games,
        logger,
        "Busca de partidas no Lichess",
    )
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            game = json.loads(line)
        except json.JSONDecodeError as error:
            logger.error("Linha NDJSON inválida recebida do Lichess: %s", error)
            continue
        if isinstance(game, dict):
            yield game


def player_data(game: dict[str, Any], color: str) -> dict[str, Any]:
    """Retorna os dados do jogador na cor informada."""

    return game.get("players", {}).get(color, {}) or {}


def player_name(player: dict[str, Any]) -> str | None:
    """Extrai o nome de usuário de um jogador, inclusive contas anônimas."""

    user = player.get("user", {}) or {}
    return user.get("name") or user.get("id")


def game_result(game: dict[str, Any], own_color: str) -> str:
    """Converte o resultado para ``vitoria``, ``derrota`` ou ``empate``."""

    winner = game.get("winner")
    if winner is None:
        return "empate"
    return "vitoria" if winner == own_color else "derrota"


def normalized_result(result: str) -> str:
    """Converte um resultado para o valor aceito pela tabela ``partidas``."""

    result_map = {
        "vitoria": "VITORIA",
        "win": "VITORIA",
        "derrota": "DERROTA",
        "loss": "DERROTA",
        "empate": "EMPATE",
        "draw": "EMPATE",
    }
    try:
        return result_map[result.strip().lower()]
    except KeyError as error:
        raise ValueError(f"Resultado de partida inválido: {result}") from error


def normalized_color(color: str) -> str:
    """Converte a cor do Lichess para o valor aceito pela tabela ``partidas``."""

    color_map = {"white": "BRANCAS", "black": "PRETAS"}
    try:
        return color_map[color.strip().lower()]
    except KeyError as error:
        raise ValueError(f"Cor de partida inválida: {color}") from error


def game_timestamp(game: dict[str, Any]) -> str | None:
    """Converte ``createdAt`` em ISO 8601, quando fornecido pelo Lichess."""

    created_at = game.get("createdAt")
    if not created_at:
        return None
    try:
        return datetime.fromtimestamp(created_at / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def build_pgn(game: dict[str, Any]) -> str:
    """Obtém o PGN recebido ou o reconstrói a partir dos lances da partida."""

    if isinstance(game.get("pgn"), str) and game["pgn"].strip():
        return game["pgn"]

    board = chess.Board()
    pgn_game = chess.pgn.Game()
    headers = pgn_game.headers
    headers["Event"] = "Lichess game"
    headers["Site"] = f"https://lichess.org/{game.get('id', '')}"
    headers["Date"] = datetime.fromtimestamp(
        game.get("createdAt", 0) / 1000, tz=timezone.utc
    ).strftime("%Y.%m.%d")
    headers["White"] = player_name(player_data(game, "white")) or "?"
    headers["Black"] = player_name(player_data(game, "black")) or "?"
    headers["Result"] = pgn_result(game)
    node = pgn_game
    for san in str(game.get("moves", "")).split():
        try:
            move = board.parse_san(san)
            node = node.add_variation(move)
            board.push(move)
        except (ValueError, chess.InvalidMoveError):
            break
    return str(pgn_game)


def pgn_result(game: dict[str, Any]) -> str:
    """Retorna o resultado no formato padrão de PGN."""

    winner = game.get("winner")
    if winner == "white":
        return "1-0"
    if winner == "black":
        return "0-1"
    return "1/2-1/2"


def to_record(game: dict[str, Any], username: str) -> dict[str, Any]:
    """Transforma uma partida da API no registro da tabela ``partidas``."""

    white = player_data(game, "white")
    black = player_data(game, "black")
    own_color = (
        "white"
        if (player_name(white) or "").lower() == username.lower()
        else "black"
    )
    own_player = white if own_color == "white" else black
    opponent = black if own_color == "white" else white
    opening = game.get("opening", {}) or {}

    return {
        "plataforma": "LICHESS",
        "external_id": game["id"],
        "pgn": build_pgn(game),
        "data_partida": game_timestamp(game),
        "resultado": normalized_result(game_result(game, own_color)),
        "cor_jogada": normalized_color(own_color),
        "rating_proprio": own_player.get("rating"),
        "rating_oponente": opponent.get("rating"),
        "eco_abertura": opening.get("eco") if isinstance(opening, dict) else None,
        "status_processamento": "pendente",
    }


def main() -> None:
    """Executa a coleta e imprime o resumo da operação."""

    logger = configure_logging()
    inserted = existing = failed = 0
    try:
        settings = load_settings()
        client = create_supabase_client(
            settings.supabase_url, settings.supabase_service_role_key
        )
        games = list(fetch_games(settings, logger))
        total = len(games)
        start_time = time.time()
        for index, game in enumerate(games, start=1):
            try:
                external_id = str(game["id"])
                if already_exists(client, external_id):
                    existing += 1
                    continue
                insert_game(client, to_record(game, settings.lichess_username))
                inserted += 1
            except Exception as error:
                failed += 1
                logger.exception(
                    "Falha ao processar a partida %s: %s",
                    game.get("id", "desconhecida"),
                    error,
                )
            log_and_print(
                logger,
                format_progress(
                    "Coleta", "partidas", index, total, time.time() - start_time
                ),
            )
    except Exception as error:
        failed += 1
        logger.exception("Falha na execução da ingestão: %s", error)

    print(f"Partidas novas inseridas: {inserted}")
    print(f"Partidas já existentes: {existing}")
    print(f"Partidas com falha: {failed}")


if __name__ == "__main__":
    main()