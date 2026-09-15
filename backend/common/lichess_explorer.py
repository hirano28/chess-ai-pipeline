"""Integração com Lichess Opening Explorer (explorer.lichess.org).

Permite consultar a base de partidas de mestres e identificar o lance exato
onde uma partida saiu da teoria ("fora do livro"), quem jogou o lance de saída
(jogador vs oponente) e a avaliação/estatísticas do último momento teórico.

Atenção: explorer.lichess.org/masters exige cabeçalho de autorização Bearer.
Utiliza LICHESS_STUDY_TOKEN do ambiente ou token OAuth do usuário.
"""

from __future__ import annotations

import io
import os
from typing import Any

import chess
import chess.pgn
import requests

EXPLORER_MASTERS_URL = "https://explorer.lichess.org/masters"
MAX_PLY_TEORIA = 40  # Verifica até o lance 20 (40 meio-lances)
REQUEST_TIMEOUT_S = 6


def consultar_opening_explorer(
    moves_uci: list[str] | str,
    token: str | None = None,
) -> dict[str, Any]:
    """Consulta o Lichess Opening Explorer (base de Mestres) para uma sequência UCI.

    Args:
        moves_uci: Lista de lances em UCI (ex: ["e2e4", "e7e6"]) ou string separada por vírgula.
        token: Token de autenticação Lichess (Bearer). Se None, busca em LICHESS_STUDY_TOKEN.
    """
    if isinstance(moves_uci, list):
        play_param = ",".join(moves_uci)
    else:
        play_param = moves_uci.strip()

    auth_token = token or os.environ.get("LICHESS_STUDY_TOKEN")
    headers = {"User-Agent": "ChessAIPipeline/1.0"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    url = f"{EXPLORER_MASTERS_URL}?play={play_param}" if play_param else EXPLORER_MASTERS_URL
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_S)
        if resp.status_code == 401:
            return {
                "sucesso": False,
                "erro": "autenticacao_necessaria",
                "detalhes": "Lichess Opening Explorer exige token de autenticação válido.",
            }
        if resp.status_code != 200:
            return {
                "sucesso": False,
                "erro": f"http_{resp.status_code}",
                "detalhes": resp.text[:200],
            }
        data = resp.json()
        total = data.get("white", 0) + data.get("draws", 0) + data.get("black", 0)
        return {
            "sucesso": True,
            "white": data.get("white", 0),
            "draws": data.get("draws", 0),
            "black": data.get("black", 0),
            "total": total,
            "opening": data.get("opening"),
            "moves": data.get("moves", []),
            "top_games": data.get("topGames", []),
        }
    except Exception as exc:
        return {"sucesso": False, "erro": "falha_rede", "detalhes": str(exc)}


def _extrair_lances_pgn(pgn_ou_moves: str | list[str]) -> tuple[list[str], list[str]]:
    """Extrai listas paralelas de lances UCI e SAN a partir de PGN ou lista UCI."""
    if isinstance(pgn_ou_moves, list):
        # Se for lista, assume que são strings UCI e reconstrói SAN se possível
        board = chess.Board()
        san_list: list[str] = []
        uci_list: list[str] = []
        for uci_str in pgn_ou_moves:
            try:
                move = chess.Move.from_uci(uci_str)
                if move in board.legal_moves:
                    san_list.append(board.san(move))
                    board.push(move)
                    uci_list.append(uci_str)
                else:
                    uci_list.append(uci_str)
                    san_list.append(uci_str)
            except Exception:
                uci_list.append(uci_str)
                san_list.append(uci_str)
        return uci_list, san_list

    # Se for string PGN
    try:
        game = chess.pgn.read_game(io.StringIO(pgn_ou_moves))
        if not game:
            return [], []
        board = game.board()
        uci_list = []
        san_list = []
        for move in game.mainline_moves():
            san_list.append(board.san(move))
            uci_list.append(move.uci())
            board.push(move)
        return uci_list, san_list
    except Exception:
        return [], []


