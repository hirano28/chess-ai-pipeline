"""Funções matemáticas de avaliação de posições de xadrez."""

from __future__ import annotations

import math

CENTIPAWNS_CLAMP = 10_000
WIN_PERCENT_K = 0.00368208


def centipawns_para_win_percent(cp: int) -> float:
    """Converte centipawns em probabilidade de vitória (fórmula do Lichess)."""

    cp_limitado = max(-CENTIPAWNS_CLAMP, min(CENTIPAWNS_CLAMP, cp))
    return 50 + 50 * (2 / (1 + math.exp(-WIN_PERCENT_K * cp_limitado)) - 1)
