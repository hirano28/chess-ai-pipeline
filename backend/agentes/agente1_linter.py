"""Gera diagnósticos estratégicos para lances críticos usando Gemini."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import chess.pgn
import google.genai as genai
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import (  # noqa: E402
    configurar_encoding_utf8,
    format_progress,
    log_and_print,
)

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "agente1_linter.log"
MODEL_NAME = "gemini-flash-latest"
PAGE_SIZE = 1000
VALIDATION_RETRY_LIMIT = 1
SERVER_ERROR_RETRY_LIMIT = 3
SERVER_ERROR_BACKOFF_SECONDS = (5, 15, 45)


TagFalha = Literal[
    "perda_de_material",
    "seguranca_do_rei",
    "calculo_tatico_deficiente",
    "visao_em_tunel",
    "perda_de_iniciativa",
    "erro_tecnico_de_final",
    "fraqueza_estrutural_de_peoes",
    "negligencia_profilatica",
    "gestao_de_tempo_ruim",
    "abertura_de_linhas_desfavoravel",
    "simplificacao_prematura",
    "avaliacao_posicional_incorreta",
    "troca_desfavoravel",
    "falta_de_coordenacao_de_pecas",
    "ataque_prematuro",
    "passividade_excessiva",
]


class DiagnosticoLance(BaseModel):
    """Schema estruturado de um diagnóstico gerado pelo agente."""

    fase_do_jogo: Literal["ABERTURA", "MEIO_JOGO", "FINAL"]
    tags_falha: list[TagFalha]
    diagnostico_mecanico: str
    raiz_conceitual_violada: str
    refinamento_pos_revisao: str
    acao_corretiva_sugerida: str
    confianca_diagnostico: Literal["ALTA", "MEDIA", "BAIXA"]


@dataclass(frozen=True)
class ProcessResult:
    """Resultado do processamento de um lance."""

    lance_id: Any
    diagnostico: DiagnosticoLance


@dataclass(frozen=True)
class AgentSettings:
    """Configurações do Supabase, Gemini e controle de chamadas."""

    supabase_url: str
    supabase_service_role_key: str
    gemini_api_key: str
    rate_limit_sleep_seconds: float
    limiar_apuro_tempo_seg: float


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do agente."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("agente1_linter")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


def load_settings() -> AgentSettings:
    """Carrega e valida as configurações do ambiente."""

    load_dotenv(PROJECT_ROOT / ".env")
    required = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )

    raw_sleep = os.getenv("GEMINI_RATE_LIMIT_SLEEP_SEC", "2")
    try:
        sleep_seconds = float(raw_sleep)
    except ValueError as error:
        raise ValueError(
            "GEMINI_RATE_LIMIT_SLEEP_SEC deve ser um número"
        ) from error
    if sleep_seconds < 0:
        raise ValueError("GEMINI_RATE_LIMIT_SLEEP_SEC não pode ser negativo")

    raw_limiar = os.getenv("LIMIAR_APURO_TEMPO_SEG", "15")
    try:
        limiar_apuro_tempo_seg = float(raw_limiar)
    except ValueError as error:
        raise ValueError("LIMIAR_APURO_TEMPO_SEG deve ser um número") from error

    return AgentSettings(
        supabase_url=required["SUPABASE_URL"],
        supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],
        gemini_api_key=required["GEMINI_API_KEY"],
        rate_limit_sleep_seconds=sleep_seconds,
        limiar_apuro_tempo_seg=limiar_apuro_tempo_seg,
    )


def fetch_critical_moves(
    supabase_client: Client, logger: logging.Logger
) -> list[dict[str, Any]]:
    """Busca lances críticos com o PGN da partida e o tempo de relógio, quando existirem."""

    moves: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            supabase_client.table("lances_criticos")
            .select("*, partidas(*)")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        moves.extend(page)
        logger.info(
            "Página de lances críticos carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    tempos_index = fetch_tempos_lance_index(supabase_client, logger)
    for lance in moves:
        attach_tempo_lance(lance, tempos_index)
    return moves


def fetch_tempos_lance_index(
    supabase_client: Client, logger: logging.Logger
) -> dict[tuple[Any, int, str], dict[str, Any]]:
    """Indexa tempos_lance por (partida_id, numero_lance, cor), em páginas."""

    index: dict[tuple[Any, int, str], dict[str, Any]] = {}
    offset = 0
    while True:
        response = (
            supabase_client.table("tempos_lance")
            .select("partida_id, numero_lance, cor, tempo_restante_seg, tempo_gasto_seg")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        for row in page:
            chave = (row.get("partida_id"), row.get("numero_lance"), row.get("cor"))
            index[chave] = row
        logger.info(
            "Página de tempos_lance carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            return index
        offset += PAGE_SIZE


def attach_tempo_lance(
    lance: dict[str, Any],
    tempos_index: dict[tuple[Any, int, str], dict[str, Any]],
) -> None:
    """Preenche tempo_restante_seg/tempo_gasto_seg no lance, quando existirem.

    Partidas do Chess.com ou lances sem esse dado simplesmente não recebem os
    campos, e o restante do fluxo continua funcionando normalmente.
    """

    try:
        partida = get_partida(lance)
    except ValueError:
        return
    cor_jogada = partida.get("cor_jogada")
    numero_lance = lance.get("numero_lance")
    if cor_jogada is None or numero_lance is None:
        return
    chave = (partida.get("id"), int(numero_lance), cor_jogada)
    tempo_row = tempos_index.get(chave)
    if tempo_row is not None:
        lance["tempo_restante_seg"] = tempo_row.get("tempo_restante_seg")
        lance["tempo_gasto_seg"] = tempo_row.get("tempo_gasto_seg")


def fetch_diagnosed_move_ids(
    supabase_client: Client, logger: logging.Logger
) -> set[Any]:
    """Busca os lance_id que já possuem diagnóstico, em páginas."""

    diagnosed_ids: set[Any] = set()
    offset = 0
    while True:
        response = (
            supabase_client.table("diagnosticos")
            .select("lance_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        diagnosed_ids.update(
            item["lance_id"] for item in page if item.get("lance_id") is not None
        )
        logger.info(
            "Página de diagnósticos carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            return diagnosed_ids
        offset += PAGE_SIZE


def get_partida(lance: dict[str, Any]) -> dict[str, Any]:
    """Obtém a partida do relacionamento retornado pelo Supabase."""

    partida = lance.get("partidas") or lance.get("partida")
    if isinstance(partida, list):
        partida = partida[0] if partida else None
    if not isinstance(partida, dict):
        raise ValueError(f"Lance {lance.get('id')} não possui partida relacionada")
    return partida


def reconstruct_context(pgn: str, move_number: int) -> str:
    """Reconstrói os dois lances completos anteriores ao lance crítico."""

    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise ValueError("Não foi possível fazer parse do PGN da partida")

    first_move = max(1, move_number - 2)
    board = game.board()
    moves_by_number: dict[int, list[str]] = {}
    for move in game.mainline_moves():
        current_move_number = board.fullmove_number
        if first_move <= current_move_number < move_number:
            moves_by_number.setdefault(current_move_number, []).append(
                board.san(move)
            )
        board.push(move)
        if current_move_number >= move_number:
            break

    context_tokens: list[str] = []
    for current_move_number, san_moves in sorted(moves_by_number.items()):
        if len(san_moves) == 1 and current_move_number > 1:
            context_tokens.extend([f"{current_move_number}...", san_moves[0]])
        else:
            context_tokens.extend([f"{current_move_number}.", *san_moves])
    return " ".join(context_tokens) or "(sem lances anteriores disponíveis)"


def reconstruct_erosion_window(
    pgn: str, move_start: int, move_end: int, color: str
) -> str:
    """Reconstrói apenas os lances do jogador dentro da janela de erosão."""

    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        raise ValueError("Não foi possível fazer parse do PGN da partida")

    player_is_white = str(color).strip().upper() == "BRANCAS"
    board = game.board()
    tokens: list[str] = []
    for move in game.mainline_moves():
        current_move_number = board.fullmove_number
        if current_move_number > move_end:
            break
        is_white_move = board.turn == chess.WHITE
        if (
            move_start <= current_move_number <= move_end
            and is_white_move == player_is_white
        ):
            san = board.san(move)
            prefixo = f"{current_move_number}." if player_is_white else f"{current_move_number}..."
            tokens.append(f"{prefixo} {san}")
        board.push(move)
    return " ".join(tokens) or "(sem lances do jogador na janela)"



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
    client: Any,
    prompt: str,
    sleep_seconds: float,
    logger: logging.Logger,
) -> str:
    """Chama o Gemini, repetindo erros 503 com backoff exponencial."""

    for attempt in range(SERVER_ERROR_RETRY_LIMIT):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            time.sleep(sleep_seconds)
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


def build_prompt(
    lance: dict[str, Any], context: str, time_pressure_note: str = ""
) -> str:
    """Monta o prompt estruturado para o diagnóstico estratégico."""

    return f"""Você é um treinador de xadrez. Faça um traceback estratégico do lance abaixo.

