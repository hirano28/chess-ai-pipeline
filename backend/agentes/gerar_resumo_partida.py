"""Sintetiza narrativa de partida inteira a partir dos dados já existentes.

Não recalcula nada: apenas compõe lances_criticos + diagnosticos +
metricas_lichess_partida + tempos_lance numa narrativa coesa via Gemini,
com validação anti-alucinação obrigatória.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chess
import chess.pgn
import google.genai as genai
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
from stockfish import Stockfish
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.agente1_linter import em_apuro_de_tempo  # noqa: E402
from backend.agentes.agente2_analista import HEXAGON_CATEGORIES  # noqa: E402
from backend.agentes.revisar_pensamento import (  # noqa: E402
    lances_inventados,
    obter_linha_principal,
    obter_top_candidatos,
)
from backend.common.progress import (  # noqa: E402
    configurar_encoding_utf8,
    format_duration,
    format_progress,
    log_and_print,
)

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "gerar_resumo_partida.log"
MODEL_NAME = "gemini-flash-latest"
PAGE_SIZE = 1000
LIMIAR_APURO_TEMPO_SEG = 15.0
SERVER_ERROR_RETRY_LIMIT = 3
SERVER_ERROR_BACKOFF_SECONDS = (5, 15, 45)
MAX_ANTI_HALLUCINATION_RETRIES = 1


# ---------------------------------------------------------------------------
# Pydantic schema da resposta do Gemini
# ---------------------------------------------------------------------------

class PontoCritico(BaseModel):
    """Um ponto crítico extraído da partida."""

    numero_lance: int
    tipo_evento: str
    tags_falha: list[str]


class ResumoPartida(BaseModel):
    """Schema da narrativa gerada pelo Gemini."""

    narrativa: str
    pontos_criticos: list[PontoCritico]
    momento_chave_estrategico: str


# ---------------------------------------------------------------------------
# Dataclass de dados coletados de uma partida
# ---------------------------------------------------------------------------

@dataclass
class LanceCriticoComDiagnostico:
    """Lance crítico com seu diagnóstico associado."""

    numero_lance: int
    numero_lance_fim: int | None
    tipo_evento: str
    lance_notacao: str | None
    queda_win_percent: float | None
    avaliacao_antes_cp: int | None
    avaliacao_depois_cp: int | None
    tags_falha: list[str]
    diagnostico_mecanico: str
    tipo_erro: str | None
    linha_principal_motor: list[str] = field(default_factory=list)
    top_candidatos_motor: list[dict] = field(default_factory=list)


@dataclass
class DadosPartida:
    """Dados consolidados de uma partida para gerar o resumo."""

    partida_id: str
    cor_jogada: str | None
    eco_abertura: str | None
    resultado: str | None
    lances_criticos: list[LanceCriticoComDiagnostico]
    metricas_lichess: dict[str, Any] | None
    lances_em_apuro_de_tempo: int
    total_lances_criticos_com_tempo: int
    pgn: str | None = None


# ---------------------------------------------------------------------------
# Configuração e logging
# ---------------------------------------------------------------------------

def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do agente."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("gerar_resumo_partida")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


def load_settings() -> dict[str, str]:
    """Carrega e valida as configurações do ambiente."""

    load_dotenv(PROJECT_ROOT / ".env")
    required = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        "STOCKFISH_PATH": os.getenv("STOCKFISH_PATH"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )
    settings = {name: value for name, value in required.items()}  # type: ignore[misc]
    settings["STOCKFISH_DEPTH"] = os.getenv("STOCKFISH_DEPTH", "16")
    return settings


# ---------------------------------------------------------------------------
# Busca de dados no Supabase
# ---------------------------------------------------------------------------

def fetch_partidas_elegiveis(
    client: Client, logger: logging.Logger
) -> list[str]:
    """Retorna IDs de partidas com diagnósticos completos e sem resumo ainda.

    Lógica:
    1. Busca todos os partida_id distintos que possuem pelo menos 1 diagnóstico
       (via lances_criticos → diagnosticos).
    2. Subtrai os partida_id que já estão em resumo_partida.
    """

    # Passo 1: partidas com diagnósticos
    partidas_com_diag: set[str] = set()
    offset = 0
    while True:
        response = (
            client.table("lances_criticos")
            .select("partida_id, diagnosticos(id)")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        for row in page:
            diags = row.get("diagnosticos")
            # diagnosticos pode ser lista (1-to-many) ou dict ou None
            has_diag = False
            if isinstance(diags, list) and len(diags) > 0:
                has_diag = True
            elif isinstance(diags, dict) and diags.get("id"):
                has_diag = True
            if has_diag and row.get("partida_id"):
                partidas_com_diag.add(row["partida_id"])
        logger.info(
            "Página de lances_criticos para elegibilidade: %d registros (offset %d)",
            len(page), offset,
        )
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    if not partidas_com_diag:
        return []

    # Passo 2: partidas que já têm resumo
    partidas_resumidas: set[str] = set()
    offset = 0
    while True:
        response = (
            client.table("resumo_partida")
            .select("partida_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        partidas_resumidas.update(row["partida_id"] for row in page if row.get("partida_id"))
        logger.info(
            "Página de resumo_partida existentes: %d registros (offset %d)",
            len(page), offset,
        )
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    elegiveis = sorted(partidas_com_diag - partidas_resumidas)
    logger.info(
        "Partidas elegíveis: %d (com diagnóstico: %d, já resumidas: %d)",
        len(elegiveis), len(partidas_com_diag), len(partidas_resumidas),
    )
    return elegiveis


def coletar_dados_partida(
    client: Client, partida_id: str, logger: logging.Logger
) -> DadosPartida:
    """Coleta todos os dados de uma partida necessários para a narrativa."""

    # Dados da partida
    partida_resp = (
        client.table("partidas")
        .select("id, cor_jogada, eco_abertura, resultado, pgn")
        .eq("id", partida_id)
        .execute()
    )
    partida_row = (partida_resp.data or [{}])[0]
    cor_jogada = partida_row.get("cor_jogada")
    eco_abertura = partida_row.get("eco_abertura")
    resultado = partida_row.get("resultado")
    pgn = partida_row.get("pgn")

    # Lances críticos com diagnósticos
    lances_resp = (
        client.table("lances_criticos")
        .select(
            "numero_lance, numero_lance_fim, tipo_evento, lance_notacao, "
            "queda_win_percent, avaliacao_antes_cp, avaliacao_depois_cp, "
            "diagnosticos(tags_falha, diagnostico_mecanico, tipo_erro)"
        )
        .eq("partida_id", partida_id)
        .execute()
    )
    lances_criticos: list[LanceCriticoComDiagnostico] = []
    for row in lances_resp.data or []:
        diag = row.get("diagnosticos")
        if isinstance(diag, list):
            diag = diag[0] if diag else None
        if not isinstance(diag, dict):
            continue  # Sem diagnóstico → pula
        lances_criticos.append(
            LanceCriticoComDiagnostico(
                numero_lance=row.get("numero_lance", 0),
                numero_lance_fim=row.get("numero_lance_fim"),
                tipo_evento=row.get("tipo_evento", "PICO"),
                lance_notacao=row.get("lance_notacao"),
                queda_win_percent=row.get("queda_win_percent"),
                avaliacao_antes_cp=row.get("avaliacao_antes_cp"),
                avaliacao_depois_cp=row.get("avaliacao_depois_cp"),
                tags_falha=diag.get("tags_falha") or [],
                diagnostico_mecanico=diag.get("diagnostico_mecanico") or "",
                tipo_erro=diag.get("tipo_erro"),
            )
        )

    # Métricas Lichess (opcional)
    metricas_resp = (
        client.table("metricas_lichess_partida")
        .select("*")
        .eq("partida_id", partida_id)
        .execute()
    )
    metricas_rows = metricas_resp.data or []
    metricas_lichess = metricas_rows[0] if metricas_rows else None

    # Tempos de lance → contar lances críticos em apuro de tempo
    tempos_resp = (
        client.table("tempos_lance")
        .select("numero_lance, cor, tempo_restante_seg, tempo_gasto_seg")
        .eq("partida_id", partida_id)
        .execute()
    )
    tempos_index: dict[tuple[int, str], dict[str, Any]] = {}
    for row in tempos_resp.data or []:
        chave = (row.get("numero_lance", 0), row.get("cor", ""))
        tempos_index[chave] = row

    lances_em_apuro = 0
    lances_com_tempo = 0
    for lc in lances_criticos:
        cor = cor_jogada or ""
        tempo_row = tempos_index.get((lc.numero_lance, cor))
        if tempo_row and tempo_row.get("tempo_restante_seg") is not None:
            lances_com_tempo += 1
            if em_apuro_de_tempo(
                tempo_row["tempo_restante_seg"],
                tempo_row.get("tempo_gasto_seg"),
                LIMIAR_APURO_TEMPO_SEG,
            ):
                lances_em_apuro += 1

    return DadosPartida(
        partida_id=partida_id,
        cor_jogada=cor_jogada,
        eco_abertura=eco_abertura,
        resultado=resultado,
        lances_criticos=lances_criticos,
        metricas_lichess=metricas_lichess,
        lances_em_apuro_de_tempo=lances_em_apuro,
        total_lances_criticos_com_tempo=lances_com_tempo,
        pgn=pgn,
    )


# ---------------------------------------------------------------------------
# Classificação de tags pelo hexágono
# ---------------------------------------------------------------------------

def classificar_tags_por_hexagono(
    tags_falha_list: list[str],
) -> dict[str, int]:
    """Classifica uma lista de tags_falha nas categorias do hexágono.

    Usa HEXAGON_CATEGORIES importado de agente2_analista.py.
    Tags não reconhecidas são ignoradas.
    """

    contagem: dict[str, int] = {cat: 0 for cat in HEXAGON_CATEGORIES}
    tag_para_categoria: dict[str, str] = {}
    for categoria, tags in HEXAGON_CATEGORIES.items():
        for tag in tags:
            tag_para_categoria[tag] = categoria

    for tag in tags_falha_list:
        categoria = tag_para_categoria.get(tag)
        if categoria:
            contagem[categoria] += 1

    return contagem


# ---------------------------------------------------------------------------
# Enriquecimento com dados reais do motor (Stockfish)
# ---------------------------------------------------------------------------

def reconstruir_posicao_antes(
    pgn: str, numero_lance: int, cor_jogada: str
) -> chess.Board | None:
    """Reconstrói o tabuleiro imediatamente ANTES do lance numero_lance/cor_jogada.

    Percorre o PGN lance a lance (mesmo padrão de avaliar_lance em
    revisar_pensamento.py) até o instante em que é a vez de cor_jogada jogar
    o numero_lance. Retorna None se o PGN for inválido ou o lance não existir.
    """

    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except Exception:
        return None
    if game is None:
        return None

    board = game.board()
    for move in game.mainline_moves():
        playing_color = "BRANCAS" if board.turn == chess.WHITE else "PRETAS"
        if board.fullmove_number == numero_lance and playing_color == cor_jogada:
            return board.copy()
        board.push(move)
    return None


def selecionar_evento_chave(
    lances_criticos: list[LanceCriticoComDiagnostico],
) -> LanceCriticoComDiagnostico | None:
    """Escolhe o evento usado como momento_chave_estrategico.

    Preferência: primeira EROSÃO da lista; na ausência, primeiro PICO. Mesma
    preferência já sugerida ao Gemini no prompt e usada no fallback literal.
    """

    for lc in lances_criticos:
        if lc.tipo_evento == "EROSAO":
            return lc
    for lc in lances_criticos:
        if lc.tipo_evento == "PICO":
            return lc
    return None


def enriquecer_com_dados_motor(
    dados: DadosPartida, engine: Stockfish, logger: logging.Logger
) -> None:
    """Preenche linha_principal_motor/top_candidatos_motor com dados reais do motor.

    - Evento usado como momento_chave_estrategico: reconstrói a posição antes
      do 1º lance da janela e consulta a linha principal (3-5 lances) que o
      motor recomendaria a partir dali.
    - Eventos PICO com alguma tag da categoria TATICA (hexágono): reconstrói a
      posição antes do lance jogado e consulta os 2-3 melhores candidatos
      reais do motor naquele ponto.

    Sem PGN ou cor_jogada não há como reconstruir posições — não faz nada.
    """

    if not dados.pgn or not dados.cor_jogada:
        return

    evento_chave = selecionar_evento_chave(dados.lances_criticos)
    if evento_chave is not None:
        board = reconstruir_posicao_antes(
            dados.pgn, evento_chave.numero_lance, dados.cor_jogada
        )
        if board is not None:
            evento_chave.linha_principal_motor = obter_linha_principal(
                engine, board, num_lances=5
            )
            if not evento_chave.linha_principal_motor:
                logger.warning(
                    "Motor não retornou linha principal para o evento-chave "
                    "(lance %s)",
                    evento_chave.numero_lance,
                )

    tags_tatica = set(HEXAGON_CATEGORIES.get("TATICA", []))
    for lc in dados.lances_criticos:
        if lc.tipo_evento != "PICO":
            continue
        if not any(tag in tags_tatica for tag in lc.tags_falha):
            continue
        board = reconstruir_posicao_antes(dados.pgn, lc.numero_lance, dados.cor_jogada)
        if board is None:
            continue
        lc.top_candidatos_motor = obter_top_candidatos(engine, board, num=3)


# ---------------------------------------------------------------------------
# Prompt para o Gemini
# ---------------------------------------------------------------------------

def build_prompt_resumo(dados: DadosPartida) -> str:
    """Monta o prompt com todos os dados reais para gerar a narrativa."""

    # Listar lances críticos
    lances_texto_parts: list[str] = []
    todas_tags: list[str] = []
    for lc in dados.lances_criticos:
        todas_tags.extend(lc.tags_falha)
        if lc.tipo_evento == "EROSAO":
            linha_texto = (
                f"\n    linha_principal_do_motor a partir daqui: "
                f"{' '.join(lc.linha_principal_motor)}"
                if lc.linha_principal_motor
                else ""
            )
            lances_texto_parts.append(
                f"  - EROSÃO lances {lc.numero_lance}-{lc.numero_lance_fim}: "
                f"tags={lc.tags_falha}, diagnóstico=\"{lc.diagnostico_mecanico}\", "
                f"queda_win%={lc.queda_win_percent}{linha_texto}"
            )
        else:
            notacao = lc.lance_notacao or "?"
            candidatos_texto = (
                "\n    top_candidatos_do_motor nesse ponto: "
                + ", ".join(
                    f"{c['lance']} ({c['avaliacao']})" for c in lc.top_candidatos_motor
                )
                if lc.top_candidatos_motor
                else ""
            )
            lances_texto_parts.append(
                f"  - PICO lance {lc.numero_lance} ({notacao}): "
                f"tags={lc.tags_falha}, diagnóstico=\"{lc.diagnostico_mecanico}\", "
                f"queda_win%={lc.queda_win_percent}, "
                f"eval_antes={lc.avaliacao_antes_cp}cp → eval_depois={lc.avaliacao_depois_cp}cp"
                f"{candidatos_texto}"
            )
    lances_texto = "\n".join(lances_texto_parts) if lances_texto_parts else "(nenhum lance crítico)"

    # Classificação hexagonal
    hexagono = classificar_tags_por_hexagono(todas_tags)
    hexagono_texto = ", ".join(f"{cat}: {count}" for cat, count in hexagono.items() if count > 0)
    if not hexagono_texto:
        hexagono_texto = "(nenhuma categoria com ocorrências)"

    # Métricas Lichess
    if dados.metricas_lichess:
        m = dados.metricas_lichess
        metricas_texto = (
            f"  - Precisão própria: {m.get('precisao_propria')}%\n"
            f"  - ACPL: {m.get('acpl')}\n"
            f"  - Blunders/Erros/Imprecisões: "
            f"{m.get('blunders', '?')}/{m.get('erros', '?')}/{m.get('imprecisoes', '?')}"
        )
    else:
        metricas_texto = "  (métricas Lichess não disponíveis para esta partida)"

    # Pressão de tempo
    if dados.total_lances_criticos_com_tempo > 0:
        tempo_texto = (
            f"  - {dados.lances_em_apuro_de_tempo} de {dados.total_lances_criticos_com_tempo} "
            f"lances críticos ocorreram em apuro de tempo (≤{LIMIAR_APURO_TEMPO_SEG}s no relógio)"
        )
    else:
        tempo_texto = "  (dados de relógio não disponíveis)"

    # Lances reais para referência anti-alucinação (jogado + dados reais do motor)
    lances_permitidos_texto = (
        ", ".join(sorted(coletar_lances_permitidos(dados.lances_criticos)))
        or "(nenhum)"
    )

    return f"""Você é um treinador de xadrez escrevendo um resumo narrativo de uma partida analisada.