def detectar_saida_teoria(
    pgn_ou_moves: str | list[str],
    token: str | None = None,
    cor_jogada: str | None = None,
) -> dict[str, Any]:
    """Identifica o momento exato em que a partida saiu do livro de teoria de mestres.

    Utiliza busca binária para encontrar a transição de posição com partidas
    para posição sem partidas na base de Mestres do Lichess.

    Args:
        pgn_ou_moves: PGN textual ou lista de strings de lances UCI.
        token: Token Lichess para autenticação.
        cor_jogada: 'BRANCAS' ou 'PRETAS' para definir 'JOGADOR' vs 'OPONENTE'.

    Returns:
        Dicionário detalhado com ply_saida, numero_lance, cor, quem_saiu,
        nome da abertura e lances candidatos recomendados pelos mestres.
    """
    uci_moves, san_moves = _extrair_lances_pgn(pgn_ou_moves)
    if not uci_moves:
        return {
            "sucesso": False,
            "disponivel": False,
            "motivo": "sem_lances",
        }

    # Limita a checagem aos primeiros MAX_PLY_TEORIA lances
    limite_plies = min(len(uci_moves), MAX_PLY_TEORIA)

    # 1. Primeiro testa se o primeiro lance é válido no livro
    consulta_inicial = consultar_opening_explorer(uci_moves[:1], token=token)
    if not consulta_inicial.get("sucesso"):
        return {
            "sucesso": False,
            "disponivel": False,
            "motivo": consulta_inicial.get("erro", "erro_consulta"),
            "detalhes": consulta_inicial.get("detalhes"),
        }

    # Se mesmo o lance 1 não tem partidas (ex: 1. h4 ou variante ultrarrara)
    if consulta_inicial.get("total", 0) == 0:
        return _montar_resultado_saida(
            ply_saida=1,
            uci_moves=uci_moves,
            san_moves=san_moves,
            ultimo_livro={},
            cor_jogada=cor_jogada,
        )

    # 2. Testa o último ply do limite: se ainda estiver no livro, a partida seguiu teoria longa
    consulta_fim = consultar_opening_explorer(uci_moves[:limite_plies], token=token)
    if consulta_fim.get("sucesso") and consulta_fim.get("total", 0) > 0:
        return {
            "sucesso": True,
            "disponivel": True,
            "ficou_no_livro": True,
            "plies_teoricos_jogados": limite_plies,
            "lances_completos_teoricos": (limite_plies + 1) // 2,
            "nome_abertura": (consulta_fim.get("opening") or {}).get("name"),
            "eco": (consulta_fim.get("opening") or {}).get("eco"),
            "stats_fim": {
                "white": consulta_fim.get("white", 0),
                "draws": consulta_fim.get("draws", 0),
                "black": consulta_fim.get("black", 0),
                "total": consulta_fim.get("total", 0),
            },
        }

    # 3. Busca binária para achar o menor ply k com total == 0
    # Invariante: low tem partidas > 0; high tem total == 0
    low = 1
    high = limite_plies
    ultimo_livro_data: dict[str, Any] = consulta_inicial

    while low + 1 < high:
        mid = (low + high) // 2
        res = consultar_opening_explorer(uci_moves[:mid], token=token)
        if not res.get("sucesso"):
            # Em caso de falha de rede em uma iteração intermediária, encerra graciosamente
            break
        if res.get("total", 0) > 0 and len(res.get("moves", [])) > 0:
            low = mid
            ultimo_livro_data = res
        else:
            high = mid

    # high é o primeiro ply onde a partida saiu do livro
    ply_saida = high
    # Se ainda não temos os dados do ply 'low', garante busca
    if low > 1 and (not ultimo_livro_data or ultimo_livro_data.get("total", 0) == 0):
        ultimo_livro_data = consultar_opening_explorer(uci_moves[:low], token=token)

    return _montar_resultado_saida(
        ply_saida=ply_saida,
        uci_moves=uci_moves,
        san_moves=san_moves,
        ultimo_livro=ultimo_livro_data,
        cor_jogada=cor_jogada,
    )


def _montar_resultado_saida(
    ply_saida: int,
    uci_moves: list[str],
    san_moves: list[str],
    ultimo_livro: dict[str, Any],
    cor_jogada: str | None,
) -> dict[str, Any]:
    """Formata a resposta estruturada do ponto de saída da teoria."""
    numero_lance = (ply_saida + 1) // 2
    cor_saida = "BRANCAS" if ply_saida % 2 == 1 else "PRETAS"

    quem_saiu: str | None = None
    if cor_jogada:
        quem_saiu = "JOGADOR" if cor_saida == cor_jogada.upper() else "OPONENTE"

    idx = ply_saida - 1
    lance_uci = uci_moves[idx] if idx < len(uci_moves) else None
    lance_san = san_moves[idx] if idx < len(san_moves) else None

    opening_info = ultimo_livro.get("opening") or {}
    total_games = ultimo_livro.get("total", 0)

    # Candidatos que os mestres costumam jogar nessa posição
    candidatos = []
    for m in (ultimo_livro.get("moves") or [])[:4]:
        candidatos.append(
            {
                "uci": m.get("uci"),
                "san": m.get("san"),
                "total_partidas": m.get("white", 0) + m.get("draws", 0) + m.get("black", 0),
                "white": m.get("white", 0),
                "draws": m.get("draws", 0),
                "black": m.get("black", 0),
            }
        )

    return {
        "sucesso": True,
        "disponivel": True,
        "ficou_no_livro": False,
        "ply_saida": ply_saida,
        "numero_lance_saida": numero_lance,
        "cor_saida": cor_saida,
        "quem_saiu": quem_saiu,
        "lance_uci": lance_uci,
        "lance_san": lance_san,
        "nome_abertura": opening_info.get("name"),
        "eco": opening_info.get("eco"),
        "stats_ultimo_livro": {
            "white": ultimo_livro.get("white", 0),
            "draws": ultimo_livro.get("draws", 0),
            "black": ultimo_livro.get("black", 0),
            "total": total_games,
        },
        "candidatos_recomendados": candidatos,
    }

