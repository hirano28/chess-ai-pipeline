"""Analisa partidas pendentes com Stockfish e registra lances críticos."""

from __future__ import annotations

import io
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chess
import chess.pgn
from dotenv import load_dotenv
from stockfish import Stockfish
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import format_progress, log_and_print  # noqa: E402
LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "analise_engine.log"
PAGE_SIZE = 1000
CRITICAL_SWING_CP = 100
MAX_MATE_SCORE_CP = 10000


@dataclass(frozen=True)
class AnalysisSettings:
    """Configurações necessárias para a análise."""

    supabase_url: str
    supabase_service_role_key: str
    stockfish_path: str
    stockfish_depth: int


@dataclass(frozen=True)
class CriticalMove:
    """Dados de um lance cuja avaliação mudou significativamente."""

    move_number: int
    notation: str
    evaluation_before_cp: int
    evaluation_after_cp: int


@dataclass(frozen=True)
class ProcessResult:
    """Resultado do processamento de uma partida."""

    partida_id: Any
    critical_moves: list[CriticalMove]


def configure_logging() -> logging.Logger:
    """Configura o logger exclusivo da análise e cria o diretório de logs."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("analise_engine")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


def load_settings() -> AnalysisSettings:
    """Carrega e valida as variáveis de ambiente da análise."""

    load_dotenv(PROJECT_ROOT / ".env")
    required = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        "STOCKFISH_PATH": os.getenv("STOCKFISH_PATH"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )

    raw_depth = os.getenv("STOCKFISH_DEPTH", "16")
    try:
        depth = int(raw_depth)
    except ValueError as error:
        raise ValueError("STOCKFISH_DEPTH deve ser um inteiro") from error
    if depth < 1:
        raise ValueError("STOCKFISH_DEPTH deve ser maior que zero")

    return AnalysisSettings(
        supabase_url=required["SUPABASE_URL"],
        supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],
        stockfish_path=required["STOCKFISH_PATH"],
        stockfish_depth=depth,
    )


def fetch_pending_games(client: Client, logger: logging.Logger) -> list[dict[str, Any]]:
    """Busca todas as partidas pendentes em páginas."""

    games: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            client.table("partidas")
            .select("*")
            .eq("status_processamento", "pendente")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        games.extend(page)
        logger.info(
            "Página de partidas pendentes carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            return games
        offset += PAGE_SIZE


def update_status(client: Client, partida_id: Any, status: str) -> None:
    """Atualiza somente o status de processamento da partida."""

    client.table("partidas").update({"status_processamento": status}).eq(
        "id", partida_id
    ).execute()


def evaluation_to_cp(evaluation: dict[str, str | int]) -> int:
    """Converte avaliação de centipawns ou mate para uma escala numérica."""

    value = int(evaluation["value"])
    if evaluation["type"] == "cp":
        return value
    if evaluation["type"] == "mate":
        mate_score = max(0, MAX_MATE_SCORE_CP - (abs(value) * 10))
        return mate_score * (1 if value >= 0 else -1)
    raise ValueError(f"Tipo de avaliação desconhecido: {evaluation['type']}")


def perspective_score(score_cp: int, color: str) -> int:
    """Converte uma avaliação da perspectiva das brancas para a do jogador."""

    normalized_color = color.strip().upper()
    if normalized_color == "BRANCAS":
        return score_cp
    if normalized_color == "PRETAS":
        return -score_cp
    raise ValueError(f"Cor de jogada inválida: {color}")


def evaluate_position(engine: Stockfish, board: chess.Board, color: str) -> int:
    """Avalia uma posição da perspectiva do jogador da pipeline."""

    engine.set_fen_position(board.fen())
    score_cp = evaluation_to_cp(engine.get_evaluation())
    return perspective_score(score_cp, color)


def processar_partida(partida: dict, engine: Stockfish) -> ProcessResult:
    """Analisa uma partida e retorna seus três maiores swings relevantes."""

    partida_id = partida["id"]
    pgn = partida.get("pgn")
    color = partida.get("cor_jogada")
    if not isinstance(pgn, str) or not pgn.strip():
        raise ValueError(f"Partida {partida_id} não possui PGN válido")
    if color not in {"BRANCAS", "PRETAS"}:
        raise ValueError(f"Partida {partida_id} possui cor_jogada inválida: {color}")

    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise ValueError(f"Não foi possível fazer parse do PGN da partida {partida_id}")

    board = game.board()
    evaluated_moves: list[CriticalMove] = []
    for move in game.mainline_moves():
        playing_color = "BRANCAS" if board.turn == chess.WHITE else "PRETAS"
        if playing_color == color:
            notation = board.san(move)
            move_number = board.fullmove_number
            before_cp = evaluate_position(engine, board, color)
            board.push(move)
            if board.is_checkmate():
                break
            after_cp = evaluate_position(engine, board, color)
            evaluated_moves.append(
                CriticalMove(
                    move_number=move_number,
                    notation=notation,
                    evaluation_before_cp=before_cp,
                    evaluation_after_cp=after_cp,
                )
            )
        else:
            board.push(move)

    evaluated_moves.sort(
        key=lambda item: abs(item.evaluation_after_cp - item.evaluation_before_cp),
        reverse=True,
    )
    critical_moves = [
        move
        for move in evaluated_moves[:3]
        if abs(move.evaluation_after_cp - move.evaluation_before_cp)
        >= CRITICAL_SWING_CP
    ]
    return ProcessResult(partida_id=partida_id, critical_moves=critical_moves)


def insert_critical_moves(
    client: Client, result: ProcessResult
) -> int:
    """Insere os lances críticos de uma partida e retorna a quantidade."""

    inserted = 0
    for move in result.critical_moves:
        client.table("lances_criticos").insert(
            {
                "partida_id": result.partida_id,
                "numero_lance": move.move_number,
                "lance_notacao": move.notation,
                "avaliacao_antes_cp": move.evaluation_before_cp,
                "avaliacao_depois_cp": move.evaluation_after_cp,
            }
        ).execute()
        inserted += 1
    return inserted


def main() -> None:
    """Processa todas as partidas pendentes e imprime o resumo final."""

    logger = configure_logging()
    processed = failed = critical_moves_inserted = 0
    engine: Stockfish | None = None
    try:
        settings = load_settings()
        client = create_client(
            settings.supabase_url, settings.supabase_service_role_key
        )
        pending_games = fetch_pending_games(client, logger)
        engine = Stockfish(
            path=settings.stockfish_path,
            depth=settings.stockfish_depth,
            turn_perspective=False,
        )
        total = len(pending_games)
        start_time = time.time()
        for index, partida in enumerate(pending_games, start=1):
            partida_id = partida.get("id", "desconhecida")
            try:
                update_status(client, partida_id, "processando")
                result = processar_partida(partida, engine)
                critical_moves_inserted += insert_critical_moves(client, result)
                update_status(client, partida_id, "concluido")
                processed += 1
            except Exception:
                failed += 1
                logger.exception("Falha ao processar a partida %s", partida_id)
                try:
                    update_status(client, partida_id, "falhou")
                except Exception:
                    logger.exception(
                        "Falha ao marcar a partida %s como falhou", partida_id
                    )
            log_and_print(
                logger,
                format_progress(
                    "Análise", "partidas", index, total, time.time() - start_time
                ),
            )
    except Exception:
        failed += 1
        logger.exception("Falha geral na análise das partidas")
    finally:
        if engine is not None:
            try:
                engine.send_quit_command()
            except Exception:
                logger.exception("Falha ao fechar a instância do Stockfish")

    print(f"Partidas processadas com sucesso: {processed}")
    print(f"Partidas com falha: {failed}")
    print(f"Lances críticos inseridos: {critical_moves_inserted}")


if __name__ == "__main__":
    main()