Dados REAIS da partida (NÃO invente dados, use APENAS o que está listado abaixo):

Informações gerais:
  - Partida ID: {dados.partida_id}
  - Cor jogada: {dados.cor_jogada or "desconhecida"}
  - Abertura (ECO): {dados.eco_abertura or "desconhecida"}
  - Resultado: {dados.resultado or "desconhecido"}

Lances críticos com diagnósticos:
{lances_texto}

Classificação pelo hexágono de competências:
  {hexagono_texto}

Métricas Lichess:
{metricas_texto}

Pressão de tempo nos lances críticos:
{tempo_texto}

REGRAS OBRIGATÓRIAS:
1. Escreva uma narrativa de 3 a 5 parágrafos cobrindo:
   - Qualidade da abertura/desenvolvimento
   - Momento-chave estratégico (eventos de EROSÃO são candidatos naturais)
   - Pontos críticos táticos (eventos PICO com tags de TATICA)
   - Concentração de pressão de tempo (se houver dados)
   - Síntese final de 1-2 frases sobre o padrão recorrente
2. Cite lances usando EXATAMENTE a notação dos lances críticos listados acima.
   Lances permitidos para citar: {lances_permitidos_texto}
   NÃO invente lances que não estejam nesta lista.
3. O campo momento_chave_estrategico deve ser 1-2 frases identificando o momento
   mais decisivo da partida (preferencialmente um evento de EROSÃO, se existir).
