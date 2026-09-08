"""Ferramenta interativa de feedback imediato para exercícios avulsos de xadrez.

Reaproveita a lógica de backend/agentes/revisar_pensamento.py (Stockfish,
chess_math, classificação de qualidade, prompt/schema do Gemini) para dar
feedback na hora sobre posições avulsas de "Guess the Move" (ex.: ChessTempo).

Ferramenta de uso pontual: sem barra de progresso e sem log em arquivo,
apenas prints diretos na tela.
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Iterator

import chess
import chess.pgn
import google.genai as genai
from stockfish import Stockfish


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.revisar_pensamento import (  # noqa: E402
    AvaliacaoLance,
    RevisaoRaciocinio,
    Settings,
    build_prompt,
    classificar_qualidade_lance,
    gerar_revisao,
    load_settings,
    obter_linha_principal,
    obter_melhor_lance,
)
from backend.analise_engine.analisar_partidas import evaluate_position  # noqa: E402
from backend.common.chess_math import centipawns_para_win_percent  # noqa: E402
from backend.ingestao.common_ingestao import create_supabase_client  # noqa: E402

# Ferramenta de uso pontual (1 posição por vez): pode pagar uma busca bem mais
# profunda que o STOCKFISH_SEARCHTIME_MS usado no processamento em lote.
EXERCICIO_AVULSO_SEARCHTIME_MS = int(
    os.getenv("EXERCICIO_AVULSO_SEARCHTIME_MS", "10000")
)

# Uma única instância do Stockfish é compartilhada entre requisições web
# concorrentes; sem lock, duas requisições simultâneas corrompem o diálogo
# com o subprocesso do motor e travam indefinidamente (sem erro, sem timeout).
ENGINE_LOCK_TIMEOUT_SECONDS = 60


class EngineIndisponivelError(RuntimeError):
    """Erro sinalizando que o lock do engine não foi obtido dentro do timeout."""


@contextlib.contextmanager
def _acquire_engine_lock(
    engine_lock: threading.Lock | None,
    timeout_seconds: float = ENGINE_LOCK_TIMEOUT_SECONDS,
) -> Iterator[None]:
    """Serializa o acesso ao engine; sem lock (uso via CLI), é um no-op."""

    if engine_lock is None:
        yield
        return
    if not engine_lock.acquire(timeout=timeout_seconds):
        raise EngineIndisponivelError(
            "Servidor ocupado, tente novamente em instantes."
        )
    try:
        yield
    finally:
        engine_lock.release()


def configure_console_logger() -> logging.Logger:
    """Logger só em console (sem arquivo), para os avisos de retry do Gemini."""

    logger = logging.getLogger("revisar_exercicio_avulso")
    logger.setLevel(logging.WARNING)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)
    return logger


def ler_fen() -> chess.Board:
    """Pede a FEN da posição até que seja válida."""

    while True:
        fen = input("Cole a FEN da posição: ").strip()
        try:
            return chess.Board(fen)
        except ValueError as error:
            print(f"FEN inválida: {error}. Tente novamente.\n")


def ler_lance(board: chess.Board) -> chess.Move:
    """Pede o lance em SAN até que seja legal na posição."""

    while True:
        lance_texto = input("Lance jogado (SAN, ex: Nxe5 ou Rxc3+): ").strip()
        try:
            return board.parse_san(lance_texto)
        except ValueError as error:
            print(f"Lance inválido: {error}. Tente novamente.\n")


def ler_texto_pensamento() -> str:
    """Lê múltiplas linhas de raciocínio até uma linha só com 'FIM'."""

    print("Descreva seu raciocínio (finalize com uma linha contendo apenas FIM):")
    linhas: list[str] = []
    while True:
        linha = input()
        if linha.strip().upper() == "FIM":
            break
        linhas.append(linha)
    return "\n".join(linhas).strip()


def perguntar_sim_nao(pergunta: str, default_sim: bool = True) -> bool:
    """Pergunta Y/n ao usuário, com valor padrão configurável."""

    sufixo = "[Y/n]" if default_sim else "[y/N]"
    resposta = input(f"{pergunta} {sufixo} ").strip().lower()
    if not resposta:
        return default_sim
    return resposta in {"y", "s", "sim", "yes"}


def avaliar_lance_avulso(
    engine: Stockfish,
    board: chess.Board,
    move: chess.Move,
    engine_lock: threading.Lock | None = None,
) -> AvaliacaoLance:
    """Avalia o lance jogado numa posição avulsa, reaproveitando o mesmo motor.

    Todo o uso do engine (avaliação antes, melhor lance, linha principal e
    avaliação depois) fica dentro de engine_lock, para não corromper o
    subprocesso do Stockfish quando requisições concorrentes o compartilham.
    """

    with _acquire_engine_lock(engine_lock):
        cor_jogada = "BRANCAS" if board.turn == chess.WHITE else "PRETAS"
        before_cp = evaluate_position(
            engine, board, cor_jogada, searchtime_ms=EXERCICIO_AVULSO_SEARCHTIME_MS
        )
        melhor_lance = obter_melhor_lance(
            engine, board, searchtime_ms=EXERCICIO_AVULSO_SEARCHTIME_MS
        )
        linha_principal = obter_linha_principal(engine, board)
        lance_jogado = board.san(move)
        board.push(move)
        after_cp = evaluate_position(
            engine, board, cor_jogada, searchtime_ms=EXERCICIO_AVULSO_SEARCHTIME_MS
        )
    queda_win_percent = round(
        centipawns_para_win_percent(before_cp) - centipawns_para_win_percent(after_cp),
        2,
    )
    return AvaliacaoLance(lance_jogado, melhor_lance, queda_win_percent, linha_principal)


def resolver_posicao(posicao: str) -> chess.Board:
    """Resolve uma FEN direta ou um PGN completo para o tabuleiro de avaliação.

    Tenta primeiro como FEN; se falhar, tenta como PGN (com ou sem cabeçalhos)
    e aplica todos os lances, retornando a posição final resultante.
    """

    posicao = posicao.strip()
    try:
        return chess.Board(posicao)
    except ValueError:
        pass

    game = chess.pgn.read_game(io.StringIO(posicao))
    # chess.pgn.read_game nunca retorna None para texto não vazio: para lixo
    # sem estrutura de PGN, ele devolve um jogo com headers padrão e 0 lances.
    if game is None:
        raise ValueError("A posição informada não é uma FEN nem um PGN válido.")

    moves = list(game.mainline_moves())
    if not moves:
        raise ValueError(
            "A posição informada não é uma FEN nem um PGN válido "
            "(nenhum lance foi reconhecido)."
        )

    board = game.board()
    for move in moves:
        board.push(move)
    return board


def processar_revisao_avulsa(
    engine: Stockfish,
    gemini_client: Any,
    settings: Settings,
    logger: logging.Logger,
    fen: str,
    lance_san: str,
    texto_pensamento: str,
    engine_lock: threading.Lock | None = None,
) -> dict[str, Any]:
    """Núcleo reutilizável: avalia o lance, classifica a qualidade e chama o Gemini.

    Usado tanto pelo script interativo quanto pelo servidor web (backend/api).
    engine_lock, quando fornecido, serializa o acesso ao Stockfish compartilhado
    entre requisições concorrentes (ver _acquire_engine_lock).
    """

    board = chess.Board(fen)
    move = board.parse_san(lance_san)

    avaliacao = avaliar_lance_avulso(engine, board, move, engine_lock)
    qualidade_lance = classificar_qualidade_lance(
        avaliacao.queda_win_percent, settings.limiar_lance_bom, settings.limiar_lance_ruim
    )
    prompt = build_prompt(texto_pensamento, avaliacao, qualidade_lance)
    revisao = gerar_revisao(gemini_client, prompt, logger, avaliacao.linha_principal)

    return {
        "lance_jogado": avaliacao.lance_jogado,
        "melhor_lance": avaliacao.melhor_lance,
        "queda_win_percent": avaliacao.queda_win_percent,
        "qualidade_lance": qualidade_lance,
        "qualidade_raciocinio": revisao.qualidade_raciocinio,
        "feedback_texto": revisao.feedback_texto,
        "analise_mestre": revisao.analise_mestre,
    }


def imprimir_resultado(resultado: dict[str, Any]) -> None:
    """Imprime o feedback formatado na tela."""

    print("\n" + "=" * 60)
    print(f"Lance jogado:            {resultado['lance_jogado']}")
    print(f"Melhor lance (motor):    {resultado['melhor_lance']}")
    print(f"Queda de win%:           {resultado['queda_win_percent']}")
    print(f"Qualidade do lance:      {resultado['qualidade_lance']}")
    print(f"Qualidade do raciocínio: {resultado['qualidade_raciocinio']}")
    print(f"Feedback: {resultado['feedback_texto']}")
    print(f"Análise do mestre: {resultado['analise_mestre']}")
    print("=" * 60 + "\n")


def salvar_exercicio(
    client: Any,
    fen: str,
    texto_pensamento: str,
    resultado: dict[str, Any],
) -> None:
    """Insere o exercício avulso revisado em revisao_exercicio_avulso."""

    client.table("revisao_exercicio_avulso").insert(
        {
            "fen": fen,
            "lance_jogado": resultado["lance_jogado"],
            "melhor_lance": resultado["melhor_lance"],
            "queda_win_percent": resultado["queda_win_percent"],
            "texto_pensamento": texto_pensamento,
            "qualidade_lance": resultado["qualidade_lance"],
            "qualidade_raciocinio": resultado["qualidade_raciocinio"],
            "feedback_texto": resultado["feedback_texto"],
            "origem": "GUESS_THE_MOVE",
        }
    ).execute()


def executar_um_exercicio(
    engine: Stockfish,
    gemini_client: Any,
    supabase_client: Any,
    settings: Settings,
    logger: logging.Logger,
) -> None:
    """Executa o ciclo completo de um único exercício avulso."""

    board = ler_fen()
    fen = board.fen()
    move = ler_lance(board)
    lance_san = board.san(move)
    texto_pensamento = ler_texto_pensamento()

    print("\nAvaliando com o Stockfish e consultando o Gemini...")
    resultado = processar_revisao_avulsa(
        engine, gemini_client, settings, logger, fen, lance_san, texto_pensamento
    )

    imprimir_resultado(resultado)

    if perguntar_sim_nao("Salvar este exercício?"):
        salvar_exercicio(supabase_client, fen, texto_pensamento, resultado)
        print("Exercício salvo.\n")
    else:
        print("Exercício não salvo.\n")


def run() -> None:
    """Loop interativo principal: pede exercícios até o usuário encerrar."""

    logger = configure_console_logger()
    settings = load_settings()
    supabase_client = create_supabase_client(
        settings.supabase_url, settings.supabase_service_role_key
    )
    gemini_client = genai.Client(api_key=settings.gemini_api_key)

    print("Inicializando o Stockfish...")
    engine = Stockfish(
        path=settings.stockfish_path,
        depth=settings.stockfish_depth,
        turn_perspective=False,
    )
    print("Pronto. Vamos revisar seus exercícios avulsos.\n")

    try:
        while True:
            try:
                executar_um_exercicio(
                    engine, gemini_client, supabase_client, settings, logger
                )
            except Exception as error:
                print(f"\nOcorreu um erro neste exercício: {error}\nVamos tentar de novo.\n")

            if not perguntar_sim_nao("Fazer outro exercício?"):
                break
    finally:
        try:
            engine.send_quit_command()
        except Exception:
            pass
        print("Encerrado.")


if __name__ == "__main__":
    run()
