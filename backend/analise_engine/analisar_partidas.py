"""Analisa partidas pendentes com Stockfish e registra lances críticos."""

from __future__ import annotations

import io
import logging
import multiprocessing
import os
import queue
import sys
import time
import traceback
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
from backend.common.chess_math import centipawns_para_win_percent  # noqa: E402
from backend.common.progress import format_progress, log_and_print  # noqa: E402
LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "analise_engine.log"
PAGE_SIZE = 1000
CRITICAL_SWING_CP = 100
MAX_MATE_SCORE_CP = 10000
# Janela deslizante (em lances do jogador) e queda líquida mínima para erosão.
WINDOW_SIZE_EROSAO = 8
EROSAO_THRESHOLD_PERCENT = 15.0
PARTIDA_TIMEOUT_SECONDS = 600
STOCKFISH_INIT_TIMEOUT_SECONDS = 15
# O timeout da partida cobre todas as avaliações; mantenha este valor baixo
# o suficiente para que dezenas de posições caibam no orçamento total.
STOCKFISH_SEARCHTIME_MS = 3_000


@dataclass(frozen=True)
class AnalysisSettings:
    """Configurações necessárias para a análise."""

    supabase_url: str
    supabase_service_role_key: str
    stockfish_path: str
    stockfish_depth: int


@dataclass(frozen=True)
class CriticalMove:
    """Dados de um evento crítico (pico isolado ou janela de erosão)."""

    move_number: int
    notation: str | None
    evaluation_before_cp: int
    evaluation_after_cp: int
    win_percent_drop: float
    tipo_evento: str = "PICO"
    move_number_fim: int | None = None


@dataclass(frozen=True)
class PlayerMoveEval:
    """Avaliação de um lance do jogador em ordem cronológica."""

    move_number: int
    notation: str
    evaluation_before_cp: int
    evaluation_after_cp: int
    win_percent_before: float
    win_percent_after: float


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


def load_timeout_setting(name: str, default: int) -> int:
    """Carrega um timeout inteiro positivo, mantendo defaults seguros."""

    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} deve ser um inteiro") from error
    if value < 1:
        raise ValueError(f"{name} deve ser maior que zero")
    return value


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
    try:
        evaluation = engine.get_evaluation(searchtime=STOCKFISH_SEARCHTIME_MS)
    except TypeError:
        # Mantém compatibilidade com engines falsos usados nos testes unitários.
        evaluation = engine.get_evaluation()
    score_cp = evaluation_to_cp(evaluation)
    return perspective_score(score_cp, color)


def validate_standard_game(game: chess.pgn.Game, partida_id: Any) -> None:
    """Rejeita variantes e PGNs que não podem ser analisados com segurança."""

    variant = (game.headers.get("Variant") or "").strip().lower()
    if variant and variant not in {"standard", ""}:
        raise ValueError(
            f"Partida {partida_id} usa variante não padrão: "
            f"{game.headers.get('Variant')}"
        )
    if game.headers.get("Chess960", "").strip().lower() in {"1", "true", "yes"}:
        raise ValueError(f"Partida {partida_id} usa Chess960/Fischer Random")
    if game.errors:
        raise ValueError(
            f"Partida {partida_id} possui PGN incompleto ou inválido: "
            f"{'; '.join(str(error) for error in game.errors)}"
        )
    if game.end() is game:
        raise ValueError(f"Partida {partida_id} não possui lances para analisar")


def load_validated_game(partida: dict[str, Any]) -> chess.pgn.Game:
    """Carrega e valida um PGN antes de qualquer chamada ao Stockfish."""

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
    validate_standard_game(game, partida_id)
    return game


def load_erosao_settings() -> tuple[int, float]:
    """Carrega o tamanho da janela e o limiar de erosão do ambiente."""

    raw_window = os.getenv("WINDOW_SIZE_EROSAO", str(WINDOW_SIZE_EROSAO))
    try:
        window_size = int(raw_window)
    except ValueError as error:
        raise ValueError("WINDOW_SIZE_EROSAO deve ser um inteiro") from error
    if window_size < 1:
        raise ValueError("WINDOW_SIZE_EROSAO deve ser maior que zero")

    raw_threshold = os.getenv(
        "EROSAO_THRESHOLD_PERCENT", str(EROSAO_THRESHOLD_PERCENT)
    )
    try:
        threshold = float(raw_threshold)
    except ValueError as error:
        raise ValueError("EROSAO_THRESHOLD_PERCENT deve ser um número") from error
    return window_size, threshold


