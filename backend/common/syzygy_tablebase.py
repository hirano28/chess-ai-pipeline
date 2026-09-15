"""Integração com a Syzygy Tablebase do Lichess (tablebase.lichess.org).

Permite avaliar posições de final com até 7 peças (3 a 7 peças) com 100% de
precisão matemática provada. Identifica blunders teóricos de conversão e defesa
(ex: posição ganha transformada em empate/derrota) sem depender exclusivamente
da avaliação heurística em centipawns do Stockfish.

API pública, sem necessidade de autenticação.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import chess
import requests

TABLEBASE_URL = "https://tablebase.lichess.org/standard"
MAX_PECAS_SYZYGY = 7
REQUEST_TIMEOUT_S = 5


def contar_pecas_fen(fen: str) -> int:
    """Retorna o número total de peças no tabuleiro para o FEN informado."""
    try:
        board = chess.Board(fen)
        return len(board.piece_map())
    except Exception:
        return 99


def consultar_syzygy(fen: str) -> dict[str, Any] | None:
    """Consulta a Syzygy Tablebase do Lichess para um FEN de até 7 peças.

    Retorna None se a posição tiver mais de 7 peças, for ilegal ou a API falhar.
    """
    try:
        board = chess.Board(fen)
        if len(board.piece_map()) > MAX_PECAS_SYZYGY:
            return None
        # Verifica se o rei que não joga está em xeque (posição ilegal)
        if not board.is_valid():
            return None
    except Exception:
        return None

    url = f"{TABLEBASE_URL}?fen={quote(fen)}"
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "ChessAIPipeline/1.0"},
            timeout=REQUEST_TIMEOUT_S,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def avaliar_lance_final_syzygy(
    fen_antes: str,
    lance_uci_ou_san: str,
) -> dict[str, Any]:
    """Avalia objetivamente se um lance de final com <= 7 peças manteve o resultado provado.

    Classifica se houve:
    - 'erro_conversao': a posição era vitória forçada ('win'), mas o lance jogado virou 'draw' ou 'loss'.
    - 'erro_defesa': a posição era empate teórico ('draw'), mas o lance jogado virou 'loss'.
    - 'preciso': manteve o melhor desfecho possível.
    - 'irreversivel': a posição já era derrota inevitável ('loss').
    """
    num_pecas = contar_pecas_fen(fen_antes)
    if num_pecas > MAX_PECAS_SYZYGY:
        return {
            "elegivel_syzygy": False,
            "motivo": f"Posição possui {num_pecas} peças (máximo para Syzygy é {MAX_PECAS_SYZYGY}).",
            "num_pecas": num_pecas,
        }

    data = consultar_syzygy(fen_antes)
    if not data:
        return {
            "elegivel_syzygy": False,
            "motivo": "Consulta à Tablebase não retornou dados ou posição é inválida.",
            "num_pecas": num_pecas,
        }

    cat_antes = data.get("category")  # 'win', 'loss', 'draw', 'maybe-win', etc.
    dtz_antes = data.get("dtz")
    dtm_antes = data.get("dtm")
    moves = data.get("moves") or []

    # Normaliza o lance de busca para comparar com moves (uci ou san)
    lance_alvo = lance_uci_ou_san.strip().replace("+", "").replace("#", "")
    info_lance = None
    for m in moves:
        m_san = m.get("san", "").replace("+", "").replace("#", "")
        m_uci = m.get("uci", "")
        if lance_alvo in (m_san, m_uci):
            info_lance = m
            break

    # Categoria resultante do lance do jogador
    # Na resposta da API Lichess, 'moves[i].category' indica o desfecho da perspectiva de quem joga:
    # 'win' = lance vence, 'draw' = lance empata, 'loss' = lance perde
    cat_jogado = info_lance.get("category") if info_lance else None

    # Avaliação do erro teórico
    eh_blunder_teorico = False
    tipo_erro_final: str | None = None
    veredito_pt: str

    if cat_antes == "win":
        if cat_jogado in ("draw", "loss"):
            eh_blunder_teorico = True
            tipo_erro_final = "erro_conversao"
            veredito_pt = f"Blunder teórico de final: vitória provada perdida (virou {cat_jogado})."
        else:
            veredito_pt = "Lance preciso: vitória teórica mantida."
    elif cat_antes == "draw":
        if cat_jogado == "loss":
            eh_blunder_teorico = True
            tipo_erro_final = "erro_defesa"
            veredito_pt = "Blunder teórico de final: posição de empate entregue em derrota."
        else:
            veredito_pt = "Lance preciso: empate teórico mantido."
    elif cat_antes == "loss":
        veredito_pt = "Posição já era derrota teoricamente inevitável contra jogo perfeito."
    else:
        veredito_pt = f"Resultado teórico Syzygy: {cat_antes}."

    # Melhores lances matemáticos alternativos
    melhores_lances = []
    melhor_cat = "win" if cat_antes == "win" else ("draw" if cat_antes == "draw" else "loss")
    for m in moves:
        if m.get("category") == melhor_cat:
            melhores_lances.append(
                {
                    "uci": m.get("uci"),
                    "san": m.get("san"),
                    "categoria": m.get("category"),
                    "dtz": m.get("dtz"),
                    "dtm": m.get("dtm"),
                }
            )
            if len(melhores_lances) >= 3:
                break

    return {
        "elegivel_syzygy": True,
        "num_pecas": num_pecas,
        "categoria_antes": cat_antes,
        "categoria_lance_jogado": cat_jogado,
        "dtz": dtz_antes,
        "dtm": dtm_antes,
        "eh_blunder_teorico": eh_blunder_teorico,
        "tipo_erro_final": tipo_erro_final,
        "veredito_pt": veredito_pt,
        "melhores_lances": melhores_lances,
    }

