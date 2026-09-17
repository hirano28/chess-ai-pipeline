"""Importa exercícios "ache o melhor lance" NÃO táticos do banco público de
broadcasts do Lichess (partidas OTB reais de torneio) para o catálogo
`exercicios_posicionais` (D-55).

Existe para fechar o buraco que o D-49 deixou documentado e o P-15 registrou:
puzzle é tática por construção, então ESTRATEGIA ficou com zero exercícios e
GESTAO_DE_TEMPO também (posição de puzzle é estática, não tem relógio). O
broadcast resolve os dois porque não é puzzle: é partida inteira, com
`[%eval]` em todo lance, `[%clk]` em todo lance, e a anotação do próprio
Lichess dizendo onde alguém errou e qual era o melhor lance.

Import ocasional/manual - não roda no pipeline diário. Uso:
  python backend/rag/importar_exercicios_posicionais.py

Como um exercício é escolhido:

1. O Lichess já marcou o lance como `Mistake` ou `Blunder` (`Inaccuracy` é
   ruído demais para virar exercício).
2. A posição ainda estava em aberto antes do erro (|avaliação| <= 300cp): não
   adianta pedir "ache o melhor lance" em partida já ganha ou já perdida, que
   é outra habilidade.
3. O erro custou caro de verdade (queda >= 150cp), então existe mesmo uma
   decisão a tomar ali.
4. **O melhor lance é quieto** - não é captura, não é xeque, não é promoção.
   É este filtro que faz o exercício ser posicional/defensivo em vez de uma
   tática disfarçada, e portanto material legítimo para ESTRATEGIA.

Assim como no D-49, NÃO guardamos a resposta certa, mesmo tendo ela de graça
na anotação. Quem avalia continua sendo o Stockfish em
`POST /treino/{id}/responder`. Isso resolve sozinho o problema clássico de
posição posicional ter vários lances defensáveis: não comparamos com um
gabarito, medimos a queda de avaliação — qualquer lance que não perca nada
passa como BOM.

Licença: broadcasts do Lichess são **CC BY-SA 4.0**, não CC0 como os puzzles
do D-49. Exige atribuição, por isso a procedência é gravada e exibida.
"""

from __future__ import annotations

import io
import logging
import os
import random
import re
import sys
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import chess
import chess.pgn
import requests
import zstandard
from supabase import Client, create_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import configurar_encoding_utf8, log_and_print  # noqa: E402
from backend.common.settings import carregar_variaveis_obrigatorias  # noqa: E402

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "importar_exercicios_posicionais.log"
BROADCAST_URL_MOLDE = "https://database.lichess.org/broadcast/lichess_db_broadcast_{mes}.pgn.zst"
BATCH_SIZE = 500

# Anotação que o próprio Lichess grava no PGN, ex.:
#   "[%eval 2.24] Blunder. bxc4 was best. [%clk 0:34:44]"
ANOTACAO_ERRO = re.compile(r"\b(Inaccuracy|Mistake|Blunder)\.\s+(\S+)\s+was best\.")
SEVERIDADES_ACEITAS = ("Mistake", "Blunder")

# Filtros de seleção - configuráveis por env var, mesmo padrão do D-49.
POSICIONAL_EVAL_MAX_CP = int(os.getenv("POSICIONAL_EVAL_MAX_CP", "300"))
POSICIONAL_QUEDA_MIN_CP = int(os.getenv("POSICIONAL_QUEDA_MIN_CP", "150"))
POSICIONAL_POR_CATEGORIA = int(os.getenv("POSICIONAL_POR_CATEGORIA", "300"))
# Abaixo disto o erro conta como falha de gestão de tempo, não de entendimento
# posicional: 2 minutos num clássico é apuro de relógio, não descuido.
POSICIONAL_SEGUNDOS_PRESSAO = int(os.getenv("POSICIONAL_SEGUNDOS_PRESSAO", "120"))
# Peças que não são rei nem peão. Com 4 ou menos a posição é final na prática.
POSICIONAL_PECAS_FINAL = int(os.getenv("POSICIONAL_PECAS_FINAL", "4"))