Antes de responder, analise silenciosamente em 3 etapas: (1) o que mudou
mecanicamente na posição, (2) quais 1-2 lances anteriores podem explicar a
causa raiz, e (3) qual princípio conceitual foi violado e qual ação corrige o
padrão. Não exponha esse raciocínio intermediário na resposta.

Responda ESTRITAMENTE com um único JSON válido compatível com o schema abaixo,
sem texto antes ou depois e sem markdown fences.

O campo tags_falha deve conter de 1 a 3 tags, escolhidas SOMENTE desta lista
fechada (as mais relevantes). Nunca invente uma tag nova; valores fora desta
lista serão rejeitados na validação:
"perda_de_material", "seguranca_do_rei", "calculo_tatico_deficiente",
"visao_em_tunel", "perda_de_iniciativa", "erro_tecnico_de_final",
"fraqueza_estrutural_de_peoes", "negligencia_profilatica",
"gestao_de_tempo_ruim", "abertura_de_linhas_desfavoravel",
"simplificacao_prematura", "avaliacao_posicional_incorreta",
"troca_desfavoravel", "falta_de_coordenacao_de_pecas",
"ataque_prematuro", "passividade_excessiva".

Schema:
{{
  "fase_do_jogo": "ABERTURA|MEIO_JOGO|FINAL",
  "tags_falha": ["escolher 1 a 3 tags da lista fechada acima"],
  "diagnostico_mecanico": "string",
  "raiz_conceitual_violada": "string",
  "refinamento_pos_revisao": "string",
  "acao_corretiva_sugerida": "string",
  "confianca_diagnostico": "ALTA|MEDIA|BAIXA"
}}