def selecionar_picos(player_moves: list[PlayerMoveEval]) -> list[CriticalMove]:
    """Escolhe até três lances com a maior queda isolada de win_percent."""

    candidatos = [
        CriticalMove(
            move_number=move.move_number,
            notation=move.notation,
            evaluation_before_cp=move.evaluation_before_cp,
            evaluation_after_cp=move.evaluation_after_cp,
            win_percent_drop=round(
                move.win_percent_before - move.win_percent_after, 2
            ),
        )
        for move in player_moves
    ]
    candidatos.sort(key=lambda item: abs(item.win_percent_drop), reverse=True)
    return [
        move
        for move in candidatos[:3]
        if abs(move.evaluation_after_cp - move.evaluation_before_cp)
        >= CRITICAL_SWING_CP
    ]


def calcular_max_eventos_erosao(total_lances_jogador: int) -> int:
    """Escala o número de eventos de erosão permitidos com o tamanho da partida."""

    return max(1, min(3, total_lances_jogador // 20))


def detectar_erosao(
    player_moves: list[PlayerMoveEval],
    pico_move_numbers: set[int],
    window_size: int,
    threshold_percent: float,
) -> list[CriticalMove]:
    """Detecta até N janelas não sobrepostas com queda líquida acima do limiar."""

    if window_size < 1 or len(player_moves) < window_size:
        return []

    candidatos: list[tuple[float, int]] = []
    for start in range(0, len(player_moves) - window_size + 1):
        janela = player_moves[start : start + window_size]
        queda_liquida = janela[0].win_percent_before - janela[-1].win_percent_after
        if queda_liquida >= threshold_percent:
            candidatos.append((queda_liquida, start))

    if not candidatos:
        return []

    # Guloso: prioriza as maiores quedas, pulando o que sobrepõe demais o já escolhido.
    candidatos.sort(key=lambda item: item[0], reverse=True)
    max_eventos = calcular_max_eventos_erosao(len(player_moves))

    selecionados: list[CriticalMove] = []
    move_numbers_selecionados: set[int] = set()
    for queda_liquida, start in candidatos:
        if len(selecionados) >= max_eventos:
            break

        janela = player_moves[start : start + window_size]
        move_numbers_janela = {move.move_number for move in janela}

        sobreposicao_pico = len(move_numbers_janela & pico_move_numbers)
        if sobreposicao_pico / window_size > 0.5:
            continue

        sobreposicao_selecionados = len(
            move_numbers_janela & move_numbers_selecionados
        )
        if sobreposicao_selecionados / window_size > 0.5:
            continue

        inicio = janela[0]
        fim = janela[-1]
        selecionados.append(
            CriticalMove(
                move_number=inicio.move_number,
                notation=None,
                evaluation_before_cp=inicio.evaluation_before_cp,
                evaluation_after_cp=fim.evaluation_after_cp,
                win_percent_drop=round(queda_liquida, 2),
                tipo_evento="EROSAO",
                move_number_fim=fim.move_number,
            )
        )
        move_numbers_selecionados.update(move_numbers_janela)

    return selecionados


def processar_partida(partida: dict, engine: Stockfish) -> ProcessResult:
    """Analisa uma partida e retorna seus picos e um possível evento de erosão."""

    partida_id = partida["id"]
    color = partida.get("cor_jogada")
    game = load_validated_game(partida)

    board = game.board()
    player_moves: list[PlayerMoveEval] = []
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
            player_moves.append(
                PlayerMoveEval(
                    move_number=move_number,
                    notation=notation,
                    evaluation_before_cp=before_cp,
                    evaluation_after_cp=after_cp,
                    win_percent_before=centipawns_para_win_percent(before_cp),
                    win_percent_after=centipawns_para_win_percent(after_cp),
                )
            )
        else:
            board.push(move)

    critical_moves = selecionar_picos(player_moves)
    window_size, threshold = load_erosao_settings()
    critical_moves.extend(
        detectar_erosao(
            player_moves,
            {move.move_number for move in critical_moves},
            window_size,
            threshold,
        )
    )
    return ProcessResult(partida_id=partida_id, critical_moves=critical_moves)


def _processar_partida_em_processo(
    partida: dict[str, Any],
    stockfish_path: str,
    stockfish_depth: int,
    result_queue: multiprocessing.Queue,
) -> None:
    """Inicializa o engine e analisa uma partida em processo isolado."""

    engine: Stockfish | None = None
    try:
        load_validated_game(partida)
        engine = Stockfish(
            path=stockfish_path,
            depth=stockfish_depth,
            turn_perspective=False,
        )
        result_queue.put({"kind": "ready"})
        result = processar_partida(partida, engine)
        result_queue.put({"kind": "result", "value": result})
    except Exception as error:
        result_queue.put(
            {
                "kind": "error",
                "message": str(error),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        if engine is not None:
            try:
                engine.send_quit_command()
            except Exception:
                pass


def processar_partida_com_timeout(
    partida: dict[str, Any],
    settings: AnalysisSettings,
    init_timeout_seconds: int,
    partida_timeout_seconds: int,
) -> ProcessResult:
    """Analisa uma partida com limites independentes de init e execução."""

    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    process = multiprocessing.get_context("spawn").Process(
        target=_processar_partida_em_processo,
        args=(partida, settings.stockfish_path, settings.stockfish_depth, result_queue),
    )
    started_at = time.monotonic()
    process.start()
    try:
        remaining_init = max(
            0.1, init_timeout_seconds - (time.monotonic() - started_at)
        )
        try:
            message = result_queue.get(timeout=remaining_init)
        except queue.Empty as error:
            raise TimeoutError(
                f"Partida {partida.get('id', 'desconhecida')} excedeu "
                f"{init_timeout_seconds}s na inicialização do Stockfish"
            ) from error
        if message.get("kind") != "ready":
            raise RuntimeError(
                f"Falha ao inicializar Stockfish para a partida "
                f"{partida.get('id', 'desconhecida')}: "
                f"{message.get('message', 'erro desconhecido')}\n"
                f"{message.get('traceback', '')}"
            )

        remaining_game = max(
            0.1, partida_timeout_seconds - (time.monotonic() - started_at)
        )
        try:
            message = result_queue.get(timeout=remaining_game)
        except queue.Empty as error:
            raise TimeoutError(
                f"Partida {partida.get('id', 'desconhecida')} excedeu "
                f"{partida_timeout_seconds}s de análise"
            ) from error
        if message.get("kind") == "error":
            raise RuntimeError(
                f"Falha na partida {partida.get('id', 'desconhecida')}: "
                f"{message.get('message', 'erro desconhecido')}\n"
                f"{message.get('traceback', '')}"
            )
        return message["value"]
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=5)
        result_queue.close()


def insert_critical_moves(
    client: Client, result: ProcessResult
) -> int:
    """Substitui os lances críticos de uma partida e retorna a quantidade inserida."""

    # Remove lances de execuções anteriores para que um reprocessamento nunca duplique.
    client.table("lances_criticos").delete().eq(
        "partida_id", result.partida_id
    ).execute()

    inserted = 0
    for move in result.critical_moves:
        client.table("lances_criticos").insert(
            {
                "partida_id": result.partida_id,
                "numero_lance": move.move_number,
                "numero_lance_fim": move.move_number_fim,
                "lance_notacao": move.notation,
                "avaliacao_antes_cp": move.evaluation_before_cp,
                "avaliacao_depois_cp": move.evaluation_after_cp,
                "queda_win_percent": move.win_percent_drop,
                "tipo_evento": move.tipo_evento,
            }
        ).execute()
        inserted += 1
    return inserted


def main() -> None:
    """Processa todas as partidas pendentes e imprime o resumo final."""

    logger = configure_logging()
    processed = failed = critical_moves_inserted = 0
    try:
        settings = load_settings()
        init_timeout_seconds = load_timeout_setting(
            "STOCKFISH_INIT_TIMEOUT_SECONDS", STOCKFISH_INIT_TIMEOUT_SECONDS
        )
        partida_timeout_seconds = load_timeout_setting(
            "PARTIDA_TIMEOUT_SECONDS", PARTIDA_TIMEOUT_SECONDS
        )
        client = create_client(
            settings.supabase_url, settings.supabase_service_role_key
        )
        pending_games = fetch_pending_games(client, logger)
        total = len(pending_games)
        start_time = time.time()
        for index, partida in enumerate(pending_games, start=1):
            partida_id = partida.get("id", "desconhecida")
            external_id = partida.get("external_id", partida_id)
            log_and_print(
                logger,
                f"Iniciando análise da partida {index}/{total} "
                f"(external_id={external_id})...",
            )
            try:
                update_status(client, partida_id, "processando")
                result = processar_partida_com_timeout(
                    partida,
                    settings,
                    init_timeout_seconds,
                    partida_timeout_seconds,
                )
                critical_moves_inserted += insert_critical_moves(client, result)
                update_status(client, partida_id, "concluido")
                processed += 1
            except Exception:
                failed += 1
                log_and_print(
                    logger,
                    f"Falha ao processar a partida {partida_id} "
                    f"(external_id={external_id}); status será marcado como falhou.\n"
                    f"{traceback.format_exc()}",
                )
                try:
                    update_status(client, partida_id, "falhou")
                except Exception:
                    log_and_print(
                        logger,
                        f"Falha ao marcar a partida {partida_id} como falhou.\n"
                        f"{traceback.format_exc()}",
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
    print(f"Partidas processadas com sucesso: {processed}")
    print(f"Partidas com falha: {failed}")
    print(f"Lances críticos inseridos: {critical_moves_inserted}")


if __name__ == "__main__":
    main()
