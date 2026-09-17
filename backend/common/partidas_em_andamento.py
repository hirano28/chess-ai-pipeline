"""Partidas em andamento no Lichess e no Chess.com, para a consulta ao vivo (D-69).

Sincronizar tira o trabalho de espelhar lance a lance: a tela escolhe a partida
e o servidor busca a posição direto na plataforma. Vale para qualquer partida
do dono — contra bot, amigo, aluno ou professor.

O que cada plataforma permite, verificado na documentação e na API em 17/09/2026:

**Lichess.** Os endpoints públicos de partida em andamento
(`/game/export/{id}`, `/api/stream/game/{id}`) são **atrasados em 3 lances** de
propósito ("to prevent cheat bots"). A posição atual, sem atraso, só vem de
`/api/account/playing`, que devolve as partidas do dono do token OAuth — a FEN e
o último lance, mas não o histórico. O histórico vem do export atrasado, e os
lances que faltam entre ele e a posição atual são reconstruídos por busca
(`completar_lances`). Funciona com o escopo `puzzle:read` que o OAuth já tem.

**Chess.com.** A API pública só lista partidas **diárias** em andamento
(`/pub/player/{usuario}/games`), com PGN completo e FEN atual. Partidas ao vivo
(blitz, rápidas) não aparecem em endpoint público nenhum: para elas o espelho
continua manual, ou colando o PGN.

Este módulo só lê. Não faz lance, não abre stream contínuo e não guarda token.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from typing import Any

import chess
import chess.pgn
import requests

LICHESS_PLAYING_URL = "https://lichess.org/api/account/playing"
LICHESS_EXPORT_URL = "https://lichess.org/game/export/{game_id}"
CHESSCOM_GAMES_URL = "https://api.chess.com/pub/player/{usuario}/games"
USER_AGENT = "chess-ai-pipeline/consulta-ao-vivo (contato pelo repositorio)"
TIMEOUT_SEGUNDOS = 10

# "Atrasado em 3 lances" pode ser 3 meios-lances ou 3 lances completos. Seis
# meios-lances cobre os dois com folga; a poda por casas diferentes mantém a
# busca pequena mesmo assim.
MAX_MEIOS_LANCES_FALTANTES = 6
# Um lance muda no máximo 4 casas (roque: rei e torre saem e chegam).
CASAS_POR_MEIO_LANCE = 4
# Teto de posições visitadas na reconstrução. A busca roda dentro de uma
# requisição HTTP: passar disso devolve "histórico incompleto", nunca espera.
MAX_NOS_BUSCA = 60_000

VARIANTES_LICHESS = frozenset({"standard", "fromPosition"})


class PlataformaIndisponivelError(RuntimeError):
    """A plataforma recusou ou não respondeu (limite de requisições, fora do ar)."""


@dataclass
class PartidaEmAndamento:
    """Uma partida do dono em curso, do jeito que a tela precisa para escolher."""

    plataforma: str
    game_id: str
    cor: str
    fen: str
    vez_do_jogador: bool
    adversario: str
    ranqueada: bool
    ritmo: str
    fen_inicial: str | None = None
    lances: list[str] = field(default_factory=list)
    historico_completo: bool = True
    url: str = ""
    ultimo_lance_uci: str | None = None


def _cor(valor: str | None) -> str:
    return "BRANCAS" if (valor or "").lower() == "white" else "PRETAS"


def _mascara_diferente(board: chess.Board, alvo: chess.Board) -> int:
    """Bitboard das casas cujo conteúdo difere entre as duas posições.

    Por bitboard e não casa a casa: a busca chama isto em cada nó, e a versão
    com `piece_at` nas 64 casas era o gargalo medido.
    """

    mascara = 0
    for cor in chess.COLORS:
        for tipo in chess.PIECE_TYPES:
            mascara |= board.pieces_mask(tipo, cor) ^ alvo.pieces_mask(tipo, cor)
    return mascara


def _mesma_posicao(board: chess.Board, alvo: chess.Board) -> bool:
    # Peças e vez bastam. Direitos de roque não entram de propósito: se a FEN
    # atual vier sem eles (ver `_fen_completa`), a comparação falharia sempre, e
    # duas ordens de lances que chegam às mesmas peças com a mesma vez não se
    # distinguem por roque na prática.
    return board.board_fen() == alvo.board_fen() and board.turn == alvo.turn


def completar_lances(
    fen_inicial: str | None,
    lances_conhecidos: list[str],
    fen_atual: str,
    ultimo_lance_uci: str | None = None,
    max_meios_lances: int = MAX_MEIOS_LANCES_FALTANTES,
) -> list[str] | None:
    """Acha os lances que levam do histórico atrasado até a posição atual.

    Devolve o histórico completo em SAN, ou None se não houver caminho dentro do
    limite (histórico conhecido inconsistente, ou atraso maior que o previsto).

    A busca é em profundidade, com duas podas: se faltam `n` meios-lances e o
    tabuleiro ainda difere do alvo em mais de `4n` casas, não há como chegar; e
    o último meio-lance, quando conhecido (`lastMove` do Lichess), é fixo.
    """

    try:
        board = chess.Board(fen_inicial) if fen_inicial else chess.Board()
        for lance in lances_conhecidos:
            board.push_san(lance)
        alvo = chess.Board(fen_atual)
    except ValueError:
        return None

    if _mesma_posicao(board, alvo):
        return list(lances_conhecidos)

    ultimo: chess.Move | None = None
    if ultimo_lance_uci:
        try:
            ultimo = chess.Move.from_uci(ultimo_lance_uci)
        except ValueError:
            ultimo = None

    nos_visitados = 0

    def buscar(profundidade: int, caminho: list[chess.Move]) -> list[chess.Move] | None:
        nonlocal nos_visitados
        nos_visitados += 1
        if nos_visitados > MAX_NOS_BUSCA:
            raise _BuscaEsgotada
        diferentes = _mascara_diferente(board, alvo)
        if chess.popcount(diferentes) > CASAS_POR_MEIO_LANCE * profundidade:
            return None
        if profundidade == 1 and ultimo is not None:
            candidatos = [ultimo] if ultimo in board.legal_moves else []
        else:
            # Só se mexe peça que está numa casa diferente da posição final.
            # É a poda que torna a busca viável: sem ela, 6 meios-lances são
            # dezenas de milhões de nós (medido: estourou 280 s com partidas
            # reais). O caso que ela perde — uma peça sair da casa certa e
            # voltar dentro da janela — só degrada para "histórico incompleto".
            candidatos = [
                move
                for move in board.legal_moves
                if diferentes & chess.BB_SQUARES[move.from_square]
            ]
            # Primeiro os lances que deixam a peça onde ela está no alvo: é o
            # caminho real na maioria das vezes, e achá-lo cedo encerra a busca.
            candidatos.sort(
                key=lambda move: alvo.piece_at(move.to_square) != board.piece_at(move.from_square)
            )
        for move in candidatos:
            board.push(move)
            try:
                if _mesma_posicao(board, alvo):
                    if ultimo is None or move == ultimo:
                        return caminho + [move]
                elif profundidade > 1:
                    achado = buscar(profundidade - 1, caminho + [move])
                    if achado is not None:
                        return achado
            finally:
                board.pop()
        return None

    def em_san(moves: list[chess.Move]) -> list[str]:
        # SAN só no fim: gerá-lo em cada nó (verifica xeque e mate) custava caro.
        replay = board.copy()
        sans: list[str] = []
        for move in moves:
            sans.append(replay.san(move))
            replay.push(move)
        return sans

    # Profundidade crescente: o caminho mais curto é o que de fato aconteceu.
    # A vez de jogar fixa a paridade — com as brancas a jogar nos dois lados, o
    # número de meios-lances faltantes é par —, então metade das profundidades
    # nem precisa ser tentada.
    paridade = 0 if board.turn == alvo.turn else 1
    try:
        for profundidade in range(1, max_meios_lances + 1):
            if profundidade % 2 != paridade:
                continue
            achado = buscar(profundidade, [])
            if achado is not None:
                return list(lances_conhecidos) + em_san(achado)
    except _BuscaEsgotada:
        return None
    return None


class _BuscaEsgotada(Exception):
    """A busca passou do teto de nós; melhor histórico incompleto que servidor travado."""


def _get(url: str, **kwargs: Any) -> requests.Response:
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    try:
        resposta = requests.get(url, headers=headers, timeout=TIMEOUT_SEGUNDOS, **kwargs)
    except requests.RequestException as error:
        raise PlataformaIndisponivelError(f"Sem resposta de {url.split('/')[2]}: {error}") from error
    if resposta.status_code == 429:
        raise PlataformaIndisponivelError(
            "A plataforma pediu para esperar (limite de requisições). Tente de novo em um minuto."
        )
    return resposta


def _adversario_lichess(item: dict[str, Any]) -> str:
    oponente = item.get("opponent") or {}
    if oponente.get("ai"):
        return f"Stockfish nível {oponente['ai']}"
    nome = oponente.get("username") or oponente.get("id") or "Anônimo"
    rating = oponente.get("rating")
    return f"{nome} ({rating})" if rating else str(nome)


def listar_lichess(token: str) -> list[PartidaEmAndamento]:
    """Partidas em andamento do dono do token, com a posição atual sem atraso."""

    resposta = _get(
        LICHESS_PLAYING_URL,
        headers={"Authorization": f"Bearer {token}"},
        params={"nb": 15},
    )
    if resposta.status_code == 401:
        raise PlataformaIndisponivelError(
            "O Lichess recusou a conexão da sua conta. Reconecte o Lichess no Perfil."
        )
    if resposta.status_code != 200:
        raise PlataformaIndisponivelError(f"O Lichess respondeu {resposta.status_code}.")

    partidas: list[PartidaEmAndamento] = []
    for item in resposta.json().get("nowPlaying") or []:
        variante = (item.get("variant") or {}).get("key")
        if variante not in VARIANTES_LICHESS or not item.get("gameId") or not item.get("fen"):
            continue
        cor = _cor(item.get("color"))
        # `fullId` NÃO é lido: ele identifica o jogador dentro da partida e
        # serve para jogar por ele. Nada aqui precisa disso.
        partidas.append(
            PartidaEmAndamento(
                plataforma="LICHESS",
                game_id=str(item["gameId"]),
                cor=cor,
                fen=_fen_completa(item["fen"], item.get("isMyTurn"), cor),
                vez_do_jogador=bool(item.get("isMyTurn")),
                adversario=_adversario_lichess(item),
                ranqueada=bool(item.get("rated")),
                ritmo=str(item.get("speed") or ""),
                url=f"https://lichess.org/{item['gameId']}",
                ultimo_lance_uci=item.get("lastMove") or None,
            )
        )
    return partidas


def _fen_completa(fen: str, vez_do_jogador: Any, cor: str) -> str:
    """O `fen` do /account/playing pode vir só com a colocação das peças.

    Sem o campo da vez, a posição é ambígua; `isMyTurn` e a cor resolvem. Roques
    e en passant, se ausentes, ficam desconhecidos ('-') — o motor avalia a
    posição do mesmo jeito, e a busca de histórico compara o que existe.
    """

    partes = fen.strip().split()
    if len(partes) >= 2:
        return fen.strip()
    jogador_branco = cor == "BRANCAS"
    brancas_jogam = jogador_branco if vez_do_jogador else not jogador_branco
    return f"{partes[0]} {'w' if brancas_jogam else 'b'} - - 0 1"


def historico_lichess(game_id: str, token: str | None = None) -> tuple[str | None, list[str]]:
    """Histórico (atrasado) de uma partida do Lichess: posição inicial e lances."""

    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resposta = _get(
        LICHESS_EXPORT_URL.format(game_id=game_id),
        headers=headers,
        params={"moves": "true", "clocks": "false", "evals": "false", "opening": "false"},
    )
    if resposta.status_code != 200:
        return None, []
    dados = resposta.json()
    lances = (dados.get("moves") or "").split()
    return dados.get("initialFen"), lances


def estado_lichess(
    token: str,
    game_id: str,
    conhecido: PartidaEmAndamento | None = None,
) -> PartidaEmAndamento | None:
    """Posição atual + histórico completo de uma partida em andamento do dono.

    None quando a partida não está (mais) em andamento para esta conta.

    `conhecido` é o último estado com histórico completo desta mesma partida. A
    partir dele faltam só os lances desde a última atualização — um ou dois —,
    e a reconstrução é instantânea, sem nem pedir o export ao Lichess. O export
    atrasado (e a busca de até 6 meios-lances, que pode levar segundos) fica
    para a primeira sincronização, ou para quando o conhecido não serve mais.
    """

    partida = next((p for p in listar_lichess(token) if p.game_id == game_id), None)
    if partida is None:
        return None

    if conhecido is not None and conhecido.historico_completo:
        completos = completar_lances(
            conhecido.fen_inicial, conhecido.lances, partida.fen, partida.ultimo_lance_uci
        )
        if completos is not None:
            partida.fen_inicial = conhecido.fen_inicial
            partida.lances = completos
            partida.historico_completo = True
            return partida

    fen_inicial, atrasados = historico_lichess(game_id, token)
    completos = completar_lances(
        fen_inicial, atrasados, partida.fen, partida.ultimo_lance_uci
    )
    partida.fen_inicial = fen_inicial
    if completos is not None:
        partida.lances = completos
        partida.historico_completo = True
    else:
        partida.lances = atrasados
        partida.historico_completo = False
    return partida


def _usuario_da_url(url: str | None) -> str:
    return (url or "").rstrip("/").rsplit("/", 1)[-1]


def listar_chesscom(usuario: str) -> list[PartidaEmAndamento]:
    """Partidas diárias em andamento no Chess.com (as ao vivo não são expostas)."""

    resposta = _get(CHESSCOM_GAMES_URL.format(usuario=usuario.lower()))
    if resposta.status_code == 404:
        return []
    if resposta.status_code != 200:
        raise PlataformaIndisponivelError(f"O Chess.com respondeu {resposta.status_code}.")

    partidas: list[PartidaEmAndamento] = []
    for item in resposta.json().get("games") or []:
        if item.get("rules") != "chess" or not item.get("url") or not item.get("fen"):
            continue
        brancas = _usuario_da_url(item.get("white"))
        pretas = _usuario_da_url(item.get("black"))
        cor = "BRANCAS" if brancas.lower() == usuario.lower() else "PRETAS"
        fen_inicial, lances = _lances_do_pgn(item.get("pgn") or "")
        partidas.append(
            PartidaEmAndamento(
                plataforma="CHESSCOM",
                game_id=_usuario_da_url(item["url"]),
                cor=cor,
                fen=item["fen"],
                vez_do_jogador=(item.get("turn") == "white") == (cor == "BRANCAS"),
                adversario=pretas if cor == "BRANCAS" else brancas,
                ranqueada=bool(item.get("rated")),
                ritmo=str(item.get("time_class") or "daily"),
                fen_inicial=fen_inicial,
                lances=lances,
                historico_completo=bool(lances) or not item.get("pgn"),
                url=str(item["url"]),
            )
        )
    return partidas


def _lances_do_pgn(pgn: str) -> tuple[str | None, list[str]]:
    if not pgn.strip():
        return None, []
    partida = chess.pgn.read_game(io.StringIO(pgn))
    if partida is None:
        return None, []
    fen_inicial = partida.headers.get("FEN")
    board = partida.board()
    lances: list[str] = []
    for move in partida.mainline_moves():
        lances.append(board.san(move))
        board.push(move)
    return fen_inicial, lances


def estado_chesscom(usuario: str, game_id: str) -> PartidaEmAndamento | None:
    return next((p for p in listar_chesscom(usuario) if p.game_id == game_id), None)


class CacheDeEstado:
    """Último estado de cada partida sincronizada, por dono.

    Serve a duas coisas. Dentro de `validade_segundos`, devolve o estado sem ir à
    plataforma: a tela atualiza a cada poucos segundos, e o Lichess pede, na
    documentação, uma requisição por vez e um minuto de espera ao receber 429.
    Depois disso, o estado guardado vira o `conhecido` da próxima reconstrução —
    é o que mantém a busca de histórico instantânea durante a partida.

    Fica em memória do processo de propósito: é um atalho, não uma fonte de
    verdade. Perdê-lo num novo deploy só custa uma reconstrução completa.
    """

    def __init__(self, validade_segundos: float = 3.0, maximo: int = 200) -> None:
        self.validade = validade_segundos
        self.maximo = maximo
        self._itens: dict[tuple[str, str, str], tuple[float, PartidaEmAndamento | None]] = {}

    def recente(self, chave: tuple[str, str, str]) -> tuple[bool, PartidaEmAndamento | None]:
        item = self._itens.get(chave)
        if item and time.monotonic() - item[0] < self.validade:
            return True, item[1]
        return False, None

    def ultimo(self, chave: tuple[str, str, str]) -> PartidaEmAndamento | None:
        item = self._itens.get(chave)
        return item[1] if item else None

    def guardar(self, chave: tuple[str, str, str], valor: PartidaEmAndamento | None) -> None:
        if len(self._itens) >= self.maximo and chave not in self._itens:
            mais_antiga = min(self._itens, key=lambda k: self._itens[k][0])
            del self._itens[mais_antiga]
        self._itens[chave] = (time.monotonic(), valor)