Dados do lance:
- lance_notacao: {lance.get('lance_notacao')}
- avaliacao_antes_cp: {lance.get('avaliacao_antes_cp')}
- avaliacao_depois_cp: {lance.get('avaliacao_depois_cp')}
- numero_lance: {lance.get('numero_lance')}
- trecho_pgn_das_duas_jogadas_anteriores: {context}
{time_pressure_note}"""


def em_apuro_de_tempo(
    tempo_restante_seg: float,
    tempo_gasto_seg: float | None,
    limiar_seg: float,
) -> bool:
    """Detecta apuro de tempo: relógio baixo, ou lance muito rápido com pouco tempo."""

    if tempo_restante_seg <= limiar_seg:
        return True
    return (
        tempo_gasto_seg is not None
        and tempo_restante_seg <= 30
        and tempo_gasto_seg <= 2
    )


def build_time_pressure_note(
    tempo_restante_seg: float, tempo_gasto_seg: float | None
) -> str:
    """Monta a nota de apuro de tempo a ser anexada ao prompt de diagnóstico."""

    gasto_display = (
        f"{tempo_gasto_seg:.1f}s" if tempo_gasto_seg is not None else "um tempo não registrado"
    )
    return (
        f"- apuro_de_tempo: O jogador tinha apenas {tempo_restante_seg:.1f}s restantes "
        f"no relógio e gastou apenas {gasto_display} neste lance - considere fortemente "
        "que isso foi um erro causado por apuro de tempo, não por desconhecimento "
        "conceitual, e inclua a tag gestao_de_tempo_ruim entre as tags escolhidas quando "
        "isso for o caso.\n"
    )


def montar_time_pressure_note(lance: dict[str, Any], limiar_seg: float) -> str:
    """Retorna a nota de apuro de tempo do lance, ou string vazia se não aplicável."""

    tempo_restante_seg = lance.get("tempo_restante_seg")
    if tempo_restante_seg is None:
        return ""
    tempo_gasto_seg = lance.get("tempo_gasto_seg")
    if not em_apuro_de_tempo(tempo_restante_seg, tempo_gasto_seg, limiar_seg):
        return ""
    return build_time_pressure_note(tempo_restante_seg, tempo_gasto_seg)


def build_erosion_prompt(
    lance: dict[str, Any], window_moves: str, color: str
) -> str:
    """Monta o prompt de diagnóstico para um evento de erosão (sequência)."""

    cor_legivel = "Brancas" if str(color).strip().upper() == "BRANCAS" else "Pretas"
    numero_lance = lance.get("numero_lance")
    numero_lance_fim = lance.get("numero_lance_fim")
    return f"""Você é um treinador de xadrez. Analise um evento de EROSÃO ESTRATÉGICA:
