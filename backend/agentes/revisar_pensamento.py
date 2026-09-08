"""Revisa a qualidade do raciocínio anotado versus a realidade do motor.

Tabela SEPARADA de `diagnosticos`: nunca alimenta as estatísticas do hexágono
nem altera `tags_falha` — apenas grava revisões em `revisoes_pensamento`.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import chess
import chess.pgn
import google.genai as genai
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
from stockfish import Stockfish
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.analise_engine.analisar_partidas import (  # noqa: E402
    STOCKFISH_SEARCHTIME_MS,
    evaluate_position,
)
from backend.common.chess_math import centipawns_para_win_percent  # noqa: E402
from backend.common.progress import format_progress, log_and_print  # noqa: E402

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "revisar_pensamento.log"
MODEL_NAME = "gemini-flash-latest"
PAGE_SIZE = 1000
SERVER_ERROR_RETRY_LIMIT = 3
SERVER_ERROR_BACKOFF_SECONDS = (5, 15, 45)


class RevisaoRaciocinio(BaseModel):
    """Schema estruturado da revisão de raciocínio gerada pelo agente."""

    qualidade_raciocinio: Literal["SOLIDO", "FALHO", "INDETERMINADO"]
    feedback_texto: str
    analise_mestre: str


@dataclass(frozen=True)
class Settings:
    """Configurações do Supabase, Stockfish, Gemini e limiares de qualidade."""

    supabase_url: str
    supabase_service_role_key: str
    stockfish_path: str
    stockfish_depth: int
    gemini_api_key: str
    limiar_lance_bom: float
    limiar_lance_ruim: float


@dataclass(frozen=True)
class AvaliacaoLance:
    """Resultado da avaliação do motor para o lance realmente jogado."""

    lance_jogado: str
    melhor_lance: str | None
    queda_win_percent: float
    linha_principal: list[str] = field(default_factory=list)


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do revisor de pensamento."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("revisar_pensamento")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


def load_settings() -> Settings:
    """Carrega e valida as configurações do ambiente."""

    load_dotenv(PROJECT_ROOT / ".env")
    required = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        "STOCKFISH_PATH": os.getenv("STOCKFISH_PATH"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )

    raw_depth = os.getenv("STOCKFISH_DEPTH", "16")
    try:
        depth = int(raw_depth)
    except ValueError as error:
        raise ValueError("STOCKFISH_DEPTH deve ser um inteiro") from error
    if depth < 1:
        raise ValueError("STOCKFISH_DEPTH deve ser maior que zero")

    limiar_lance_bom = _load_float("REVISAO_LIMIAR_LANCE_BOM", 5.0)
    limiar_lance_ruim = _load_float("REVISAO_LIMIAR_LANCE_RUIM", 15.0)

    return Settings(
        supabase_url=required["SUPABASE_URL"],  # type: ignore[arg-type]
        supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],  # type: ignore[arg-type]
        stockfish_path=required["STOCKFISH_PATH"],  # type: ignore[arg-type]
        stockfish_depth=depth,
        gemini_api_key=required["GEMINI_API_KEY"],  # type: ignore[arg-type]
        limiar_lance_bom=limiar_lance_bom,
        limiar_lance_ruim=limiar_lance_ruim,
    )


def _load_float(name: str, default: float) -> float:
    """Lê um limiar numérico do ambiente com fallback seguro."""

    raw = os.getenv(name, str(default))
    try:
        return float(raw)
    except ValueError as error:
        raise ValueError(f"{name} deve ser um número") from error


def fetch_anotacoes(client: Client, logger: logging.Logger) -> list[dict[str, Any]]:
    """Busca as anotações de pensamento com o PGN e a cor da partida."""

    anotacoes: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            client.table("anotacoes_pensamento")
            .select("partida_id, numero_lance, texto_pensamento, partidas(pgn, cor_jogada)")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        anotacoes.extend(page)
        logger.info(
            "Página de anotações carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            return anotacoes
        offset += PAGE_SIZE


def fetch_revisadas(client: Client, logger: logging.Logger) -> set[tuple[Any, int]]:
    """Busca o conjunto (partida_id, numero_lance) já revisado, em páginas."""

    revisadas: set[tuple[Any, int]] = set()
    offset = 0
    while True:
        response = (
            client.table("revisoes_pensamento")
            .select("partida_id, numero_lance")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        revisadas.update((row["partida_id"], row["numero_lance"]) for row in page)
        logger.info(
            "Página de revisões carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            return revisadas
        offset += PAGE_SIZE


def selecionar_elegiveis(
    anotacoes: list[dict[str, Any]], revisadas: set[tuple[Any, int]]
) -> list[dict[str, Any]]:
    """Filtra anotações que ainda não têm revisão correspondente."""

    return [
        anotacao
        for anotacao in anotacoes
        if (anotacao["partida_id"], anotacao["numero_lance"]) not in revisadas
    ]


def _get_partida(anotacao: dict[str, Any]) -> dict[str, Any]:
    """Extrai a partida embutida na anotação (objeto ou lista)."""

    partida = anotacao.get("partidas") or anotacao.get("partida")
    if isinstance(partida, list):
        partida = partida[0] if partida else None
    if not isinstance(partida, dict):
        raise ValueError("Anotação sem partida relacionada")
    return partida


def obter_melhor_lance(
    engine: Stockfish, board: chess.Board, searchtime_ms: int = STOCKFISH_SEARCHTIME_MS
) -> str | None:
    """Consulta o melhor lance do motor na posição, em SAN."""

    engine.set_fen_position(board.fen())
    try:
        uci = engine.get_best_move_time(searchtime_ms)
    except TypeError:
        uci = engine.get_best_move()
    if not uci:
        return None
    try:
        return board.san(chess.Move.from_uci(uci))
    except (ValueError, AssertionError):
        return uci


def obter_linha_principal(
    engine: Stockfish, board: chess.Board, num_lances: int = 6
) -> list[str]:
    """Consulta a linha principal (PV) completa do motor na posição, em SAN.

    Usa get_top_moves(1, verbose=True), que expõe a PV inteira em `PVMoves`
    (não só o primeiro lance).
    """

    engine.set_fen_position(board.fen())
    try:
        top_moves = engine.get_top_moves(1, verbose=True)
    except Exception:
        return []
    if not top_moves:
        return []

    pv_uci = (top_moves[0].get("PVMoves") or "").split()
    scratch = board.copy()
    linha_principal: list[str] = []
    for uci_move in pv_uci[:num_lances]:
        try:
            move = chess.Move.from_uci(uci_move)
            linha_principal.append(scratch.san(move))
            scratch.push(move)
        except (ValueError, AssertionError):
            break
    return linha_principal


def avaliar_lance(
    engine: Stockfish, pgn: str, numero_lance: int, cor_jogada: str
) -> AvaliacaoLance:
    """Avalia o lance realmente jogado pelo jogador naquele numero_lance."""

    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise ValueError("Não foi possível fazer parse do PGN da partida")

    board = game.board()
    for move in game.mainline_moves():
        playing_color = "BRANCAS" if board.turn == chess.WHITE else "PRETAS"
        if board.fullmove_number == numero_lance and playing_color == cor_jogada:
            lance_jogado = board.san(move)
            before_cp = evaluate_position(engine, board, cor_jogada)
            melhor_lance = obter_melhor_lance(engine, board)
            linha_principal = obter_linha_principal(engine, board)
            board.push(move)
            after_cp = evaluate_position(engine, board, cor_jogada)
            queda_win_percent = round(
                centipawns_para_win_percent(before_cp)
                - centipawns_para_win_percent(after_cp),
                2,
            )
            return AvaliacaoLance(
                lance_jogado, melhor_lance, queda_win_percent, linha_principal
            )
        board.push(move)

    raise ValueError(
        f"Lance {numero_lance} ({cor_jogada}) não encontrado no PGN da partida"
    )


def classificar_qualidade_lance(
    queda_win_percent: float, limiar_bom: float, limiar_ruim: float
) -> str:
    """Classifica o lance por queda de win_percent: BOM, SUBOTIMO ou RUIM."""

    if queda_win_percent < limiar_bom:
        return "BOM"
    if queda_win_percent < limiar_ruim:
        return "SUBOTIMO"
    return "RUIM"


def build_prompt(
    texto_pensamento: str,
    avaliacao: AvaliacaoLance,
    qualidade_lance: str,
) -> str:
    """Monta o prompt de revisão do raciocínio para o Gemini."""

    linha_principal_texto = (
        " ".join(avaliacao.linha_principal)
        if avaliacao.linha_principal
        else "(linha principal indisponível)"
    )

    return f"""Você é um treinador de xadrez revisando o RACIOCÍNIO de um jogador, não apenas o resultado.