# Títulos da FIDE que o PGN do broadcast traz em WhiteTitle/BlackTitle.
TITULOS_FIDE = frozenset({"GM", "IM", "FM", "CM", "NM", "WGM", "WIM", "WFM", "WCM"})
# Exigir pelo menos um titulado na partida. Sem isto a primeira execução trouxe
# 1200 exercícios tirados de um único dia de opens juvenis (sub-14, "Open C") —
# tecnicamente OTB, mas longe de "partida real conhecida", que é o ponto de
# aprender com quem joga bem. Desligável para quem quiser volume acima de nome.
POSICIONAL_EXIGIR_TITULO = os.getenv("POSICIONAL_EXIGIR_TITULO", "1") not in ("0", "false", "")

# Só as categorias que o filtro de "lance quieto" consegue produzir. TATICA e
# CALCULO ficam de fora de propósito: são exatamente o que este filtro exclui,
# e já têm 300 exercícios cada vindos dos puzzles (D-49).
CATEGORIAS_APLICAVEIS: frozenset[str] = frozenset(
    {"ESTRATEGIA", "FINAIS", "ESTRUTURA_DE_PEOES", "GESTAO_DE_TEMPO"}
)


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do script."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("importar_exercicios_posicionais")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)

    # Transmissão ao vivo de torneio erra: um operador digita um lance ilegal e
    # a partida chega truncada. python-chess loga cada ocorrência em ERROR, o
    # que enche o console de centenas de linhas por mês importado. Os jogos
    # afetados continuam sendo lidos até o ponto do erro - só o barulho sai.
    logging.getLogger("chess.pgn").setLevel(logging.CRITICAL)
    return logger


def load_settings() -> dict[str, str]:
    """Carrega e valida as configurações do ambiente."""

    return carregar_variaveis_obrigatorias(
        PROJECT_ROOT, "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"
    )


def meses_padrao(hoje: date | None = None) -> list[str]:
    """Último mês completo, no formato 'YYYY-MM'.

    Calculado em vez de fixado numa constante: uma data escrita à mão no
    default envelhece em silêncio e passa a baixar sempre o mesmo mês antigo.
    """

    referencia = hoje or date.today()
    ano, mes = (referencia.year, referencia.month - 1)
    if mes == 0:
        ano, mes = ano - 1, 12
    return [f"{ano:04d}-{mes:02d}"]


# ---------------------------------------------------------------------------
# Funções puras - testáveis sem rede nem banco
# ---------------------------------------------------------------------------


def interpretar_anotacao(comentario: str | None) -> tuple[str, str] | None:
    """Extrai (severidade, melhor lance em SAN) da anotação do Lichess.

    Devolve None quando o lance não foi anotado como erro ou quando a
    severidade é `Inaccuracy` - imprecisão de GM raramente tem uma resposta
    única o bastante para virar exercício.
    """

    achado = ANOTACAO_ERRO.search(comentario or "")
    if not achado:
        return None
    severidade, melhor_san = achado.group(1), achado.group(2)
    if severidade not in SEVERIDADES_ACEITAS:
        return None
    return severidade, melhor_san


def centipeoes(avaliacao: Any, cor: chess.Color) -> int | None:
    """Avaliação em centipeões do ponto de vista de `cor`.

    `avaliacao` é o PovScore que python-chess extrai do `[%eval]`. Mate vira
    um número grande (mate_score) para a comparação numérica não explodir.
    """

    if avaliacao is None:
        return None
    return avaliacao.pov(cor).score(mate_score=10000)


def decisao_ainda_em_aberto(
    avaliacao_antes_cp: int, eval_max_cp: int = POSICIONAL_EVAL_MAX_CP
) -> bool:
    """True se a partida ainda estava indefinida antes do erro.

    Pedir "ache o melhor lance" numa posição já ganha ou já perdida treina
    conversão/resistência, que é outra habilidade — e o usuário não teria como
    saber qual das duas estamos cobrando.
    """

    return abs(avaliacao_antes_cp) <= eval_max_cp


def erro_custou_caro(
    avaliacao_antes_cp: int,
    avaliacao_depois_cp: int,
    queda_min_cp: int = POSICIONAL_QUEDA_MIN_CP,
) -> bool:
    """True se a queda de avaliação justifica virar exercício."""

    return (avaliacao_antes_cp - avaliacao_depois_cp) >= queda_min_cp


