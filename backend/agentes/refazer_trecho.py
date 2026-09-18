"""Um lance do treino de trecho, jogado contra o motor (D-66).

Separado de `backend/common/treino_trecho.py` de propósito: lá mora a aritmética
do trecho (que é testável sem nada), aqui mora tudo o que fala com o Stockfish.
O servidor (`POST /treino/{id}/trecho`) só orquestra os dois e persiste o
resultado.

Cada requisição avança o trecho em um lance do jogador mais a resposta do motor,
sob uma única tomada do `engine_lock` (R3). São três interações com o motor por
passo: a avaliação antes do lance, a avaliação depois dele e a escolha da
resposta do adversário — e duas no último lance da janela, que não tem resposta.
"""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chess
from stockfish import Stockfish

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.revisar_exercicio_avulso import (  # noqa: E402
    _acquire_engine_lock,
    resolver_lance_uci,
    resolver_lance_usuario,
)
from backend.analise_engine.analisar_partidas import evaluate_position  # noqa: E402
from backend.common.chess_math import centipawns_para_win_percent  # noqa: E402
from backend.common.treino_trecho import reconstruir_tabuleiro  # noqa: E402


@dataclass(frozen=True)
class PassoDoTrecho:
    """O que um lance do jogador produziu dentro do trecho."""

    progresso: dict[str, Any]
    lance_interpretado: str
    lance_oponente: str | None
    fen: str
    concluido: bool
    # O trecho acabou antes de completar a janela porque a partida acabou
    # (mate ou afogamento). Não é erro: é o desfecho mais informativo que o
    # drill pode ter, e o veredito sai da posição real onde parou.
    fim_por_fim_de_jogo: bool


def win_percent_na_posicao(engine: Stockfish, board: chess.Board, cor: str) -> float:
    """win% da posição SEMPRE pela perspectiva do jogador do card.

    É a mesma leitura que `processar_partida` usa para detectar a erosão, com a
    mesma função de conversão — sem isso o número do drill não seria comparável
    com o número que criou o evento.

    Posição terminal não vai ao motor. Num mate o Stockfish devolve
    `{'type': 'mate', 'value': 0}`, e zero não tem sinal: `evaluation_to_cp`
    lê isso como +10000 (vantagem das BRANCAS) seja quem for o matado. Quem dá
    mate de pretas no meio do trecho receberia, por causa disso, o pior
    veredito possível. O tabuleiro já sabe a resposta certa sem perguntar a
    ninguém — e `processar_partida` nunca cruzou com o caso porque para no
    lance anterior ao mate (`if board.is_checkmate(): break`).
    """

    if board.is_checkmate():
        jogador_esta_em_xeque_mate = (
            "BRANCAS" if board.turn == chess.WHITE else "PRETAS"
        ) == cor
        return 0.0 if jogador_esta_em_xeque_mate else 100.0
    if board.is_game_over():
        # Afogamento, material insuficiente, repetição, regra dos 50 lances:
        # empate é meio a meio, não uma avaliação de motor.
        return 50.0
    return round(centipawns_para_win_percent(evaluate_position(engine, board, cor)), 2)


def lance_do_motor(engine: Stockfish, board: chess.Board, elo: int) -> str | None:
    """Escolhe a resposta do adversário com a força limitada ao rating dado.

    A força volta ao máximo no `finally` porque o motor é uma instância só,
    compartilhada por todas as requisições (R3): sair daqui com UCI_LimitStrength
    ligado envenenaria a próxima análise de partida com uma avaliação fraca, e
    isso não apareceria como erro em lugar nenhum — só como número errado.

    Devolve None quando o motor não tem lance a dar (posição terminal) ou
    responde algo ilegal, e quem chama trata isso como fim do trecho.
    """

    engine.set_elo_rating(elo)
    try:
        engine.set_fen_position(board.fen())
        uci = engine.get_best_move()
    finally:
        engine.resume_full_strength()

    if not uci:
        return None
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return None
    if move not in board.legal_moves:
        return None
    return board.san(move)


def jogar_passo_do_trecho(
    engine: Stockfish,
    engine_lock: threading.Lock | None,
    progresso: dict[str, Any],
    lance_texto: str,
    elo_oponente: int,
    lance_uci: str | None = None,
) -> PassoDoTrecho:
    """Avança o trecho em um lance do jogador e a resposta do motor.

    `progresso` entra normalizado (ver `normalizar_progresso`) e sai com o
    lance, a resposta e as duas leituras de win% acrescentadas. A posição vem
    do replay do histórico, nunca do cliente — quem chama manda só o texto do
    lance.

    `lance_uci`, quando vem, tem precedência sobre `lance_texto`: é o lance
    clicado no tabuleiro, exato por construção, e escapa da ambiguidade PT/EN
    da notação (ver `resolver_lance_uci`, D-82).

    ValueError com "corrompido" vem do replay (estado inconsistente); qualquer
    outro ValueError é lance inválido do usuário.
    """

    fen_inicial = progresso["fen_inicial"]
    total_lances = int(progresso["total_lances"])
    lances: list[str] = list(progresso["lances"])
    win_antes: list[float] = list(progresso["win_antes"])
    win_depois: list[float] = list(progresso["win_depois"])

    board = reconstruir_tabuleiro(fen_inicial, lances)
    cor = "BRANCAS" if chess.Board(fen_inicial).turn == chess.WHITE else "PRETAS"
    resolvido = (
        resolver_lance_uci(board, lance_uci)
        if lance_uci
        else resolver_lance_usuario(board, lance_texto)
    )
    san_do_jogador = board.san(resolvido.move)

    lance_oponente: str | None = None
    with _acquire_engine_lock(engine_lock):
        antes = win_percent_na_posicao(engine, board, cor)
        board.push(resolvido.move)
        depois = win_percent_na_posicao(engine, board, cor)

        lances.append(san_do_jogador)
        win_antes.append(antes)
        win_depois.append(depois)

        faltam_lances = len(win_depois) < total_lances
        if faltam_lances and not board.is_game_over():
            lance_oponente = lance_do_motor(engine, board, elo_oponente)
            if lance_oponente is not None:
                lances.append(lance_oponente)
                board.push_san(lance_oponente)

    fim_de_jogo = board.is_game_over()
    # Motor sem lance a dar numa posição que não acabou é anomalia do
    # subprocesso, não desfecho da partida: encerra o trecho do mesmo jeito
    # (com o que já foi medido), mas não mente dizendo que a partida terminou.
    motor_sem_resposta = faltam_lances and lance_oponente is None and not fim_de_jogo
    concluido = not faltam_lances or fim_de_jogo or motor_sem_resposta

    return PassoDoTrecho(
        progresso={
            "fen_inicial": fen_inicial,
            "total_lances": total_lances,
            "lances": lances,
            "win_antes": win_antes,
            "win_depois": win_depois,
        },
        lance_interpretado=resolvido.lance_interpretado,
        lance_oponente=lance_oponente,
        fen=board.fen(),
        concluido=concluido,
        fim_por_fim_de_jogo=fim_de_jogo,
    )