4. O campo pontos_criticos deve ser um array com os pontos mais relevantes.
5. Para os pontos-chave, descreva concretamente qual era o plano/lance correto
   segundo os dados REAIS fornecidos acima (linha_principal_do_motor e
   top_candidatos_do_motor), contrastando com o que foi realmente jogado.
   NÃO invente lances ou planos além dos fornecidos.

Responda ESTRITAMENTE com um único JSON válido, sem texto antes ou depois e sem
markdown fences, compatível com este schema:
{{
  "narrativa": "string (3-5 parágrafos)",
  "pontos_criticos": [
    {{"numero_lance": int, "tipo_evento": "PICO|EROSAO", "tags_falha": ["tag1", ...]}}
  ],
  "momento_chave_estrategico": "string (1-2 frases)"
}}"""


# ---------------------------------------------------------------------------
# Anti-alucinação
# ---------------------------------------------------------------------------

def coletar_lances_permitidos(
    lances_criticos: list[LanceCriticoComDiagnostico],
) -> set[str]:
    """Reúne os lances SAN que a narrativa pode citar sem ser alucinação:
    o lance jogado, a linha principal do motor e os top candidatos do motor
    de cada evento."""

    permitidos: set[str] = set()
    for lc in lances_criticos:
        if lc.lance_notacao:
            permitidos.add(lc.lance_notacao)
        permitidos.update(lc.linha_principal_motor)
        permitidos.update(c["lance"] for c in lc.top_candidatos_motor)
    return permitidos


def validar_narrativa(
    narrativa: str, lances_criticos_reais: list[LanceCriticoComDiagnostico]
) -> list[str]:
    """Retorna lances SAN citados na narrativa que NÃO são lances reais.

    Aceita como permitidos o lance jogado, a linha principal do motor e os
    top candidatos do motor de cada evento. Reaproveita lances_inventados de
    revisar_pensamento.py (mesma lógica de extrair_lances_san + comparação já
    validada ali), generalizada aqui para essas fontes adicionais.
    """

    return lances_inventados(narrativa, coletar_lances_permitidos(lances_criticos_reais))


def correction_prompt_narrativa(
    original_prompt: str,
    lances_inventados: list[str],
    lances_permitidos: list[str],
) -> str:
    """Solicita correção quando a narrativa cita lances inexistentes."""

    inventados_texto = ", ".join(lances_inventados)
    permitidos_texto = ", ".join(lances_permitidos) if lances_permitidos else "(nenhum)"
    return (
        f"{original_prompt}\n\n"
        "A resposta anterior citou lances que NÃO existem nos dados reais da partida. "
        f"Estes lances são INVENTADOS e devem ser removidos: {inventados_texto}\n"
        f"Os ÚNICOS lances que você pode citar são: {permitidos_texto}\n"
        "Reescreva a narrativa sem citar nenhum lance fora dessa lista. "
        "Responda novamente apenas com o JSON válido, sem markdown e sem explicações."
    )


def fallback_resumo(dados: DadosPartida) -> ResumoPartida:
    """Gera resumo sem LLM, formatando os dados reais literalmente."""

    partes: list[str] = []
    picos = [lc for lc in dados.lances_criticos if lc.tipo_evento == "PICO"]
    erosoes = [lc for lc in dados.lances_criticos if lc.tipo_evento == "EROSAO"]

    partes.append(
        f"Partida jogada com {dados.cor_jogada or 'cor desconhecida'}, "
        f"abertura {dados.eco_abertura or 'desconhecida'}, "
        f"resultado: {dados.resultado or 'desconhecido'}."
    )

    if picos:
        desc_picos = "; ".join(
            f"lance {lc.numero_lance} ({lc.lance_notacao or '?'}): {', '.join(lc.tags_falha)}"
            + (
                " [motor recomendava: "
                + ", ".join(c["lance"] for c in lc.top_candidatos_motor) + "]"
                if lc.top_candidatos_motor
                else ""
            )
            for lc in picos
        )
        partes.append(f"Pontos críticos táticos: {desc_picos}.")

    if erosoes:
        desc_erosoes = "; ".join(
            f"lances {lc.numero_lance}-{lc.numero_lance_fim}: {', '.join(lc.tags_falha)}"
            for lc in erosoes
        )
        partes.append(f"Erosões estratégicas: {desc_erosoes}.")

    if dados.lances_em_apuro_de_tempo > 0:
        partes.append(
            f"{dados.lances_em_apuro_de_tempo} lance(s) crítico(s) ocorreu(ram) "
            "em apuro de tempo."
        )

    narrativa = " ".join(partes)

    pontos_criticos = [
        PontoCritico(
            numero_lance=lc.numero_lance,
            tipo_evento=lc.tipo_evento,
            tags_falha=lc.tags_falha,
        )
        for lc in dados.lances_criticos
    ]

    momento = ""
    evento_chave = selecionar_evento_chave(dados.lances_criticos)
    if evento_chave is not None:
        if evento_chave.tipo_evento == "EROSAO":
            momento = (
                f"Erosão estratégica entre os lances {evento_chave.numero_lance} e "
                f"{evento_chave.numero_lance_fim}: {evento_chave.diagnostico_mecanico}"
            )
        else:
            momento = (
                f"Ponto crítico no lance {evento_chave.numero_lance} "
                f"({evento_chave.lance_notacao or '?'}): {evento_chave.diagnostico_mecanico}"
            )
        if evento_chave.linha_principal_motor:
            momento += (
                " O plano correto segundo o motor seria: "
                + " ".join(evento_chave.linha_principal_motor) + "."
            )

    return ResumoPartida(
        narrativa=narrativa,
        pontos_criticos=pontos_criticos,
        momento_chave_estrategico=momento,
    )


# ---------------------------------------------------------------------------
# Chamada ao Gemini
# ---------------------------------------------------------------------------

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


def call_gemini(client: Any, prompt: str, logger: logging.Logger) -> str:
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
                attempt + 1, SERVER_ERROR_RETRY_LIMIT, delay, error,
            )
            time.sleep(delay)
    raise RuntimeError("Chamada ao Gemini encerrada sem resultado")


def parse_resumo(text: str) -> ResumoPartida:
    """Limpa a resposta e valida o JSON contra ResumoPartida."""

    return ResumoPartida.model_validate_json(strip_json_fences(text))


def gerar_resumo_gemini(
    client_gemini: Any,
    prompt: str,
    dados: DadosPartida,
    logger: logging.Logger,
) -> ResumoPartida:
    """Gera o resumo via Gemini com validação e anti-alucinação.

    Fluxo:
    1. Chama Gemini → parse JSON → valida Pydantic
    2. Extrai lances SAN da narrativa → compara contra lances reais
    3. Se há lances inventados → retry com correção
    4. Se persistir → fallback literal (sem LLM)
    """

    # Primeira tentativa
    response_text = call_gemini(client_gemini, prompt, logger)
    try:
        resumo = parse_resumo(response_text)
    except (ValidationError, Exception) as error:
        logger.warning("Falha no parse do resumo, tentando fallback: %s", error)
        return fallback_resumo(dados)

    # Anti-alucinação
    inventados = validar_narrativa(resumo.narrativa, dados.lances_criticos)
    if not inventados:
        return resumo

    logger.warning(
        "Lances inventados detectados na narrativa: %s — solicitando correção",
        inventados,
    )

    # Retry de correção
    lances_permitidos = sorted(coletar_lances_permitidos(dados.lances_criticos))
    prompt_correcao = correction_prompt_narrativa(
        prompt, inventados, lances_permitidos
    )
    try:
        response_text = call_gemini(client_gemini, prompt_correcao, logger)
        resumo = parse_resumo(response_text)
        inventados = validar_narrativa(resumo.narrativa, dados.lances_criticos)
        if not inventados:
            return resumo
    except Exception as error:
        logger.warning("Falha no retry de correção: %s", error)

    logger.warning(
        "Alucinação persistente após retry — usando fallback literal"
    )
    return fallback_resumo(dados)


# ---------------------------------------------------------------------------
# Inserção no Supabase
# ---------------------------------------------------------------------------

def inserir_resumo(
    client: Client, partida_id: str, resumo: ResumoPartida
) -> None:
    """Insere o resumo na tabela resumo_partida (upsert por partida_id)."""

    payload = {
        "partida_id": partida_id,
        "narrativa": resumo.narrativa,
        "pontos_criticos": [pc.model_dump() for pc in resumo.pontos_criticos],
        "momento_chave_estrategico": resumo.momento_chave_estrategico,
    }
    client.table("resumo_partida").upsert(
        payload, on_conflict="partida_id"
    ).execute()


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def main() -> None:
    """Processa partidas elegíveis e gera resumos narrativos."""

    logger = configure_logging()
    processed = failed = 0
    start_time = time.time()

    try:
        settings = load_settings()
        supabase_client = create_client(
            settings["SUPABASE_URL"], settings["SUPABASE_SERVICE_ROLE_KEY"]
        )
        gemini_client = genai.Client(api_key=settings["GEMINI_API_KEY"])
        engine = Stockfish(
            path=settings["STOCKFISH_PATH"],
            depth=int(settings["STOCKFISH_DEPTH"]),
            turn_perspective=False,
        )

        try:
            elegiveis = fetch_partidas_elegiveis(supabase_client, logger)
            total = len(elegiveis)
            log_and_print(logger, f"Partidas elegíveis para resumo: {total}")

            if total == 0:
                log_and_print(logger, "Nenhuma partida para processar.")

            for i, partida_id in enumerate(elegiveis, 1):
                try:
                    dados = coletar_dados_partida(supabase_client, partida_id, logger)
                    if not dados.lances_criticos:
                        logger.info(
                            "Partida %s sem lances críticos com diagnóstico — pulando",
                            partida_id,
                        )
                        continue

                    enriquecer_com_dados_motor(dados, engine, logger)
                    prompt = build_prompt_resumo(dados)
                    resumo = gerar_resumo_gemini(gemini_client, prompt, dados, logger)
                    inserir_resumo(supabase_client, partida_id, resumo)
                    processed += 1
                    logger.info("Resumo gerado para partida %s", partida_id)
                except Exception:
                    failed += 1
                    logger.error(
                        "Falha ao processar partida %s:\n%s",
                        partida_id, traceback.format_exc(),
                    )

                if i % 5 == 0 or i == total:
                    log_and_print(
                        logger,
                        format_progress(
                            "Resumo", "partidas", i, total,
                            time.time() - start_time,
                        ),
                    )
        finally:
            try:
                engine.send_quit_command()
            except Exception:
                pass

    except Exception:
        logger.error("Falha geral do agente:\n%s", traceback.format_exc())

    elapsed = format_duration(time.time() - start_time)
    log_and_print(logger, f"Resumos gerados com sucesso: {processed}")
    log_and_print(logger, f"Partidas com falha: {failed}")
    log_and_print(logger, f"Tempo total: {elapsed}")


if __name__ == "__main__":
    main()