uma perda de vantagem GRADUAL ao longo de uma SEQUÊNCIA de lances (do lance
{numero_lance} até o lance {numero_lance_fim}), não um erro isolado de um único lance.

O jogador analisado está jogando de {cor_legivel}. Explique o PADRÃO que causou a
erosão gradual ao longo dessa sequência específica — não aponte um único
"lance culpado".

REGRA OBRIGATÓRIA: não descreva lances de fora do intervalo
[{numero_lance}, {numero_lance_fim}] e não inverta a perspectiva — todas as ações
analisadas são do jogador de {cor_legivel}, nunca do oponente.

Antes de responder, analise silenciosamente em 3 etapas: (1) como a vantagem foi
se deteriorando ao longo da sequência, (2) qual padrão recorrente do jogador de
{cor_legivel} explica a queda, e (3) qual princípio conceitual foi violado e qual
ação corrige o padrão. Não exponha esse raciocínio intermediário na resposta.

Responda ESTRITAMENTE com um único JSON válido compatível com o schema abaixo,
sem texto antes ou depois e sem markdown fences.

O campo tags_falha deve conter de 1 a 3 tags, escolhidas SOMENTE desta lista
fechada (as mais relevantes). Nunca invente uma tag nova; valores fora desta
lista serão rejeitados na validação:
"perda_de_material", "seguranca_do_rei", "calculo_tatico_deficiente",
"visao_em_tunel", "perda_de_iniciativa", "erro_tecnico_de_final",
"fraqueza_estrutural_de_peoes", "negligencia_profilatica",
"gestao_de_tempo_ruim", "abertura_de_linhas_desfavoravel",
"simplificacao_prematura", "avaliacao_posicional_incorreta",
"troca_desfavoravel", "falta_de_coordenacao_de_pecas",
"ataque_prematuro", "passividade_excessiva".

Schema:
{{
  "fase_do_jogo": "ABERTURA|MEIO_JOGO|FINAL",
  "tags_falha": ["escolher 1 a 3 tags da lista fechada acima"],
  "diagnostico_mecanico": "string",
  "raiz_conceitual_violada": "string",
  "refinamento_pos_revisao": "string",
  "acao_corretiva_sugerida": "string",
  "confianca_diagnostico": "ALTA|MEDIA|BAIXA"
}}

Dados do evento de erosão:
- tipo_evento: EROSAO
- cor_do_jogador: {cor_legivel}
- numero_lance_inicio: {numero_lance}
- numero_lance_fim: {numero_lance_fim}
- avaliacao_antes_cp (início da janela): {lance.get('avaliacao_antes_cp')}
- avaliacao_depois_cp (fim da janela): {lance.get('avaliacao_depois_cp')}
- queda_win_percent: {lance.get('queda_win_percent')}
- lances_do_jogador_na_janela: {window_moves}
"""


def montar_prompt(
    lance: dict[str, Any], partida: dict[str, Any], limiar_apuro_tempo_seg: float = 15.0
) -> str:
    """Escolhe o prompt adequado ao tipo de evento (PICO ou EROSAO)."""

    pgn = partida.get("pgn")
    if not isinstance(pgn, str) or not pgn.strip():
        raise ValueError(f"Lance {lance.get('id')} não possui PGN da partida")

    tipo_evento = str(lance.get("tipo_evento") or "PICO").upper()
    if tipo_evento == "EROSAO":
        move_start = int(lance["numero_lance"])
        move_end = int(lance.get("numero_lance_fim") or move_start)
        color = partida.get("cor_jogada")
        window = reconstruct_erosion_window(pgn, move_start, move_end, color)
        return build_erosion_prompt(lance, window, color)

    context = reconstruct_context(pgn, int(lance["numero_lance"]))
    time_pressure_note = montar_time_pressure_note(lance, limiar_apuro_tempo_seg)
    return build_prompt(lance, context, time_pressure_note)



def correction_prompt(original_prompt: str, error: ValidationError) -> str:
    """Solicita correção quando o primeiro JSON não valida no Pydantic."""

    return f"""{original_prompt}