def lance_e_quieto(board: chess.Board, lance: chess.Move) -> bool:
    """True quando o melhor lance não é captura, xeque nem promoção.

    É o filtro central do D-55: sem ele, o que sobra são táticas — que já têm
    300 exercícios por categoria vindos dos puzzles (D-49). Com ele, o que
    sobra é decisão posicional ou defensiva, que é exatamente o material que
    faltava para ESTRATEGIA.
    """

    return (
        not board.is_capture(lance)
        and not board.gives_check(lance)
        and lance.promotion is None
    )


def contar_pecas_maiores(board: chess.Board) -> int:
    """Peças que não são rei nem peão, somando os dois lados."""

    return sum(
        len(board.pieces(tipo, cor))
        for tipo in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
        for cor in (chess.WHITE, chess.BLACK)
    )


def classificar_posicao(
    board: chess.Board,
    melhor_lance: chess.Move,
    segundos_restantes: int | None,
    segundos_pressao: int = POSICIONAL_SEGUNDOS_PRESSAO,
    pecas_final: int = POSICIONAL_PECAS_FINAL,
) -> str | None:
    """Categoria do hexágono para este exercício, ou None se ele deve ser
    descartado.

    A ordem importa. O relógio vem primeiro: errar com dois minutos no relógio
    é falha de gestão de tempo, qualquer que seja a natureza do lance — e é
    por isso que esta é a única categoria aqui que aceita lance não-quieto. Só
    depois vem a natureza da posição.
    """

    if segundos_restantes is not None and segundos_restantes <= segundos_pressao:
        return "GESTAO_DE_TEMPO"
    if not lance_e_quieto(board, melhor_lance):
        return None
    if contar_pecas_maiores(board) <= pecas_final:
        return "FINAIS"
    if board.piece_type_at(melhor_lance.from_square) == chess.PAWN:
        return "ESTRUTURA_DE_PEOES"
    return "ESTRATEGIA"


def partida_tem_titulado(headers: dict[str, str]) -> bool:
    """True se pelo menos um dos jogadores tem título da FIDE.

    Diferença prática grande: "ache o melhor lance onde um GM errou" é um
    exercício; "onde alguém errou num sub-14" é ruído com posição bonita.
    """

    return any(
        (headers.get(chave) or "").strip().upper() in TITULOS_FIDE
        for chave in ("WhiteTitle", "BlackTitle")
    )


def nome_do_jogador(nome: str | None, titulo: str | None) -> str | None:
    """'GM Aroshidze Levan' quando o PGN traz o título, só o nome quando não."""

    nome_limpo = (nome or "").strip()
    if not nome_limpo or nome_limpo == "?":
        return None
    titulo_limpo = (titulo or "").strip()
    return f"{titulo_limpo} {nome_limpo}" if titulo_limpo else nome_limpo


def data_da_partida(headers: dict[str, str]) -> date | None:
    """`UTCDate` quando existe; `Date` como reserva. Os broadcasts trazem
    '????.??.??' com frequência, e isso não é erro - só falta de dado."""

    for chave in ("UTCDate", "Date"):
        bruto = (headers.get(chave) or "").strip()
        if not bruto or "?" in bruto:
            continue
        try:
            ano, mes, dia = (int(parte) for parte in bruto.split("."))
            return date(ano, mes, dia)
        except (ValueError, TypeError):
            continue
    return None


