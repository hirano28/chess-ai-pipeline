"""Classificação da cadência (ritmo de jogo) de uma partida, a partir do
header `TimeControl` do PGN (D-57).

Por que isto existe: 74% do corpus analisado é blitz de 3 a 5 minutos, e até
aqui não havia coluna de cadência em `partidas` — não dava nem para filtrar.
Toda conclusão do Hexágono sobre "o gargalo do jogador" saía misturada com o
efeito do relógio, e a tag mais frequente ser `calculo_tatico_deficiente`
podia significar tanto "calcula mal" quanto "joga rápido demais". Sem separar
as duas coisas, o diagnóstico central do produto é ambíguo.

Os cortes são os do Lichess, sobre a duração ESTIMADA da partida
(`base + 40 * incremento`, a estimativa que eles próprios usam para classificar
uma partida em bullet/blitz/rapid/classical). Adotar a convenção de uma
plataforma conhecida é melhor que inventar faixas próprias: o usuário já
reconhece esses nomes, e a comparação com as estatísticas dele no Lichess
continua fazendo sentido.

Diferente de `parse_time_control` (backend/ingestao/backfill_tempos_chesscom.py),
aqui **não existe fallback para 300s**. Aquele default serve ao cálculo de
tempo por lance, onde chutar 5 minutos é melhor que não calcular nada. Para
classificar, chutar seria pior que admitir: uma partida sem header viraria
"blitz" e contaminaria exatamente a estatística que esta coluna veio limpar.
"""

from __future__ import annotations

BULLET = "BULLET"
BLITZ = "BLITZ"
RAPIDA = "RAPIDA"
CLASSICA = "CLASSICA"
CORRESPONDENCIA = "CORRESPONDENCIA"
DESCONHECIDA = "DESCONHECIDA"

CADENCIAS: tuple[str, ...] = (
    BULLET,
    BLITZ,
    RAPIDA,
    CLASSICA,
    CORRESPONDENCIA,
    DESCONHECIDA,
)

# Rótulos para tela. Mantidos aqui, junto das chaves, para não divergirem.
ROTULOS_CADENCIA: dict[str, str] = {
    BULLET: "Bullet",
    BLITZ: "Blitz",
    RAPIDA: "Rápida",
    CLASSICA: "Clássica",
    CORRESPONDENCIA: "Correspondência",
    DESCONHECIDA: "Cadência desconhecida",
}

# Cortes do Lichess sobre `base + 40 * incremento`, em segundos.
LIMITE_BULLET = 179
LIMITE_BLITZ = 479
LIMITE_RAPIDA = 1499


def interpretar_time_control(
    time_control: str | None,
) -> tuple[int | None, int | None]:
    """Devolve (base_segundos, incremento_segundos) do header `TimeControl`.

    `(None, None)` quando o header está ausente, é `-`/`?`, ou não é um tempo
    de relógio (partida por correspondência usa `dias/segundos`). Devolver
    None aqui é o que permite ao classificador dizer DESCONHECIDA em vez de
    inventar um número.
    """

    bruto = (time_control or "").strip()
    if not bruto or bruto in {"-", "?"}:
        return None, None
    if "/" in bruto:
        # Correspondência, ex.: "1/86400" (1 lance por dia). Não tem base de
        # relógio comparável às outras cadências.
        return None, None

    partes = bruto.split("+")
    try:
        base = int(float(partes[0]))
        incremento = int(float(partes[1])) if len(partes) > 1 else 0
    except (ValueError, IndexError):
        return None, None
    if base < 0 or incremento < 0:
        return None, None
    return base, incremento


def classificar_cadencia(time_control: str | None) -> str:
    """Nome da cadência para um header `TimeControl`."""

    bruto = (time_control or "").strip()
    if "/" in bruto:
        return CORRESPONDENCIA

    base, incremento = interpretar_time_control(time_control)
    if base is None or incremento is None:
        return DESCONHECIDA

    estimativa = base + 40 * incremento
    if estimativa <= LIMITE_BULLET:
        return BULLET
    if estimativa <= LIMITE_BLITZ:
        return BLITZ
    if estimativa <= LIMITE_RAPIDA:
        return RAPIDA
    return CLASSICA


def campos_de_cadencia(time_control: str | None) -> dict[str, object]:
    """As três colunas que `partidas` ganhou no D-57, prontas para o insert."""

    base, incremento = interpretar_time_control(time_control)
    return {
        "cadencia": classificar_cadencia(time_control),
        "tempo_base_segundos": base,
        "incremento_segundos": incremento,
    }


def time_control_do_pgn(pgn: str | None) -> str | None:
    """Lê o header `TimeControl` de um PGN cru, sem montar o jogo inteiro.

    Feito por varredura de texto de propósito: o backfill roda sobre centenas
    de PGNs e só precisa de uma linha de cabeçalho — parsear a partida inteira
    com python-chess para isso custaria ordens de grandeza mais.
    """

    if not pgn:
        return None
    for linha in pgn.splitlines():
        despida = linha.strip()
        if not despida.startswith("["):
            # Cabeçalhos vêm todos antes dos lances; ao sair deles, acabou.
            if despida:
                break
            continue
        if despida.startswith('[TimeControl "'):
            fim = despida.find('"', len('[TimeControl "'))
            if fim > 0:
                return despida[len('[TimeControl "') : fim]
    return None
