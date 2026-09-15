"""Backfill de tempos de relógio (tempos_lance) para partidas do Chess.com.

Lê as tags [%clk ...] presentes nos comentários do PGN de cada partida do
Chess.com e povoa a tabela tempos_lance com tempo_restante_seg e tempo_gasto_seg
por lance e cor (Fase 15 do Roadmap).
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import chess.pgn
from dotenv import load_dotenv
from supabase import Client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import (  # noqa: E402
    configurar_encoding_utf8,
    format_progress,
    log_and_print,
)
from backend.ingestao.common_ingestao import (  # noqa: E402
    configure_logging,
    create_supabase_client,
)

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "backfill_tempos_chesscom.log"
CLK_PATTERN = re.compile(r"\[%clk\s+(\d+):(\d+):(\d+(?:\.\d+)?)\]")
BATCH_SIZE = 500
PAGE_SIZE = 1000


def parse_time_control(tc_header: str | None) -> tuple[float, float]:
    """Extrai (initial_seg, increment_seg) a partir do header TimeControl do PGN."""
    if not tc_header or tc_header == "-":
        return 300.0, 0.0  # Fallback padrão 5 min
    parts = tc_header.strip().split("+")
    try:
        initial = float(parts[0])
        increment = float(parts[1]) if len(parts) > 1 else 0.0
        return initial, increment
    except (ValueError, IndexError):
        return 300.0, 0.0


def extrair_tempos_pgn_chesscom(
    pgn: str, partida_id: Any
) -> list[dict[str, Any]]:
    """Extrai os registros de tempos_lance de uma partida a partir do seu PGN."""
    if not pgn or not pgn.strip():
        return []

    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return []

    initial_seg, increment_seg = parse_time_control(game.headers.get("TimeControl"))

    # Relógio anterior para cada cor inicia no tempo inicial do controle
    anterior: dict[str, float] = {"BRANCAS": initial_seg, "PRETAS": initial_seg}
    primeiro_lance: dict[str, bool] = {"BRANCAS": True, "PRETAS": True}

    rows: list[dict[str, Any]] = []
    for ply, node in enumerate(game.mainline()):
        numero_lance = ply // 2 + 1
        cor = "BRANCAS" if ply % 2 == 0 else "PRETAS"
        comment = node.comment or ""
        match = CLK_PATTERN.search(comment)
        if not match:
            continue

        horas, minutos, segundos = match.groups()
        tempo_restante_seg = (
            int(horas) * 3600 + int(minutos) * 60 + float(segundos)
        )

        # Se o controle era desconhecido ou diferente, ajusta pelo primeiro lance
        if primeiro_lance[cor]:
            primeiro_lance[cor] = False
            if tempo_restante_seg > anterior[cor]:
                anterior[cor] = tempo_restante_seg

        tempo_gasto_seg = max(
            0.0, anterior[cor] - tempo_restante_seg + increment_seg
        )
        anterior[cor] = tempo_restante_seg

        rows.append(
            {
                "partida_id": partida_id,
                "numero_lance": numero_lance,
                "cor": cor,
                "tempo_restante_seg": round(tempo_restante_seg, 2),
                "tempo_gasto_seg": round(tempo_gasto_seg, 2),
            }
        )

    return rows


def fetch_partidas_chesscom(
    client: Client,
    partida_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Busca partidas do Chess.com que possuem PGN salvo."""
    query = client.table("partidas").select("id, external_id, pgn").eq("plataforma", "CHESSCOM")
    if partida_id:
        query = query.eq("id", partida_id)

    partidas: list[dict[str, Any]] = []
    offset = 0
    while True:
        resp = query.range(offset, offset + PAGE_SIZE - 1).execute()
        page = resp.data or []
        partidas.extend(page)
        if len(page) < PAGE_SIZE or (limit and len(partidas) >= limit):
            break
        offset += PAGE_SIZE

    if limit:
        partidas = partidas[:limit]
    return partidas


def executar_backfill(
    client: Client,
    dry_run: bool = False,
    partida_id: str | None = None,
    limit: int | None = None,
    logger: logging.Logger | None = None,
) -> tuple[int, int, int]:
    """Executa a extração e persistência de tempos de relógio para partidas Chess.com."""
    logger = logger or logging.getLogger("backfill_tempos_chesscom")
    partidas = fetch_partidas_chesscom(client, partida_id=partida_id, limit=limit)
    total = len(partidas)
    log_and_print(logger, f"Encontradas {total} partidas do Chess.com para processar tempos.")

    processadas = 0
    total_linhas = 0
    falhas = 0
    start_time = time.time()

    buffer_tempos: list[dict[str, Any]] = []

    for index, partida in enumerate(partidas, start=1):
        pid = partida["id"]
        pgn = partida.get("pgn", "")
        try:
            tempos = extrair_tempos_pgn_chesscom(pgn, pid)
            if tempos:
                total_linhas += len(tempos)
                buffer_tempos.extend(tempos)
                processadas += 1

            if not dry_run and len(buffer_tempos) >= BATCH_SIZE:
                client.table("tempos_lance").upsert(
                    buffer_tempos, on_conflict="partida_id,numero_lance,cor"
                ).execute()
                buffer_tempos.clear()

        except Exception as err:
            falhas += 1
            logger.error("Erro ao extrair tempos da partida %s: %s", pid, err)

        if index % 10 == 0 or index == total:
            log_and_print(
                logger,
                format_progress(
                    "Extração %clk Chess.com", "partidas", index, total, time.time() - start_time
                ),
            )

    if not dry_run and buffer_tempos:
        client.table("tempos_lance").upsert(
            buffer_tempos, on_conflict="partida_id,numero_lance,cor"
        ).execute()
        buffer_tempos.clear()

    return processadas, total_linhas, falhas


def main() -> None:
    """CLI do backfill de tempos de relógio do Chess.com."""
    parser = argparse.ArgumentParser(
        description="Backfill de tempos de relógio para partidas do Chess.com."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas simula a extração sem gravar no banco.",
    )
    parser.add_argument(
        "--partida-id",
        help="Processa apenas uma partida específica por UUID.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limita o número de partidas processadas.",
    )
    args = parser.parse_args()

    logger = configure_logging(LOG_PATH, "backfill_tempos_chesscom")
    load_dotenv(PROJECT_ROOT / ".env")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        print("Erro: SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY não definidos.")
        sys.exit(1)

    client = create_supabase_client(supabase_url, supabase_key)
    processadas, total_linhas, falhas = executar_backfill(
        client,
        dry_run=args.dry_run,
        partida_id=args.partida_id,
        limit=args.limit,
        logger=logger,
    )

    modo = "[DRY-RUN] " if args.dry_run else ""
    print(
        f"\n{modo}Concluído: {processadas} partidas processadas, "
        f"{total_linhas} linhas de tempos_lance geradas, {falhas} falhas."
    )


if __name__ == "__main__":
    main()