Um lance crítico foi anotado pelo jogador com o que ele estava pensando. Sua tarefa
é avaliar a QUALIDADE DO RACIOCÍNIO, de forma independente de o lance ter dado certo
ou errado no tabuleiro.

Dados objetivos (do motor, não os revele como "certo/errado" de forma dura):
- lance_realmente_jogado: {avaliacao.lance_jogado}
- melhor_lance_segundo_o_motor: {avaliacao.melhor_lance}
- linha_principal_do_motor (continuação completa, não apenas o primeiro lance): {linha_principal_texto}
- queda_win_percent_real: {avaliacao.queda_win_percent}
- qualidade_objetiva_do_lance: {qualidade_lance}

Pensamento anotado pelo jogador:
\"\"\"{texto_pensamento}\"\"\"

Classifique qualidade_raciocinio em UM destes valores:
- "SOLIDO": o jogador considerou as opções relevantes e tomou uma decisão justificada,
  INDEPENDENTE do resultado ter sido bom ou ruim.
- "FALHO": o raciocínio tinha uma lacuna real (não considerou algo importante que
  estava disponível na posição).
- "INDETERMINADO": o texto é vago demais para avaliar o raciocínio.

Escreva também um feedback_texto curto (2 a 3 frases) sugerindo como refinar o
raciocínio. Ele deve ser SEMPRE construtivo, mesmo quando o lance foi objetivamente
bom (nesse caso, reforce o que foi bem pensado e aponte um próximo passo).