def registro_do_erro(
    board: chess.Board,
    comentario_do_lance: str | None,
    avaliacao_antes: Any,
    avaliacao_depois: Any,
    segundos_restantes: int | None,
    headers: dict[str, str],
    **limites: int,
) -> dict[str, Any] | None:
    """Converte um lance anotado como erro num registro de
    `exercicios_posicionais`, ou None se ele não passa nos filtros.

    `board` é a posição ANTES do lance ruim - é ela que vira o exercício.
    """

    anotacao = interpretar_anotacao(comentario_do_lance)
    if not anotacao:
        return None
    severidade, melhor_san = anotacao

    cor = board.turn
    antes = centipeoes(avaliacao_antes, cor)
    depois = centipeoes(avaliacao_depois, cor)
    if antes is None or depois is None:
        return None
    if not decisao_ainda_em_aberto(
        antes, limites.get("eval_max_cp", POSICIONAL_EVAL_MAX_CP)
    ):
        return None
    if not erro_custou_caro(
        antes, depois, limites.get("queda_min_cp", POSICIONAL_QUEDA_MIN_CP)
    ):
        return None

    try:
        melhor_lance = board.parse_san(melhor_san)
    except (ValueError, chess.IllegalMoveError, chess.AmbiguousMoveError):
        # Transmissão ao vivo erra; um SAN que não bate com a posição é dado
        # ruim, não exceção a tratar.
        return None

    categoria = classificar_posicao(
        board,
        melhor_lance,
        segundos_restantes,
        limites.get("segundos_pressao", POSICIONAL_SEGUNDOS_PRESSAO),
        limites.get("pecas_final", POSICIONAL_PECAS_FINAL),
    )
    if categoria is None:
        return None

    jogo_url = (headers.get("GameURL") or "").strip()
    if not jogo_url:
        return None

    data_partida = data_da_partida(headers)
    return {
        "jogo_url": jogo_url,
        "ply": board.ply(),
        "numero_lance": board.fullmove_number,
        "fen": board.fen(),
        "categoria_hexagono": categoria,
        "severidade": severidade,
        "queda_centipeoes": antes - depois,
        # Só faz sentido guardar o relógio onde ele É o exercício.
        "segundos_restantes": (
            int(segundos_restantes)
            if segundos_restantes is not None and categoria == "GESTAO_DE_TEMPO"
            else None
        ),
        "brancas": nome_do_jogador(headers.get("White"), headers.get("WhiteTitle")),
        "pretas": nome_do_jogador(headers.get("Black"), headers.get("BlackTitle")),
        "evento": (headers.get("BroadcastName") or headers.get("Event") or "").strip() or None,
        "data_partida": data_partida.isoformat() if data_partida else None,
    }


def extrair_exercicios_do_jogo(
    jogo: chess.pgn.Game, exigir_titulo: bool = POSICIONAL_EXIGIR_TITULO, **limites: int
) -> list[dict[str, Any]]:
    """Percorre a linha principal e devolve os exercícios aprovados."""

    headers = dict(jogo.headers)
    if exigir_titulo and not partida_tem_titulado(headers):
        return []
    exercicios: list[dict[str, Any]] = []
    no = jogo
    while no.variations:
        proximo = no.variations[0]
        registro = registro_do_erro(
            no.board(),
            proximo.comment,
            no.eval(),
            proximo.eval(),
            proximo.clock(),
            headers,
            **limites,
        )
        if registro is not None:
            exercicios.append(registro)
        no = proximo
    return exercicios


class ReservatorioPorCategoria:
    """Amostragem por reservatório: N exercícios por categoria, sorteados
    uniformemente do mês INTEIRO, sem guardar o mês inteiro em memória.

    A primeira versão do D-55 simplesmente aceitava os primeiros N e parava de
    ler. O resultado foi 1200 exercícios tirados quase todos do mesmo dia, de
    meia dúzia de torneios — aumentar o teto não resolveria, porque o viés
    estava em *onde* no arquivo a leitura parava. Com reservatório, ler o mês
    todo custa alguns minutos e devolve material espalhado por todos os
    torneios daquele mês.

    O algoritmo é o clássico (Vitter R): enquanto cabe, guarda; depois disso,
    o k-ésimo candidato entra com probabilidade N/k, sorteando quem sai.
    """

    def __init__(self, tamanho: int) -> None:
        self.tamanho = tamanho
        self.itens: dict[str, list[dict[str, Any]]] = {}
        self.vistos: dict[str, int] = {}

    def oferecer(self, categoria: str, registro: dict[str, Any]) -> None:
        reservatorio = self.itens.setdefault(categoria, [])
        self.vistos[categoria] = vistos = self.vistos.get(categoria, 0) + 1

        if self.tamanho <= 0:
            return
        if len(reservatorio) < self.tamanho:
            reservatorio.append(registro)
            return
        sorteado = random.randrange(vistos)
        if sorteado < self.tamanho:
            reservatorio[sorteado] = registro

    def coletar(self) -> list[dict[str, Any]]:
        return [
            registro for reservatorio in self.itens.values() for registro in reservatorio
        ]

    def contagem(self) -> dict[str, int]:
        return {categoria: len(itens) for categoria, itens in self.itens.items()}


