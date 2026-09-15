"""Preenche o ECO de partidas existentes sem alterar os demais campos."""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import configurar_encoding_utf8  # noqa: E402

configurar_encoding_utf8()

try:
    from .coletar_partidas import (
        Settings,
        configure_logging,
        fetch_games,
        load_settings,
    )
except ImportError:
    from coletar_partidas import Settings, configure_logging, fetch_games, load_settings

PAGE_SIZE = 1000


def eco_from_pgn(pgn: str | None) -> str | None:
    """Extrai o código ECO do cabeçalho [ECO "..."] do PGN."""
    if not pgn:
        return None
    match = re.search(r'\[ECO\s+"([A-Ea-e][0-9]{2})"', pgn)
    return match.group(1).upper() if match else None


def fetch_missing_records(
    client: Client, logger: logging.Logger
) -> list[dict[str, Any]]:
    """Busca todas as partidas sem ECO, selecionando id, external_id, plataforma e pgn."""

    records: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            client.table("partidas")
            .select("id, external_id, plataforma, pgn")
            .is_("eco_abertura", "null")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        records.extend(page)
        logger.info(
            "Página de partidas sem ECO carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return records


def game_index(games: list[dict[str, Any]]) -> dict[str, str]:
    """Indexa partidas da API por external_id quando há um ECO válido."""

    indexed: dict[str, str] = {}
    for game in games:
        external_id = game.get("id")
        opening = game.get("opening")
        eco = opening.get("eco") if isinstance(opening, dict) else None
        if external_id and eco:
            indexed[str(external_id)] = str(eco)
    return indexed


def update_eco(client: Client, partida_id: str, eco: str) -> None:
    """Atualiza somente o ECO da partida ainda sem esse valor."""

    (
        client.table("partidas")
        .update({"eco_abertura": eco})
        .eq("id", partida_id)
        .is_("eco_abertura", "null")
        .execute()
    )


def run_backfill(
    client: Client, settings: Settings | None, logger: logging.Logger
) -> tuple[int, int, int]:
    """Executa o backfill e retorna atualizadas, sem correspondência e falhas."""

    missing_records = fetch_missing_records(client, logger)
    if not missing_records:
        logger.info("Nenhuma partida sem eco_abertura encontrada.")
        return 0, 0, 0

    games_by_id: dict[str, str] | None = None
    updated = unmatched = failed = 0

    for record in missing_records:
        partida_id = record.get("id")
        pgn = record.get("pgn")
        eco = eco_from_pgn(pgn)

        # Se não encontrou no PGN e a partida for Lichess, consulta API externa caso settings exista
        if not eco and record.get("plataforma") == "LICHESS" and settings is not None:
            if games_by_id is None:
                try:
                    games = list(fetch_games(settings, logger))
                    games_by_id = game_index(games)
                except Exception as error:
                    logger.warning("Não foi possível buscar partidas na API do Lichess: %s", error)
                    games_by_id = {}
            external_id = record.get("external_id")
            eco = games_by_id.get(str(external_id)) if external_id else None

        if not eco:
            unmatched += 1
            continue

        try:
            update_eco(client, str(partida_id), eco)
            updated += 1
        except Exception as error:
            failed += 1
            logger.exception(
                "Falha ao atualizar eco_abertura da partida %s: %s",
                partida_id,
                error,
            )

    logger.info(
        "Backfill concluído: %d atualizadas, %d sem correspondência, %d falhas",
        updated,
        unmatched,
        failed,
    )
    return updated, unmatched, failed


def main() -> None:
    """Executa o backfill uma única vez e imprime o resumo."""

    logger = configure_logging()
    load_dotenv(PROJECT_ROOT / ".env")
    settings: Settings | None = None
    try:
        settings = load_settings()
    except Exception as error:
        logger.warning("Settings do Lichess não carregadas (seguindo com fallback PGN): %s", error)

    try:
        client = create_client(
            os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        )
        updated, unmatched, failed = run_backfill(client, settings, logger)
    except Exception as error:
        logger.exception("Falha na execução do backfill: %s", error)
        print("Backfill interrompido por falha geral; consulte backend/logs/ingestao.log")
        return

    print(f"Partidas atualizadas: {updated}")
    print(f"Partidas sem correspondência: {unmatched}")
    print(f"Partidas com falha: {failed}")


if __name__ == "__main__":
    main()
