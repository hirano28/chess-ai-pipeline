"""Casa cada consulta ao vivo com a partida real e registra o desfecho (D-68).

A consulta ao vivo (D-67) registra a dúvida no momento em que ela acontece. Este
script fecha o ciclo: quando a coleta traz a partida, procura nela a posição
consultada e grava o que o jogador jogou depois de pedir ajuda — se era uma das
ideias candidatas, se era o lance do motor e quanto custou.

Roda no pipeline diário, depois da coleta, do Stockfish, do Agente 1 e da
população da fila: precisa da partida gravada e, para ligar a dúvida ao treino,
dos lances críticos e dos cards já existentes.

Como acha a partida:
- com `partida_externa_id` (consulta feita com a partida sincronizada, D-69),
  direto por `partidas.external_id`;
- sem ele (espelhamento manual), pelas partidas do mesmo dono, mesma cor e mesma
  plataforma cujo horário cabe na janela da consulta — e, entre elas, a que de
  fato passou pela posição. A posição é o critério; a janela só evita varrer o
  acervo inteiro.
"""

from __future__ import annotations

import io
import logging
import sys
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import chess
import chess.pgn
from stockfish import Stockfish
from supabase import Client, create_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.refazer_trecho import win_percent_na_posicao  # noqa: E402
from backend.analise_engine.analisar_partidas import (  # noqa: E402
    load_settings as load_analysis_settings,
)
from backend.common.progress import configurar_encoding_utf8, log_and_print  # noqa: E402

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "casar_consultas_ao_vivo.log"

# A partida começa antes da consulta e termina depois dela; `data_partida` é o
# início no Lichess e pode ser o fim no Chess.com. A janela é larga de propósito:
# quem decide é a posição, não o relógio.
JANELA_ANTES = timedelta(hours=24)
JANELA_DEPOIS = timedelta(hours=6)
# A coleta diária traz a partida na mesma noite. Três dias sem achar significa
# que ela não virá (outro site, tabuleiro físico, variante não coletada).
DESISTIR_APOS = timedelta(days=3)


@dataclass(frozen=True)
class PosicaoNaPartida:
    """Onde a posição consultada aparece na partida, e o que veio a seguir."""

    board: chess.Board
    lance_seguinte: chess.Move | None


def configure_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("casar_consultas_ao_vivo")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def chave_posicao(board: chess.Board) -> str:
    """Identidade da posição para comparar: peças, vez e roques.

    Ignora en passant e os contadores de lance: a mesma posição chega por ordens
    de lances diferentes, e os contadores de uma partida que partiu de FEN não
    batem com os de outra.
    """

    return f"{board.board_fen()} {'w' if board.turn == chess.WHITE else 'b'} {board.castling_xfen()}"


def localizar_posicao(
    pgn: str, fen_consulta: str, cor_jogador: str, numero_lance: int | None = None
) -> PosicaoNaPartida | None:
    """Procura na partida a posição consultada, com o jogador na vez.

    Uma posição pode se repetir (transposição, repetição); quando isso acontece,
    vale a ocorrência com o mesmo número de lance da consulta, e na falta dela a
    primeira.
    """

    try:
        partida = chess.pgn.read_game(io.StringIO(pgn))
        alvo = chave_posicao(chess.Board(fen_consulta))
    except (ValueError, TypeError):
        return None
    if partida is None:
        return None

    vez_do_jogador = chess.WHITE if cor_jogador == "BRANCAS" else chess.BLACK
    board = partida.board()
    lances = list(partida.mainline_moves())
    ocorrencias: list[PosicaoNaPartida] = []
    for indice in range(len(lances) + 1):
        if board.turn == vez_do_jogador and chave_posicao(board) == alvo:
            seguinte = lances[indice] if indice < len(lances) else None
            ocorrencias.append(PosicaoNaPartida(board.copy(), seguinte))
        if indice < len(lances):
            board.push(lances[indice])

    if not ocorrencias:
        return None
    for ocorrencia in ocorrencias:
        if numero_lance is not None and ocorrencia.board.fullmove_number == numero_lance:
            return ocorrencia
    return ocorrencias[0]


