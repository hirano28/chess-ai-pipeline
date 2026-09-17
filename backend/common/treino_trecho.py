"""Lógica pura do treino de trecho — o formato de drill dos eventos EROSAO (D-66).

Um PICO é um lance: existe um "lance certo", e treiná-lo é mostrar a posição e
pedir o lance (D-48). Uma EROSAO não é um lance, é uma JANELA de 8 lances do
jogador em que a posição escorregou sem nenhum erro isolado grande o bastante
para virar pico. Perguntar "qual era o lance certo?" numa janela dessas seria
inventar um gabarito que o próprio detector não tem — por isso os 106 eventos
ficaram fora da fila desde o D-48.

O formato que cabe nela é refazer o trecho: o jogador joga os mesmos 8 lances de
novo, contra um motor limitado ao rating do adversário real daquela partida, e
no fim mede-se a MESMA coisa que detectou o evento — a queda líquida de
win_percent entre o começo e o fim da janela (`detectar_erosao` em
backend/analise_engine/analisar_partidas.py usa exatamente
`janela[0].win_percent_before - janela[-1].win_percent_after`).

Nada aqui toca o motor nem o banco: o módulo existe para ser testável sem
Stockfish e sem Supabase. O estado do trecho em andamento vive num jsonb da
linha da fila (`progresso_trecho`), e é reconstruído a cada requisição pelo
replay dos SAN já jogados — o cliente nunca manda a posição, só o lance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import chess

# Faixa que o UCI_Elo do Stockfish aceita. Abaixo do piso o motor ignora o
# valor; melhor cravar o piso do que mandar um número que ele descarta em
# silêncio. O adversário mais fraco dos eventos reais tem 1171 de rating, então
# esse clamp acontece de verdade, não é defesa teórica.
ELO_MINIMO_STOCKFISH = 1320
ELO_MAXIMO_STOCKFISH = 3190
# Usado quando a partida não registrou rating de nenhum dos dois lados (1 dos
# 106 eventos). Um adversário de clube: nem sparring de brincadeira, nem motor.
ELO_PADRAO_OPONENTE = 1600

# Tamanho de janela usado quando `numero_lance_fim` está ausente ou incoerente.
# É o mesmo default de WINDOW_SIZE_EROSAO no detector.
TOTAL_LANCES_PADRAO = 8


class ProgressoCorrompidoError(ValueError):
    """O histórico gravado não reconstrói uma partida legal.

    Existe como tipo próprio para o servidor distinguir "estado quebrado"
    (recomeça o trecho) de "lance inválido do usuário" (400), sem ter que ler
    o texto da mensagem. Herda de ValueError porque é o que quem chama já
    esperava antes de o tipo existir.
    """


@dataclass(frozen=True)
class LanceDaCurva:
    """Quanto um lance do jogador custou, dentro do trecho refeito."""

    numero: int
    lance: str
    win_antes: float
    win_depois: float
    queda: float


def total_lances_do_trecho(
    numero_lance: int | None, numero_lance_fim: int | None
) -> int:
    """Quantos lances do JOGADOR a janela cobre.

    `numero_lance`/`numero_lance_fim` são `board.fullmove_number` do primeiro e
    do último lance da janela. Como todos os lances da janela são da mesma cor,
    os números de lance são consecutivos e a contagem é a diferença + 1 (os 106
    eventos reais têm todos diferença 7, ou seja, 8 lances).

    Dados incoerentes caem no default em vez de derrubar o card: uma janela de
    tamanho zero ou negativo tornaria o drill impossível de concluir.
    """

    if not isinstance(numero_lance, int) or not isinstance(numero_lance_fim, int):
        return TOTAL_LANCES_PADRAO
    total = numero_lance_fim - numero_lance + 1
    if total < 1:
        return TOTAL_LANCES_PADRAO
    return total


def elo_do_oponente(
    rating_oponente: int | None, rating_proprio: int | None = None
) -> int:
    """Força do motor que vai jogar o trecho contra o usuário.

    O adversário real daquela partida é a referência certa: um Stockfish inteiro
    transformaria toda tentativa em derrota (e, via SM-2, prenderia o card na
    nota mínima para sempre), e um motor fraco demais daria um "você segurou"
    que não significa nada. Refazer o trecho só é comparável com o que
    aconteceu se a resistência for parecida.

    Sem o rating do adversário, o do próprio jogador é a melhor aproximação
    disponível — em partidas pareadas por rating os dois andam juntos.
    """

    for candidato in (rating_oponente, rating_proprio):
        if isinstance(candidato, int) and candidato > 0:
            return max(ELO_MINIMO_STOCKFISH, min(ELO_MAXIMO_STOCKFISH, candidato))
    return ELO_PADRAO_OPONENTE


def reconstruir_tabuleiro(fen_inicial: str, lances: list[str]) -> chess.Board:
    """Reaplica os SAN já jogados sobre a posição inicial da janela.

    É assim que o servidor sabe onde o trecho está sem confiar em nada que o
    cliente mande: a posição é derivada do histórico gravado, e o cliente só
    envia o próximo lance. Um SAN ilegal aqui significa estado corrompido, não
    erro do usuário — por isso estoura `ProgressoCorrompidoError`, que quem
    chama converte em "recomeçar o trecho", nunca num 400 culpando quem
    respondeu.
    """

    board = chess.Board(fen_inicial)
    for indice, san in enumerate(lances):
        try:
            board.push_san(san)
        except ValueError as error:
            raise ProgressoCorrompidoError(
                f"Progresso do trecho corrompido: o lance {indice + 1} ('{san}') "
                f"não é legal na posição reconstruída."
            ) from error
    return board


def _lista_de(valor: Any, tipo: type | tuple[type, ...]) -> bool:
    """`valor` é uma lista em que TODO item é do tipo esperado.

    Descartar item a item seria pior do que rejeitar o conjunto: sumir com um
    lance do meio do histórico produz um estado que ainda "fecha" nas contagens
    e reconstrói uma posição errada em silêncio.
    """

    return isinstance(valor, list) and all(
        isinstance(item, tipo) and not isinstance(item, bool) for item in valor
    )


def progresso_inicial(fen_inicial: str, total_lances: int) -> dict[str, Any]:
    """Estado de um trecho que ainda não teve nenhum lance jogado."""

    return {
        "fen_inicial": fen_inicial,
        "total_lances": total_lances,
        "lances": [],
        "win_antes": [],
        "win_depois": [],
    }


def normalizar_progresso(
    bruto: Any, fen_inicial: str, total_lances: int
) -> dict[str, Any]:
    """Lê o jsonb da fila com desconfiança, caindo no estado zerado se preciso.

    A coluna é nullable e só passa a existir a partir do D-66: card antigo,
    jsonb nulo e jsonb com formato inesperado são todos "o trecho ainda não
    começou". O `fen_inicial` e o `total_lances` vêm sempre de
    `lances_criticos`, nunca do jsonb — o progresso guarda o caminho andado, e
    o ponto de partida continua sendo o do evento.
    """

    if not isinstance(bruto, dict):
        return progresso_inicial(fen_inicial, total_lances)

    lances = bruto.get("lances") or []
    win_antes = bruto.get("win_antes") or []
    win_depois = bruto.get("win_depois") or []
    if not _lista_de(lances, str) or not _lista_de(win_antes, (int, float)):
        return progresso_inicial(fen_inicial, total_lances)
    if not _lista_de(win_depois, (int, float)):
        return progresso_inicial(fen_inicial, total_lances)
    win_antes = [float(item) for item in win_antes]
    win_depois = [float(item) for item in win_depois]

    # Invariantes do estado, e o que a violação de cada um significa.
    #
    # Há uma leitura de win% antes e outra depois para cada lance do jogador.
    # Os SAN alternam jogador/motor, então `k` lances do jogador produzem `2k`
    # SAN — exceto no último, que não tem resposta do motor porque a janela
    # acabou ali (`2k-1`). Um comprimento ímpar em qualquer outro ponto
    # significaria que a vez é do MOTOR, e a próxima requisição empurraria o
    # lance do usuário na posição errada.
    #
    # Nada disso deveria acontecer: quem grava é só este servidor, e grava o
    # lance e a resposta juntos. Mas o estado mora num jsonb solto, e um
    # progresso ilegível é melhor recomeçado do que usado para calcular um
    # veredito sobre números que não fecham.
    jogador = len(win_depois)
    if len(win_antes) != jogador:
        return progresso_inicial(fen_inicial, total_lances)
    if len(lances) == 2 * jogador - 1:
        if jogador < total_lances:
            return progresso_inicial(fen_inicial, total_lances)
    elif len(lances) != 2 * jogador:
        return progresso_inicial(fen_inicial, total_lances)

    return {
        "fen_inicial": fen_inicial,
        "total_lances": total_lances,
        "lances": lances,
        "win_antes": win_antes,
        "win_depois": win_depois,
    }


def lances_do_jogador_feitos(progresso: dict[str, Any]) -> int:
    """Quantos lances do JOGADOR já entraram no trecho."""

    return len(progresso.get("win_depois") or [])


def trecho_concluido(progresso: dict[str, Any]) -> bool:
    """O jogador já jogou todos os lances da janela?"""

    total = int(progresso.get("total_lances") or TOTAL_LANCES_PADRAO)
    return lances_do_jogador_feitos(progresso) >= total


def queda_liquida_do_trecho(progresso: dict[str, Any]) -> float:
    """A mesma conta que detectou o evento: win% no início − win% no fim.

    "No fim" é depois do último lance do JOGADOR, não depois da resposta do
    motor — igual a `detectar_erosao`, que fecha a janela em
    `janela[-1].win_percent_after`. Incluir a resposta do adversário mudaria o
    instrumento e o número deixaria de ser comparável com o da partida.
    """

    win_antes = progresso.get("win_antes") or []
    win_depois = progresso.get("win_depois") or []
    if not win_antes or not win_depois:
        return 0.0
    return round(float(win_antes[0]) - float(win_depois[-1]), 2)


def curva_do_trecho(progresso: dict[str, Any]) -> list[LanceDaCurva]:
    """Custo lance a lance, para a revelação do fim.

    Durante o trecho nada disso aparece: erosão é justamente o que se perde sem
    perceber, e um "-4%" a cada lance transformaria o drill em oito exercícios
    táticos com placar. A curva inteira só faz sentido depois, quando dá para
    ver onde o escorregão começou.
    """

    lances = progresso.get("lances") or []
    win_antes = progresso.get("win_antes") or []
    win_depois = progresso.get("win_depois") or []

    curva: list[LanceDaCurva] = []
    for indice, depois in enumerate(win_depois):
        # Lances do jogador ocupam os índices pares (0, 2, 4...); os ímpares
        # são as respostas do motor.
        posicao_san = indice * 2
        san = lances[posicao_san] if posicao_san < len(lances) else "?"
        antes = float(win_antes[indice]) if indice < len(win_antes) else float(depois)
        curva.append(
            LanceDaCurva(
                numero=indice + 1,
                lance=san,
                win_antes=round(antes, 2),
                win_depois=round(float(depois), 2),
                queda=round(antes - float(depois), 2),
            )
        )
    return curva


def classificar_trecho(
    queda_liquida: float, queda_original: float | None, limiar_erosao: float
) -> str:
    """Traduz o trecho refeito para BOM/SUBOTIMO/RUIM (a escala do SM-2).

    O limiar de BOM é o mesmo que define o evento (`EROSAO_THRESHOLD_PERCENT`,
    15% por padrão): segurar a janela abaixo dele significa que, medido pelo
    instrumento que criou este card, não houve erosão desta vez. É um alvo
    absoluto de propósito — um critério só relativo ("caiu menos que da outra
    vez") deixaria o card sem nenhuma forma de se formar.

    Entre o limiar e a queda original, o jogador errou de novo, mas errou
    menos: SUBOTIMO. Repetir ou piorar a queda da partida é RUIM.
    """

    if queda_liquida < limiar_erosao:
        return "BOM"
    if queda_original is not None and queda_liquida < queda_original:
        return "SUBOTIMO"
    return "RUIM"


def resumo_do_veredito(
    qualidade: str, queda_liquida: float, queda_original: float | None
) -> str:
    """Uma frase dizendo o que o número significa, sem eufemismo nem exagero."""

    original = (
        f" Na partida, o mesmo trecho custou {queda_original:.1f}%."
        if queda_original is not None
        else ""
    )
    if qualidade == "BOM":
        if queda_liquida < 0:
            return (
                f"Você não só segurou o trecho como melhorou a posição em "
                f"{abs(queda_liquida):.1f}%." + original
            )
        return (
            f"Você segurou o trecho: {queda_liquida:.1f}% de queda líquida ao "
            f"longo da janela." + original
        )
    if qualidade == "SUBOTIMO":
        return (
            f"A posição escorregou de novo ({queda_liquida:.1f}%), mas menos do "
            f"que na partida." + original
        )
    return (
        f"O trecho escorregou como da primeira vez: {queda_liquida:.1f}% de "
        f"queda líquida." + original
    )