# ---------------------------------------------------------------------------
# Streaming do dump público (sem salvar o arquivo bruto em disco)
# ---------------------------------------------------------------------------


def iterar_jogos_broadcast(
    meses: Iterable[str], logger: logging.Logger
) -> Iterator[chess.pgn.Game]:
    """Baixa e descomprime os PGNs de broadcast em streaming, jogo a jogo."""

    for mes in meses:
        url = BROADCAST_URL_MOLDE.format(mes=mes)
        log_and_print(logger, f"Conectando em {url}...")
        with requests.get(url, stream=True, timeout=120) as response:
            response.raise_for_status()
            descompressor = zstandard.ZstdDecompressor()
            with descompressor.stream_reader(response.raw) as leitor:
                texto = io.TextIOWrapper(leitor, encoding="utf-8", errors="replace")
                while True:
                    jogo = chess.pgn.read_game(texto)
                    if jogo is None:
                        break
                    yield jogo


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------


def importar(
    client: Client,
    logger: logging.Logger,
    meses: Iterable[str] | None = None,
    teto_por_categoria: int = POSICIONAL_POR_CATEGORIA,
    exigir_titulo: bool = POSICIONAL_EXIGIR_TITULO,
    **limites: int,
) -> dict[str, int]:
    """Lê os broadcasts inteiros, amostra por reservatório e faz upsert em lote.

    Lê o mês todo de propósito, sem parar ao bater o teto: parar cedo foi o que
    fez a primeira importação sair enviesada para os primeiros dias do mês.
    """

    reservatorio = ReservatorioPorCategoria(teto_por_categoria)
    vistos: set[tuple[str, int]] = set()
    total_jogos = 0

    for jogo in iterar_jogos_broadcast(meses or meses_padrao(), logger):
        total_jogos += 1
        for registro in extrair_exercicios_do_jogo(jogo, exigir_titulo, **limites):
            chave = (registro["jogo_url"], registro["ply"])
            if chave in vistos:
                # O mesmo jogo pode aparecer duas vezes no dump (rodadas
                # retransmitidas); o upsert aguenta, mas mandar a mesma chave
                # duas vezes no MESMO lote é que o Postgres recusa.
                continue
            vistos.add(chave)
            reservatorio.oferecer(registro["categoria_hexagono"], registro)

        if total_jogos % 5000 == 0:
            log_and_print(
                logger,
                f"{total_jogos} partidas lidas, reservatório em "
                f"{reservatorio.contagem()}.",
            )

    registros = reservatorio.coletar()
    for inicio in range(0, len(registros), BATCH_SIZE):
        lote = registros[inicio : inicio + BATCH_SIZE]
        client.table("exercicios_posicionais").upsert(
            lote, on_conflict="jogo_url,ply"
        ).execute()

    return {
        "partidas_lidas": total_jogos,
        "exercicios_importados": len(registros),
        **reservatorio.contagem(),
    }


def main() -> None:
    """Ponto de entrada: importa o catálogo de exercícios posicionais."""

    logger = configure_logging()
    settings = load_settings()
    client = create_client(settings["SUPABASE_URL"], settings["SUPABASE_SERVICE_ROLE_KEY"])

    meses = [
        mes.strip() for mes in (os.getenv("POSICIONAL_MESES") or "").split(",") if mes.strip()
    ] or meses_padrao()

    resumo = importar(client, logger, meses)

    print(f"Meses lidos: {', '.join(meses)}")
    print(f"Partidas lidas: {resumo['partidas_lidas']}")
    print(f"Exercícios importados: {resumo['exercicios_importados']}")
    for categoria in sorted(CATEGORIAS_APLICAVEIS):
        print(f"  {categoria}: {resumo.get(categoria, 0)}")


if __name__ == "__main__":
    main()