Escreva também um analise_mestre (2 a 4 frases) explicando como um jogador forte
abordaria essa posição, mencionando o PLANO por trás da linha_principal_do_motor
acima — não apenas "o melhor lance é X", mas o raciocínio estratégico/tático da
sequência. Baseie sua explicação EXCLUSIVAMENTE na linha fornecida pelo motor. Não
invente avaliação própria. Explique o plano por trás dela em linguagem natural,
como um treinador explicaria a um aluno.

Responda ESTRITAMENTE com um único JSON válido, sem texto antes ou depois e sem
markdown fences, compatível com este schema:
{{
  "qualidade_raciocinio": "SOLIDO|FALHO|INDETERMINADO",
  "feedback_texto": "string",
  "analise_mestre": "string"
}}
"""


def strip_json_fences(text: str) -> str:
    """Remove fences markdown caso o modelo as inclua apesar da instrução."""

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def is_server_error_503(error: Exception) -> bool:
    """Identifica erro 503 ou mensagem de alta demanda do SDK Gemini."""

    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    text = str(error).lower()
    return status_code == 503 or "503" in text or "high demand" in text


def call_gemini(
    client: Any, prompt: str, logger: logging.Logger
) -> str:
    """Chama o Gemini, repetindo erros 503 com backoff exponencial."""

    for attempt in range(SERVER_ERROR_RETRY_LIMIT):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME, contents=prompt
            )
            if not response.text:
                raise ValueError("Resposta do Gemini não contém texto")
            return response.text
        except Exception as error:
            if not is_server_error_503(error) or attempt == SERVER_ERROR_RETRY_LIMIT - 1:
                raise
            delay = SERVER_ERROR_BACKOFF_SECONDS[attempt]
            logger.warning(
                "Gemini retornou 503 na tentativa %d/%d; nova tentativa em %ds: %s",
                attempt + 1,
                SERVER_ERROR_RETRY_LIMIT,
                delay,
                error,
            )
            time.sleep(delay)
    raise RuntimeError("Chamada ao Gemini encerrada sem resultado")


def correction_prompt(original_prompt: str, error: ValidationError) -> str:
    """Solicita correção quando o primeiro JSON não valida no Pydantic."""

    return f"""{original_prompt}