A resposta anterior falhou na validação Pydantic com este erro específico:
{error}

Corrija todos os problemas e responda novamente apenas com o JSON válido,
sem markdown e sem explicações externas."""


def parse_diagnosis(text: str) -> DiagnosticoLance:
    """Limpa a resposta e valida o JSON contra DiagnosticoLance."""

    return DiagnosticoLance.model_validate_json(strip_json_fences(text))


def processar_lance(
    lance: dict,
    client: Any,
    settings: AgentSettings | None = None,
    logger: logging.Logger | None = None,
) -> ProcessResult:
    """Gera e valida o diagnóstico de um lance crítico."""

    settings = settings or load_settings()
    logger = logger or configure_logging()
    partida = get_partida(lance)
    prompt = montar_prompt(lance, partida, settings.limiar_apuro_tempo_seg)
    response_text = call_gemini(client, prompt, settings.rate_limit_sleep_seconds, logger)
    try:
        diagnosis = parse_diagnosis(response_text)
    except ValidationError as validation_error:
        response_text = call_gemini(
            client,
            correction_prompt(prompt, validation_error),
            settings.rate_limit_sleep_seconds,
            logger,
        )
        diagnosis = parse_diagnosis(response_text)
    return ProcessResult(lance_id=lance["id"], diagnostico=diagnosis)


def insert_diagnosis(supabase_client: Client, result: ProcessResult) -> None:
    """Insere um diagnóstico validado vinculado ao lance correto."""

    payload = result.diagnostico.model_dump()
    payload.update(
        {
            "lance_id": result.lance_id,
            "status": "validado",
            "schema_version": "1.1",
        }
    )
    supabase_client.table("diagnosticos").insert(payload).execute()


def main() -> None:
    """Processa lances sem diagnóstico e imprime o resumo final."""

    logger = configure_logging()
    processed = failed = skipped = 0
    try:
        settings = load_settings()
        supabase_client = create_client(
            settings.supabase_url, settings.supabase_service_role_key
        )
        gemini_client = genai.Client(api_key=settings.gemini_api_key)
        all_moves = fetch_critical_moves(supabase_client, logger)
        diagnosed_ids = fetch_diagnosed_move_ids(supabase_client, logger)
        total_a_processar = sum(
            1 for lance in all_moves if lance.get("id") not in diagnosed_ids
        )
        attempted = 0
        start_time = time.time()
        for lance in all_moves:
            if lance.get("id") in diagnosed_ids:
                skipped += 1
                continue
            attempted += 1
            try:
                result = processar_lance(
                    lance, gemini_client, settings=settings, logger=logger
                )
                insert_diagnosis(supabase_client, result)
                processed += 1
            except Exception:
                failed += 1
                logger.error(
                    "Falha completa ao processar lance %s:\n%s",
                    lance.get("id", "desconhecido"),
                    traceback.format_exc(),
                )
            if attempted % 5 == 0:
                log_and_print(
                    logger,
                    format_progress(
                        "Diagnóstico",
                        "lances",
                        attempted,
                        total_a_processar,
                        time.time() - start_time,
                    ),
                )
    except Exception:
        failed += 1
        logger.error("Falha geral do agente:\n%s", traceback.format_exc())

    print(f"Lances processados com sucesso: {processed}")
    print(f"Lances com falha: {failed}")
    print(f"Lances já diagnosticados e pulados: {skipped}")


if __name__ == "__main__":
    main()