def buscar_consultas_pendentes(client: Client) -> list[dict[str, Any]]:
    resposta = (
        client.table("consultas_ao_vivo")
        .select(
            "id, user_id, plataforma, cor_jogador, fen, numero_lance, criado_em, "
            "partida_externa_id, resposta"
        )
        .eq("casamento_status", "pendente")
        .order("criado_em")
        .execute()
    )
    return resposta.data or []


def _instante(valor: Any) -> datetime:
    texto = str(valor).replace("Z", "+00:00")
    instante = datetime.fromisoformat(texto)
    return instante if instante.tzinfo else instante.replace(tzinfo=timezone.utc)


def buscar_partidas_candidatas(client: Client, consulta: dict[str, Any]) -> list[dict[str, Any]]:
    """Partidas que podem conter a posição consultada."""

    base = (
        client.table("partidas")
        .select("id, pgn, external_id, data_partida")
        .eq("user_id", consulta["user_id"])
        .eq("cor_jogada", consulta["cor_jogador"])
    )
    externa = consulta.get("partida_externa_id")
    if externa:
        return base.eq("external_id", externa).execute().data or []

    criada = _instante(consulta["criado_em"])
    consulta_janela = (
        base.gte("data_partida", (criada - JANELA_ANTES).isoformat())
        .lte("data_partida", (criada + JANELA_DEPOIS).isoformat())
    )
    if consulta.get("plataforma") in ("LICHESS", "CHESSCOM"):
        consulta_janela = consulta_janela.eq("plataforma", consulta["plataforma"])
    return consulta_janela.execute().data or []


def buscar_lance_critico(
    client: Client, partida_id: str, numero_lance: int
) -> dict[str, Any] | None:
    """O lance crítico que corresponde à decisão consultada, se o motor marcou um.

    PICO exatamente naquele lance vem primeiro; na falta, uma EROSAO cuja janela
    cobre o lance. É isso que liga a dúvida ao treino que já existe.
    """

    resposta = (
        client.table("lances_criticos")
        .select("id, tipo_evento, numero_lance, numero_lance_fim")
        .eq("partida_id", partida_id)
        .execute()
    )
    linhas = resposta.data or []
    for linha in linhas:
        if (linha.get("tipo_evento") or "PICO") == "PICO" and linha.get("numero_lance") == numero_lance:
            return linha
    for linha in linhas:
        inicio = linha.get("numero_lance")
        fim = linha.get("numero_lance_fim")
        if linha.get("tipo_evento") == "EROSAO" and isinstance(inicio, int) and isinstance(fim, int):
            if inicio <= numero_lance <= fim:
                return linha
    return None


def adiantar_card(client: Client, user_id: str, lance_id: str, hoje: date) -> bool:
    """Traz para hoje o card de treino da posição em que o jogador teve dúvida E errou.

    É o card mais valioso que a fila tem: a dúvida foi declarada, e o erro
    aconteceu mesmo assim. Só adianta card nunca respondido — um que o SM-2 já
    agendou pelo desempenho do jogador não é atropelado.
    """

    resposta = (
        client.table("fila_treino_espacado")
        .select("id, proxima_revisao_data, total_revisoes")
        .eq("user_id", user_id)
        .eq("lance_id", lance_id)
        .execute()
    )
    linhas = resposta.data or []
    if not linhas or (linhas[0].get("total_revisoes") or 0) > 0:
        return False
    agendado = str(linhas[0].get("proxima_revisao_data") or "")
    if agendado and agendado <= hoje.isoformat():
        return False
    client.table("fila_treino_espacado").update(
        {"proxima_revisao_data": hoje.isoformat()}
    ).eq("id", linhas[0]["id"]).execute()
    return True