A resposta anterior falhou na validação Pydantic com este erro específico:
{error}

Corrija todos os problemas e responda novamente apenas com o JSON válido,
sem markdown e sem explicações externas."""


def parse_revisao(text: str) -> RevisaoRaciocinio:
    """Limpa a resposta e valida o JSON contra RevisaoRaciocinio."""

    return RevisaoRaciocinio.model_validate_json(strip_json_fences(text))


# Padrão de notação algébrica SAN (inclui roque, captura, promoção e xeque/mate).
SAN_MOVE_PATTERN = re.compile(
    r"O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?"
)


def extrair_lances_san(texto: str) -> list[str]:
    """Extrai os lances em notação SAN mencionados em um texto livre."""

    return SAN_MOVE_PATTERN.findall(texto)


def lances_faltantes(
    analise_mestre: str, lances_esperados: list[str]
) -> list[str]:
    """Retorna os lances esperados que NÃO aparecem literalmente no texto."""

    citados = set(extrair_lances_san(analise_mestre))
    return [lance for lance in lances_esperados if lance not in citados]


def correction_prompt_analise_mestre(
    original_prompt: str,
    linha_principal: list[str],
    lances_faltantes_texto: list[str],
) -> str:
    """Solicita nova análise quando o texto não cita a linha principal real."""

    linha_texto = " ".join(linha_principal)
    faltantes = ", ".join(lances_faltantes_texto)
    return (
        f"{original_prompt}\n\n"
        "A resposta anterior de analise_mestre citou lances que NÃO correspondem "
        "à linha principal fornecida pelo motor. A linha principal correta e "
        f"literal é: {linha_texto}\n"
        f"Estes lances obrigatórios NÃO apareceram no seu texto: {faltantes}\n"
        "Reescreva analise_mestre citando EXATAMENTE os lances da linha principal "
        "acima, na mesma notação (copie-os literalmente), sem trocar peças nem "
        "inverter a ordem. Responda novamente apenas com o JSON válido, sem "
        "markdown e sem explicações externas."
    )


def fallback_analise_mestre(linha_principal: list[str]) -> str:
    """Gera analise_mestre sem LLM, formatando a linha principal literalmente."""

    linha_texto = " ".join(linha_principal)
    return (
        f"A linha principal sugerida pelo motor é: {linha_texto} — considere "
        "estudar essa sequência para entender o plano."
    )


def validar_analise_mestre(
    client: Any,
    prompt: str,
    revisao: RevisaoRaciocinio,
    linha_principal: list[str],
    logger: logging.Logger,
) -> RevisaoRaciocinio:
    """Garante que analise_mestre cite a linha principal real (retry + fallback).

    Verifica se ao menos os 2 primeiros lances da linha_principal aparecem
    literalmente no texto. Se não, dispara 1 retry de correção; se ainda falhar,
    substitui analise_mestre por um fallback não-LLM formatando a linha literal.
    """

    lances_esperados = linha_principal[:2]
    if not lances_esperados:
        return revisao

    faltantes = lances_faltantes(revisao.analise_mestre, lances_esperados)
    if not faltantes:
        return revisao

    logger.warning(
        "analise_mestre não citou os lances %s da linha principal; tentando "
        "correção.",
        faltantes,
    )
    revisao_base = revisao
    try:
        response_text = call_gemini(
            client,
            correction_prompt_analise_mestre(prompt, linha_principal, faltantes),
            logger,
        )
        revisao_corrigida = parse_revisao(response_text)
        revisao_base = revisao_corrigida
        if not lances_faltantes(revisao_corrigida.analise_mestre, lances_esperados):
            return revisao_corrigida
    except ValidationError as error:
        logger.warning("Retry de analise_mestre falhou na validação: %s", error)

    logger.warning(
        "analise_mestre ainda incorreta após retry; usando fallback não-LLM."
    )
    return revisao_base.model_copy(
        update={"analise_mestre": fallback_analise_mestre(linha_principal)}
    )


def gerar_revisao(
    client: Any,
    prompt: str,
    logger: logging.Logger,
    linha_principal: list[str] | None = None,
) -> RevisaoRaciocinio:
    """Chama o Gemini e valida, com uma tentativa extra de correção."""

    response_text = call_gemini(client, prompt, logger)
    try:
        revisao = parse_revisao(response_text)
    except ValidationError as validation_error:
        response_text = call_gemini(
            client, correction_prompt(prompt, validation_error), logger
        )
        revisao = parse_revisao(response_text)

    if linha_principal:
        revisao = validar_analise_mestre(
            client, prompt, revisao, linha_principal, logger
        )
    return revisao


def inserir_revisao(
    client: Client,
    anotacao: dict[str, Any],
    qualidade_lance: str,
    avaliacao: AvaliacaoLance,
    revisao: RevisaoRaciocinio,
) -> None:
    """Insere a revisão na tabela dedicada, sem tocar em diagnosticos."""

    client.table("revisoes_pensamento").insert(
        {
            "partida_id": anotacao["partida_id"],
            "numero_lance": anotacao["numero_lance"],
            "texto_pensamento": anotacao.get("texto_pensamento"),
            "qualidade_lance": qualidade_lance,
            "lance_jogado": avaliacao.lance_jogado,
            "melhor_lance": avaliacao.melhor_lance,
            "queda_win_percent": avaliacao.queda_win_percent,
            "qualidade_raciocinio": revisao.qualidade_raciocinio,
            "feedback_texto": revisao.feedback_texto,
        }
    ).execute()


def run() -> None:
    """Executa a revisão das anotações pendentes."""

    logger = configure_logging()
    settings = load_settings()
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    gemini_client = genai.Client(api_key=settings.gemini_api_key)
    engine = Stockfish(
        path=settings.stockfish_path,
        depth=settings.stockfish_depth,
        turn_perspective=False,
    )

    anotacoes = fetch_anotacoes(client, logger)
    revisadas = fetch_revisadas(client, logger)
    elegiveis = selecionar_elegiveis(anotacoes, revisadas)
    log_and_print(logger, f"Anotações a revisar: {len(elegiveis)}.")

    revisadas_ok = falhas = 0
    start_time = time.time()
    for index, anotacao in enumerate(elegiveis, start=1):
        chave = (anotacao.get("partida_id"), anotacao.get("numero_lance"))
        try:
            partida = _get_partida(anotacao)
            pgn = partida.get("pgn")
            cor_jogada = partida.get("cor_jogada")
            if not isinstance(pgn, str) or not pgn.strip() or not cor_jogada:
                raise ValueError("Partida sem PGN ou cor_jogada válidos")

            avaliacao = avaliar_lance(
                engine, pgn, int(anotacao["numero_lance"]), cor_jogada
            )
            qualidade_lance = classificar_qualidade_lance(
                avaliacao.queda_win_percent,
                settings.limiar_lance_bom,
                settings.limiar_lance_ruim,
            )
            prompt = build_prompt(
                anotacao.get("texto_pensamento") or "", avaliacao, qualidade_lance
            )
            revisao = gerar_revisao(
                gemini_client, prompt, logger, avaliacao.linha_principal
            )
            inserir_revisao(client, anotacao, qualidade_lance, avaliacao, revisao)
            revisadas_ok += 1
        except Exception as error:
            falhas += 1
            logger.exception("Falha ao revisar %s", chave)
            log_and_print(logger, f"Anotação {chave} falhou: {error}")
        log_and_print(
            logger,
            format_progress(
                "Revisão de pensamento", "anotações", index, len(elegiveis), time.time() - start_time
            ),
        )

    log_and_print(
        logger,
        f"Resumo: {revisadas_ok} revisões geradas, {falhas} falharam.",
    )


if __name__ == "__main__":
    run()
