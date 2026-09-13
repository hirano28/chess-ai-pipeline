"""Preenche fen_antes_lance nos lances_criticos que existiam antes de D-27.

Execução única: `analisar_partidas.py` já grava fen_antes_lance em toda linha
nova a partir de D-27. Este script cobre só o histórico anterior, recalculando
o FEN a partir do PGN da partida (mesma lógica de travessia de processar_partida,
sem chamar o Stockfish - não precisamos de avaliação nenhuma aqui).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import chess
from supabase import Client, create_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.analise_engine.analisar_partidas import (  # noqa: E402
    configure_logging,
    load_settings,
    load_validated_game,
)
from backend.common.progress import configurar_encoding_utf8  # noqa: E402

configurar_encoding_utf8()

PAGE_SIZE = 1000


def fetch_lances_sem_fen(client: Client, logger: logging.Logger) -> list[dict[str, Any]]:
    """Busca id/partida_id/numero_lance de todo lance ainda sem fen_antes_lance."""

    registros: list[dict[str, Any]] = []
    offset = 0
    while True:
        resposta = (
            client.table("lances_criticos")
            .select("id, partida_id, numero_lance")
            .is_("fen_antes_lance", "null")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        pagina = resposta.data or []
        registros.extend(pagina)
        logger.info(
            "Página de lances sem FEN carregada: %d registros (offset %d)",
            len(pagina),
            offset,
        )
        if len(pagina) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return registros


def mapear_fen_antes_por_lance(pgn: str, cor_jogada: str, partida_id: Any) -> dict[int, str]:
    """Reconstrói, a partir do PGN, o FEN de antes de cada lance do jogador.

    Mesma regra de `processar_partida` em analisar_partidas.py: `numero_lance`
    é o `fullmove_number` no momento em que o jogador de `cor_jogada` move.
    """

    game = load_validated_game({"id": partida_id, "pgn": pgn, "cor_jogada": cor_jogada})
    board = game.board()
    fen_por_lance: dict[int, str] = {}
    for move in game.mainline_moves():
        playing_color = "BRANCAS" if board.turn == chess.WHITE else "PRETAS"
        if playing_color == cor_jogada:
            fen_por_lance[board.fullmove_number] = board.fen()
        board.push(move)
    return fen_por_lance


def run_backfill(client: Client, logger: logging.Logger) -> tuple[int, int, int]:
    """Executa o backfill e retorna (atualizados, sem_correspondencia, falhas)."""

    lances = fetch_lances_sem_fen(client, logger)
    lances_por_partida: dict[Any, list[dict[str, Any]]] = {}
    for lance in lances:
        lances_por_partida.setdefault(lance["partida_id"], []).append(lance)

    atualizados = sem_correspondencia = falhas = 0
    for partida_id, lances_da_partida in lances_por_partida.items():
        try:
            partida = (
                client.table("partidas")
                .select("pgn, cor_jogada")
                .eq("id", partida_id)
                .single()
                .execute()
            ).data
            fen_por_lance = mapear_fen_antes_por_lance(
                partida["pgn"], partida["cor_jogada"], partida_id
            )
        except Exception as error:
            falhas += len(lances_da_partida)
            logger.exception(
                "Falha ao reconstruir FEN da partida %s: %s", partida_id, error
            )
            continue

        for lance in lances_da_partida:
            fen = fen_por_lance.get(lance["numero_lance"])
            if not fen:
                sem_correspondencia += 1
                logger.warning(
                    "Lance %s (partida %s, numero_lance %s) sem FEN correspondente no PGN",
                    lance["id"],
                    partida_id,
                    lance["numero_lance"],
                )
                continue
            try:
                client.table("lances_criticos").update(
                    {"fen_antes_lance": fen}
                ).eq("id", lance["id"]).execute()
                atualizados += 1
            except Exception as error:
                falhas += 1
                logger.exception(
                    "Falha ao atualizar fen_antes_lance do lance %s: %s",
                    lance["id"],
                    error,
                )

    logger.info(
        "Backfill concluído: %d atualizados, %d sem correspondência, %d falhas",
        atualizados,
        sem_correspondencia,
        falhas,
    )
    return atualizados, sem_correspondencia, falhas


def main() -> None:
    """Executa o backfill uma única vez e imprime o resumo."""

    logger = configure_logging()
    try:
        settings = load_settings()
        client = create_client(
            settings.supabase_url, settings.supabase_service_role_key
        )
        atualizados, sem_correspondencia, falhas = run_backfill(client, logger)
    except Exception as error:
        logger.exception("Falha na execução do backfill: %s", error)
        print("Backfill interrompido por falha geral; consulte backend/logs/ingestao.log")
        return

    print(f"Lances atualizados: {atualizados}")
    print(f"Lances sem correspondência no PGN: {sem_correspondencia}")
    print(f"Lances com falha: {falhas}")


if __name__ == "__main__":
    main()