def desfecho(
    engine: Any, posicao: PosicaoNaPartida, cor_jogador: str, resposta: dict[str, Any]
) -> dict[str, Any]:
    """O que o jogador fez com a posição, medido pelo mesmo motor das consultas."""

    if posicao.lance_seguinte is None:
        # A partida acabou exatamente ali (abandono, tempo, acordo).
        return {
            "lance_jogado": None,
            "queda_win_percent_jogado": None,
            "lance_jogado_era_candidato": None,
            "lance_jogado_era_o_melhor": None,
        }

    board = posicao.board.copy()
    san = board.san(posicao.lance_seguinte)
    antes = win_percent_na_posicao(engine, board, cor_jogador)
    board.push(posicao.lance_seguinte)
    depois = win_percent_na_posicao(engine, board, cor_jogador)

    # D-70: o que o motor disse fica só no banco; a consulta não mostra lances.
    motor = (resposta or {}).get("motor") or {}
    candidatos = set(motor.get("candidatos") or [])
    melhor = motor.get("melhor_lance")
    return {
        "lance_jogado": san,
        "queda_win_percent_jogado": round(antes - depois, 2),
        "lance_jogado_era_candidato": san in candidatos,
        "lance_jogado_era_o_melhor": san == melhor,
    }


def processar_consulta(
    client: Client, engine: Any, consulta: dict[str, Any], agora: datetime, logger: logging.Logger
) -> str:
    """Casa uma consulta. Devolve o novo status ('casada', 'sem_partida' ou 'pendente')."""

    for partida in buscar_partidas_candidatas(client, consulta):
        posicao = localizar_posicao(
            partida.get("pgn") or "",
            consulta["fen"],
            consulta["cor_jogador"],
            consulta.get("numero_lance"),
        )
        if posicao is None:
            continue

        campos = desfecho(engine, posicao, consulta["cor_jogador"], consulta.get("resposta") or {})
        lance_critico = buscar_lance_critico(client, partida["id"], posicao.board.fullmove_number)
        campos.update(
            {
                "casamento_status": "casada",
                "partida_id": partida["id"],
                "lance_critico_id": lance_critico["id"] if lance_critico else None,
                "casada_em": agora.isoformat(),
            }
        )
        client.table("consultas_ao_vivo").update(campos).eq("id", consulta["id"]).execute()

        adiantado = False
        if lance_critico:
            adiantado = adiantar_card(client, consulta["user_id"], lance_critico["id"], agora.date())
        logger.info(
            "Consulta %s casada com a partida %s (jogou %s, queda %s%%, card adiantado: %s).",
            consulta["id"], partida["id"], campos["lance_jogado"],
            campos["queda_win_percent_jogado"], adiantado,
        )
        return "casada"

    if agora - _instante(consulta["criado_em"]) > DESISTIR_APOS:
        client.table("consultas_ao_vivo").update({"casamento_status": "sem_partida"}).eq(
            "id", consulta["id"]
        ).execute()
        return "sem_partida"
    return "pendente"


def main() -> None:
    logger = configure_logging()
    contagem = {"casada": 0, "sem_partida": 0, "pendente": 0, "falha": 0}
    engine = None
    try:
        settings = load_analysis_settings()
        client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        consultas = buscar_consultas_pendentes(client)
        log_and_print(logger, f"{len(consultas)} consulta(s) ao vivo pendente(s) de casamento.")
        if consultas:
            engine = Stockfish(
                path=settings.stockfish_path,
                depth=settings.stockfish_depth,
                turn_perspective=False,
            )
        agora = datetime.now(timezone.utc)
        for consulta in consultas:
            try:
                contagem[processar_consulta(client, engine, consulta, agora, logger)] += 1
            except Exception:
                contagem["falha"] += 1
                logger.error("Falha ao casar a consulta %s:\n%s", consulta.get("id"), traceback.format_exc())
    except Exception:
        contagem["falha"] += 1
        logger.error("Falha geral ao casar consultas ao vivo:\n%s", traceback.format_exc())

    print(
        f"Casadas: {contagem['casada']} | sem partida: {contagem['sem_partida']} | "
        f"ainda pendentes: {contagem['pendente']}"
    )
    print(f"Falhas: {contagem['falha']}")
    if contagem["falha"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
