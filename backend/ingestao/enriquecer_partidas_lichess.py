"""Enriquece partidas do Lichess com precisão, clocks e divisão de fases.

Etapa 1 (atual): modo --inspecionar para descobrir a estrutura real do JSON
retornado pelo endpoint de exportação de partida do Lichess, antes de
implementar o parsing definitivo e a inserção no banco (Etapa 2).
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chess
import chess.pgn
import requests
from dotenv import load_dotenv
from supabase import Client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import format_progress, log_and_print  # noqa: E402
from backend.ingestao.common_ingestao import (  # noqa: E402
    configure_logging,
    create_supabase_client,
    with_retry,
)

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "enriquecer_lichess.log"
GAME_EXPORT_URL = (
    "https://lichess.org/game/export/{external_id}"
    "?evals=1&accuracy=1&clocks=1&division=1&opening=1"
)
CLK_PATTERN = re.compile(r"\[%clk\s+(\d+):(\d+):(\d+(?:\.\d+)?)\]")
PAGE_SIZE = 1000


@dataclass(frozen=True)
class Settings:
    """Configurações do Supabase e do jogador rastreado."""

    supabase_url: str
    supabase_service_role_key: str
    lichess_username: str | None


def load_settings() -> Settings:
    """Carrega e valida as configurações do ambiente."""

    load_dotenv(PROJECT_ROOT / ".env")
    required = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )
    return Settings(
        supabase_url=required["SUPABASE_URL"],  # type: ignore[arg-type]
        supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],  # type: ignore[arg-type]
        lichess_username=os.getenv("LICHESS_USERNAME") or None,
    )


def fetch_one_lichess_external_id(client: Client) -> str:
    """Busca um external_id qualquer de uma partida já coletada do Lichess."""

    response = (
        client.table("partidas")
        .select("external_id")
        .eq("plataforma", "LICHESS")
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise ValueError("Nenhuma partida com plataforma='LICHESS' foi encontrada.")
    external_id = rows[0].get("external_id")
    if not external_id:
        raise ValueError("A partida encontrada não possui external_id.")
    return str(external_id)


def fetch_game_export(external_id: str, logger: logging.Logger) -> dict[str, Any]:
    """Chama o endpoint de exportação do Lichess e retorna o JSON completo."""

    url = GAME_EXPORT_URL.format(external_id=external_id)

    def request() -> dict[str, Any]:
        response = requests.get(
            url, headers={"Accept": "application/json"}, timeout=30
        )
        response.raise_for_status()
        return response.json()

    return with_retry(request, logger, f"Exportação da partida {external_id}")


def inspecionar() -> None:
    """Busca uma partida real e imprime o JSON bruto do Lichess (Etapa 1)."""

    logger = configure_logging(LOG_PATH, "enriquecer_partidas_lichess")
    settings = load_settings()
    client = create_supabase_client(
        settings.supabase_url, settings.supabase_service_role_key
    )
    external_id = fetch_one_lichess_external_id(client)
    logger.info("Inspecionando partida Lichess external_id=%s", external_id)
    game_export = fetch_game_export(external_id, logger)
    print(json.dumps(game_export, indent=2, ensure_ascii=False))


def fetch_partida_row(client: Client, external_id: str) -> dict[str, Any] | None:
    """Busca a linha da partida (com PGN salvo) por external_id."""

    response = (
        client.table("partidas")
        .select("external_id, pgn, cor_jogada")
        .eq("plataforma", "LICHESS")
        .eq("external_id", external_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def extrair_sans_de_moves(moves: str) -> list[str]:
    """Deriva a lista de lances em SAN do campo `moves` via python-chess."""

    board = chess.Board()
    sans: list[str] = []
    for token in moves.split():
        move = board.parse_san(token)
        sans.append(board.san(move))
        board.push(move)
    return sans


def extrair_clk_segundos(pgn: str) -> list[float | None]:
    """Extrai os segundos de cada tag %clk do PGN, na ordem dos lances."""

    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return []
    valores: list[float | None] = []
    for node in game.mainline():
        match = CLK_PATTERN.search(node.comment or "")
        if match is None:
            valores.append(None)
            continue
        horas, minutos, segundos = match.groups()
        valores.append(int(horas) * 3600 + int(minutos) * 60 + float(segundos))
    return valores


def validar_clocks(external_id: str) -> None:
    """Valida visualmente o array `clocks` da API contra o PGN salvo (Etapa 2a)."""

    logger = configure_logging(LOG_PATH, "enriquecer_partidas_lichess")
    settings = load_settings()
    client = create_supabase_client(
        settings.supabase_url, settings.supabase_service_role_key
    )
    row = fetch_partida_row(client, external_id)
    game_export = fetch_game_export(external_id, logger)

    sans = extrair_sans_de_moves(str(game_export.get("moves", "")))
    clocks = game_export.get("clocks") or []
    clock_info = game_export.get("clock") or {}
    initial = clock_info.get("initial")

    pgn = (row or {}).get("pgn")
    clk_segundos = extrair_clk_segundos(pgn) if isinstance(pgn, str) else []
    tem_clk = any(valor is not None for valor in clk_segundos)

    print(f"Partida: {external_id}")
    print(f"PGN salvo encontrado no banco: {'sim' if pgn else 'não'}")
    print(f"PGN contém tags %clk: {'sim' if tem_clk else 'não'}")
    print(f"clock.initial (s): {initial}")
    print(f"clocks[0] cru (centissegundos): {clocks[0] if clocks else 'ausente'}")
    if clocks and initial is not None:
        print(
            f"clocks[0]/100 = {clocks[0] / 100:.2f}s  vs  clock.initial = {initial}s"
            f"  => índice 0 {'≈ tempo inicial' if abs(clocks[0] / 100 - initial) < 1 else 'já é pós-lance'}"
        )
    print()

    cabecalho = (
        f"{'ply':>3} | {'lance#':>6} | {'cor':^7} | {'san':^8} | "
        f"{'clocks_cru':>10} | {'clk_api_s':>9} | {'clk_pgn_s':>9}"
    )
    print(cabecalho)
    print("-" * len(cabecalho))
    for ply in range(min(10, len(sans))):
        numero_lance = ply // 2 + 1
        cor = "BRANCAS" if ply % 2 == 0 else "PRETAS"
        cru = clocks[ply] if ply < len(clocks) else None
        api_s = f"{cru / 100:.2f}" if cru is not None else "—"
        pgn_s = (
            f"{clk_segundos[ply]:.2f}"
            if ply < len(clk_segundos) and clk_segundos[ply] is not None
            else "—"
        )
        print(
            f"{ply:>3} | {numero_lance:>6} | {cor:^7} | {sans[ply]:^8} | "
            f"{str(cru if cru is not None else '—'):>10} | {api_s:>9} | {pgn_s:>9}"
        )


def montar_tempos_lance(
    partida_id: Any,
    clocks: list[int],
    initial_seg: float,
    increment_seg: float,
) -> list[dict[str, Any]]:
    """Constrói as linhas de tempos_lance a partir do array clocks da API."""

    rows: list[dict[str, Any]] = []
    for ply, centis in enumerate(clocks):
        numero_lance = ply // 2 + 1
        cor = "BRANCAS" if ply % 2 == 0 else "PRETAS"
        tempo_restante_seg = centis / 100
        # Relógio anterior da MESMA cor está dois plies atrás; senão é o inicial.
        idx_anterior = ply - 2
        anterior_restante = (
            clocks[idx_anterior] / 100 if idx_anterior >= 0 else initial_seg
        )
        # max(0, ...) absorve artefatos de compensação de lag que geram negativos.
        tempo_gasto_seg = max(
            0.0, anterior_restante - tempo_restante_seg + increment_seg
        )
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


def identificar_cor_rastreada(
    game_export: dict[str, Any], username: str | None
) -> str | None:
    """Descobre se o jogador rastreado jogou de brancas ou pretas."""

    if not username:
        return None
    players = game_export.get("players", {}) or {}
    white_name = ((players.get("white") or {}).get("user") or {}).get("name") or ""
    black_name = ((players.get("black") or {}).get("user") or {}).get("name") or ""
    alvo = username.lower()
    if white_name.lower() == alvo:
        return "white"
    if black_name.lower() == alvo:
        return "black"
    return None


def montar_metricas(
    partida_id: Any, game_export: dict[str, Any], username: str | None
) -> dict[str, Any] | None:
    """Constrói a linha de metricas_lichess_partida quando há análise dos dois lados."""

    players = game_export.get("players", {}) or {}
    white_analysis = (players.get("white") or {}).get("analysis")
    black_analysis = (players.get("black") or {}).get("analysis")
    if not white_analysis or not black_analysis:
        return None

    cor = identificar_cor_rastreada(game_export, username)
    if cor is None:
        return None

    proprio = white_analysis if cor == "white" else black_analysis
    oponente = black_analysis if cor == "white" else white_analysis
    division = game_export.get("division", {}) or {}
    # division.middle/end são índices de PLY (não número de lance).
    fase_abertura_fim_ply = division.get("middle")
    fase_meiojogo_fim_ply = division.get("end")

    return {
        "partida_id": partida_id,
        "precisao_propria": proprio.get("accuracy"),
        "precisao_oponente": oponente.get("accuracy"),
        "imprecisoes": proprio.get("inaccuracy"),
        "erros": proprio.get("mistake"),
        "blunders": proprio.get("blunder"),
        "acpl": proprio.get("acpl"),
        "fase_abertura_fim": fase_abertura_fim_ply,
        "fase_meiojogo_fim": fase_meiojogo_fim_ply,
    }


def _imprimir_preview_tempos(
    game_export: dict[str, Any], tempos_rows: list[dict[str, Any]]
) -> None:
    """Imprime os 10 primeiros registros que SERIAM inseridos em tempos_lance."""

    sans = extrair_sans_de_moves(str(game_export.get("moves", "")))
    clock_info = game_export.get("clock", {}) or {}
    print(
        f"clock.initial={clock_info.get('initial')}s "
        f"increment={clock_info.get('increment')}s"
    )
    cabecalho = (
        f"{'ply':>3} | {'lance#':>6} | {'cor':^7} | {'san':^8} | "
        f"{'restante_s':>10} | {'gasto_s':>8}"
    )
    print(cabecalho)
    print("-" * len(cabecalho))
    for ply in range(min(10, len(tempos_rows))):
        row = tempos_rows[ply]
        san = sans[ply] if ply < len(sans) else "—"
        print(
            f"{ply:>3} | {row['numero_lance']:>6} | {row['cor']:^7} | {san:^8} | "
            f"{row['tempo_restante_seg']:>10.2f} | {row['tempo_gasto_seg']:>8.2f}"
        )


def enriquecer_partida(
    client: Client,
    partida: dict[str, Any],
    game_export: dict[str, Any],
    username: str | None,
    dry_run: bool,
) -> tuple[bool, bool]:
    """Grava (ou simula) tempos_lance e metricas_lichess_partida de uma partida."""

    partida_id = partida["id"]
    clocks = game_export.get("clocks") or []
    clock_info = game_export.get("clock", {}) or {}
    initial_seg = clock_info.get("initial") or 0
    increment_seg = clock_info.get("increment") or 0

    tempos_rows = (
        montar_tempos_lance(partida_id, clocks, initial_seg, increment_seg)
        if clocks
        else []
    )
    metricas_row = montar_metricas(partida_id, game_export, username)

    if dry_run:
        print(f"\n[DRY-RUN] Partida id={partida_id} external_id={partida.get('external_id')}")
        if tempos_rows:
            _imprimir_preview_tempos(game_export, tempos_rows)
            print(f"(total de {len(tempos_rows)} linhas seriam upsertadas em tempos_lance)")
        else:
            print("Sem array clocks: nada a inserir em tempos_lance.")
        if metricas_row:
            print("metricas_lichess_partida que seria upsertada:")
            print(json.dumps(metricas_row, indent=2, ensure_ascii=False))
        else:
            print("Sem análise dos dois lados / jogador não identificado: nada em metricas_lichess_partida.")
        return bool(tempos_rows), bool(metricas_row)

    gravou_clocks = False
    gravou_metricas = False
    if tempos_rows:
        client.table("tempos_lance").upsert(
            tempos_rows, on_conflict="partida_id,numero_lance,cor"
        ).execute()
        gravou_clocks = True
    if metricas_row:
        client.table("metricas_lichess_partida").upsert(
            metricas_row, on_conflict="partida_id"
        ).execute()
        gravou_metricas = True
    return gravou_clocks, gravou_metricas


def _fetch_partida_ids_da_tabela(client: Client, tabela: str) -> set[Any]:
    """Coleta o conjunto de partida_id já presentes em uma tabela filha."""

    ids: set[Any] = set()
    offset = 0
    while True:
        response = (
            client.table(tabela)
            .select("partida_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        ids.update(item["partida_id"] for item in page if item.get("partida_id") is not None)
        if len(page) < PAGE_SIZE:
            return ids
        offset += PAGE_SIZE


def selecionar_partidas(
    client: Client, external_id: str | None
) -> list[dict[str, Any]]:
    """Seleciona partidas Lichess a enriquecer (ou uma específica por external_id)."""

    if external_id:
        response = (
            client.table("partidas")
            .select("id, external_id")
            .eq("plataforma", "LICHESS")
            .eq("external_id", external_id)
            .limit(1)
            .execute()
        )
        return response.data or []

    partidas: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            client.table("partidas")
            .select("id, external_id")
            .eq("plataforma", "LICHESS")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        partidas.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    com_tempos = _fetch_partida_ids_da_tabela(client, "tempos_lance")
    com_metricas = _fetch_partida_ids_da_tabela(client, "metricas_lichess_partida")
    # Reprocessa enquanto faltar registro em QUALQUER uma das duas tabelas.
    return [
        partida
        for partida in partidas
        if partida["id"] not in com_tempos or partida["id"] not in com_metricas
    ]


def enriquecer(external_id: str | None = None, dry_run: bool = False) -> None:
    """Enriquece partidas Lichess com clocks e métricas de análise (Etapa 2b)."""

    logger = configure_logging(LOG_PATH, "enriquecer_partidas_lichess")
    settings = load_settings()
    client = create_supabase_client(
        settings.supabase_url, settings.supabase_service_role_key
    )
    partidas = selecionar_partidas(client, external_id)
    total = len(partidas)
    log_and_print(logger, f"Partidas a processar: {total}")

    com_clocks = com_metricas = sem_nada = falhas = 0
    start_time = time.time()
    for index, partida in enumerate(partidas, start=1):
        ext = partida.get("external_id")
        try:
            game_export = fetch_game_export(str(ext), logger)
            gravou_clocks, gravou_metricas = enriquecer_partida(
                client, partida, game_export, settings.lichess_username, dry_run
            )
            if gravou_clocks:
                com_clocks += 1
            if gravou_metricas:
                com_metricas += 1
            if not gravou_clocks and not gravou_metricas:
                sem_nada += 1
        except Exception as error:
            falhas += 1
            logger.exception("Falha ao enriquecer a partida %s", ext)
            log_and_print(logger, f"Partida {ext} falhou: {error}")
        log_and_print(
            logger,
            format_progress(
                "Enriquecimento", "partidas", index, total, time.time() - start_time
            ),
        )

    prefixo = "[DRY-RUN] " if dry_run else ""
    log_and_print(
        logger,
        f"{prefixo}Resumo: {com_clocks} com clocks, {com_metricas} com métricas, "
        f"{sem_nada} sem nenhum dos dois, {falhas} falharam.",
    )


def main() -> None:
    """Ponto de entrada do script (Etapas 1 e 2a de descoberta/validação)."""

    parser = argparse.ArgumentParser(
        description="Enriquece partidas do Lichess com dados oficiais do próprio site."
    )
    parser.add_argument(
        "--inspecionar",
        action="store_true",
        help="Imprime o JSON bruto de exportação de uma partida Lichess já coletada.",
    )
    parser.add_argument(
        "--validar-clocks",
        action="store_true",
        help="Compara o array clocks da API com o PGN salvo para uma partida.",
    )
    parser.add_argument(
        "--external-id",
        help="external_id da partida usada por --validar-clocks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calcula e imprime o que seria gravado, sem inserir no banco.",
    )
    args = parser.parse_args()

    if args.inspecionar:
        inspecionar()
        return

    if args.validar_clocks:
        if not args.external_id:
            parser.error("--validar-clocks requer --external-id.")
        validar_clocks(args.external_id)
        return

    enriquecer(external_id=args.external_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
