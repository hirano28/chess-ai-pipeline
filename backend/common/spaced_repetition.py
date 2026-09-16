"""Agendamento de repetição espaçada (SM-2 simplificado) para a fila de
treino diário (D-48).

Reaproveita a nota de qualidade já calculada por `classificar_qualidade_lance`
(`backend/agentes/revisar_pensamento.py`) — 'BOM'/'SUBOTIMO'/'RUIM', puramente
threshold sobre `queda_win_percent`, sem Gemini — traduzida para a escala 0-5
do SM-2 original (mesmo algoritmo usado pelo Anki e pela maior parte dos
concorrentes de repetição espaçada pesquisados).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

QUALIDADE_LANCE_PARA_NOTA_SM2: dict[str, int] = {
    "BOM": 5,
    "SUBOTIMO": 3,
    "RUIM": 1,
}

FATOR_FACILIDADE_MINIMO = 1.3
NOTA_MINIMA_PARA_ACERTO = 3


@dataclass(frozen=True)
class AgendamentoAtualizado:
    """Novo estado de agendamento de um card da fila, após uma revisão."""

    intervalo_dias: int
    fator_facilidade: float
    repeticoes: int
    proxima_revisao_data: date


def nota_sm2_da_qualidade_lance(qualidade_lance: str) -> int:
    """Traduz BOM/SUBOTIMO/RUIM (classificar_qualidade_lance) para 0-5 do SM-2.

    Qualidade desconhecida (não deveria acontecer, mas é defensivo) é tratada
    como RUIM: melhor reagendar cedo demais do que tarde demais.
    """

    return QUALIDADE_LANCE_PARA_NOTA_SM2.get(qualidade_lance, 1)


def atualizar_agendamento(
    intervalo_dias: int,
    fator_facilidade: float,
    repeticoes: int,
    qualidade: int,
    hoje: date,
) -> AgendamentoAtualizado:
    """SM-2 simplificado. `qualidade` é 0-5 (ver `nota_sm2_da_qualidade_lance`).

    qualidade < 3 (errou) reseta a série: `repeticoes` volta a 0 e a próxima
    revisão é amanhã. qualidade >= 3 (acertou) avança a série: 1ª repetição
    vira intervalo de 1 dia, a 2ª vira 6 dias, as seguintes multiplicam o
    intervalo anterior pelo fator de facilidade (que cresce ou encolhe a cada
    resposta, sem nunca cair abaixo de 1.3 — os mesmos números do SM-2/Anki).
    """

    if qualidade < NOTA_MINIMA_PARA_ACERTO:
        novo_intervalo = 1
        novas_repeticoes = 0
    else:
        if repeticoes == 0:
            novo_intervalo = 1
        elif repeticoes == 1:
            novo_intervalo = 6
        else:
            novo_intervalo = round(intervalo_dias * fator_facilidade)
        novas_repeticoes = repeticoes + 1

    novo_fator = fator_facilidade + (
        0.1 - (5 - qualidade) * (0.08 + (5 - qualidade) * 0.02)
    )
    novo_fator = max(FATOR_FACILIDADE_MINIMO, round(novo_fator, 2))

    return AgendamentoAtualizado(
        intervalo_dias=novo_intervalo,
        fator_facilidade=novo_fator,
        repeticoes=novas_repeticoes,
        proxima_revisao_data=hoje + timedelta(days=novo_intervalo),
    )
