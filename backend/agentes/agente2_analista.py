"""Consolida diagnósticos em métricas do hexágono e narra via Gemini."""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import google.genai as genai
import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import log_and_print  # noqa: E402
LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "agente2_analista.log"
MODEL_NAME = "gemini-flash-latest"
PAGE_SIZE = 1000
RECENT_WINDOW_DAYS = 30
CATEGORY_MIN_DIAGNOSTICS = 5

TAGS_VOCABULARY = [
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

HEXAGON_CATEGORIES: dict[str, list[str]] = {
    "TATICA": [
        "calculo_tatico_deficiente",
        "visao_em_tunel",
        "perda_de_material",
    ],
    "ESTRATEGIA": [
        "avaliacao_posicional_incorreta",
        "troca_desfavoravel",
        "simplificacao_prematura",
        "ataque_prematuro",
    ],
    "FINAIS": [
        "erro_tecnico_de_final",
    ],
    "ESTRUTURA_DE_PEOES": [
        "fraqueza_estrutural_de_peoes",
        "abertura_de_linhas_desfavoravel",
    ],
    "GESTAO_DE_TEMPO": [
        "gestao_de_tempo_ruim",
    ],
    "CALCULO": [
        "perda_de_iniciativa",
        "seguranca_do_rei",
        "negligencia_profilatica",
        "passividade_excessiva",
        "falta_de_coordenacao_de_pecas",
    ],
}


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do agente."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("agente2_analista")
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
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )
    return {name: value for name, value in required.items()}  # type: ignore[misc]


def fetch_diagnosticos(client: Client, logger: logging.Logger) -> list[dict[str, Any]]:
    """Busca todos os diagnósticos com dados do lance e da partida."""

    rows: list[dict[str, Any]] = []
    offset = 0
    select = (
        "*, lances_criticos(gravidade_cpl, numero_lance, "
        "partidas(data_partida, eco_abertura))"
    )
    while True:
        response = (
            client.table("diagnosticos")
            .select(select)
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        rows.extend(page)
        logger.info(
            "Página de diagnósticos carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def build_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Achata os diagnósticos aninhados em um DataFrame plano."""

    records: list[dict[str, Any]] = []
    for row in rows:
        lance = row.get("lances_criticos") or {}
        if isinstance(lance, list):
            lance = lance[0] if lance else {}
        partida = lance.get("partidas") or {}
        if isinstance(partida, list):
            partida = partida[0] if partida else {}
        tags = row.get("tags_falha") or []
        records.append(
            {
                "diagnostico_id": row.get("id"),
                "tags_falha": [tag for tag in tags if tag in TAGS_VOCABULARY],
                "gravidade_cpl": lance.get("gravidade_cpl"),
                "numero_lance": lance.get("numero_lance"),
                "data_partida": partida.get("data_partida"),
                "eco_abertura": partida.get("eco_abertura"),
            }
        )
    return pd.DataFrame(
        records,
        columns=[
            "diagnostico_id",
            "tags_falha",
            "gravidade_cpl",
            "numero_lance",
            "data_partida",
            "eco_abertura",
        ],
    )


def _to_native(value: Any) -> Any:
    """Converte tipos numpy/pandas para tipos nativos serializáveis."""

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def calcular_metricas_hexagono(df: pd.DataFrame) -> dict:
    """Calcula as métricas do hexágono usando apenas pandas."""

    total_diagnosticos = int(len(df))
    metrics: dict[str, Any] = {
        "total_diagnosticos": total_diagnosticos,
        "frequencia_tags_total": {tag: 0 for tag in TAGS_VOCABULARY},
        "frequencia_tags_recente": {tag: 0 for tag in TAGS_VOCABULARY},
        "gravidade_media_por_tag": {tag: None for tag in TAGS_VOCABULARY},
        "top_3_tags": [],
        "frequencia_tags_por_eco": {},
        "frequencia_por_categoria": {name: 0 for name in HEXAGON_CATEGORIES},
        "gravidade_media_por_categoria": {name: None for name in HEXAGON_CATEGORIES},
        "gargalo_sistemico_atual": None,
    }
    if total_diagnosticos == 0:
        return metrics

    exploded = df.explode("tags_falha").dropna(subset=["tags_falha"])
    exploded = exploded[exploded["tags_falha"].isin(TAGS_VOCABULARY)]
    exploded["gravidade_cpl"] = pd.to_numeric(
        exploded["gravidade_cpl"], errors="coerce"
    )

    total_counts = exploded["tags_falha"].value_counts()
    for tag, count in total_counts.items():
        metrics["frequencia_tags_total"][tag] = int(count)

    gravity_by_tag = exploded.groupby("tags_falha")["gravidade_cpl"].mean()
    for tag, gravity in gravity_by_tag.items():
        metrics["gravidade_media_por_tag"][tag] = _to_native(round(gravity, 2))

    parsed_dates = pd.to_datetime(
        exploded["data_partida"], errors="coerce", utc=True
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_WINDOW_DAYS)
    recent = exploded[parsed_dates >= cutoff]
    for tag, count in recent["tags_falha"].value_counts().items():
        metrics["frequencia_tags_recente"][tag] = int(count)

    metrics["top_3_tags"] = [
        {
            "tag": tag,
            "contagem": int(count),
            "gravidade_media": metrics["gravidade_media_por_tag"][tag],
        }
        for tag, count in total_counts.head(3).items()
    ]

    eco_df = exploded.dropna(subset=["eco_abertura"])
    for eco, group in eco_df.groupby("eco_abertura"):
        metrics["frequencia_tags_por_eco"][str(eco)] = {
            str(tag): int(count)
            for tag, count in group["tags_falha"].value_counts().items()
        }

    tag_to_category = {
        tag: category
        for category, tags in HEXAGON_CATEGORIES.items()
        for tag in tags
    }
    exploded["categoria"] = exploded["tags_falha"].map(tag_to_category)
    category_counts = exploded["categoria"].value_counts()
    category_gravity = exploded.groupby("categoria")["gravidade_cpl"].mean()
    for category in HEXAGON_CATEGORIES:
        metrics["frequencia_por_categoria"][category] = int(
            category_counts.get(category, 0)
        )
        if category in category_gravity and not pd.isna(category_gravity[category]):
            metrics["gravidade_media_por_categoria"][category] = _to_native(
                round(category_gravity[category], 2)
            )

    metrics["gargalo_sistemico_atual"] = _identify_bottleneck(metrics)
    return metrics


def _identify_bottleneck(metrics: dict[str, Any]) -> str | None:
    """Escolhe a categoria com pior combinação de frequência e gravidade."""

    eligible = {
        category: count
        for category, count in metrics["frequencia_por_categoria"].items()
        if count >= CATEGORY_MIN_DIAGNOSTICS
    }
    if not eligible:
        return None

    max_count = max(eligible.values())
    gravities = [
        metrics["gravidade_media_por_categoria"][category] or 0.0
        for category in eligible
    ]
    max_gravity = max(gravities) or 1.0

    best_category = None
    best_score = float("-inf")
    for category, count in eligible.items():
        gravity = metrics["gravidade_media_por_categoria"][category] or 0.0
        score = (count / max_count) + (gravity / max_gravity)
        if score > best_score:
            best_score = score
            best_category = category
    return best_category


def build_prompt(metrics: dict[str, Any]) -> str:
    """Monta um prompt curto com apenas os números já calculados."""

    resumo = {
        "total_diagnosticos": metrics["total_diagnosticos"],
        "top_3_tags": metrics["top_3_tags"],
        "frequencia_por_categoria": metrics["frequencia_por_categoria"],
        "gravidade_media_por_categoria": metrics["gravidade_media_por_categoria"],
        "gargalo_sistemico_atual": metrics["gargalo_sistemico_atual"],
    }
    return (
        "Você é um treinador de xadrez. Com base APENAS nos números abaixo "
        "(já calculados a partir dos diagnósticos), escreva de 2 a 3 parágrafos "
        "em linguagem natural explicando o que esses padrões significam para o "
        "jogador e onde ele deve focar seus estudos. Não invente dados além dos "
        "fornecidos.\n\n"
        f"{json.dumps(resumo, ensure_ascii=False, indent=2)}"
    )


def gerar_narrativa(client: Any, metrics: dict[str, Any]) -> str:
    """Chama o Gemini para narrar as métricas calculadas."""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=build_prompt(metrics),
    )
    return response.text or ""


def salvar_analise(
    client: Client, metrics: dict[str, Any], narrativa: str
) -> None:
    """Persiste as métricas e a narrativa na tabela analises_hexagono."""

    client.table("analises_hexagono").insert(
        {
            "metricas": metrics,
            "narrativa": narrativa,
            "gargalo_sistemico_atual": metrics["gargalo_sistemico_atual"],
        }
    ).execute()


def main() -> None:
    """Executa a análise agregada e imprime o resumo final."""

    logger = configure_logging()
    metrics: dict[str, Any] = {
        "total_diagnosticos": 0,
        "top_3_tags": [],
        "gargalo_sistemico_atual": None,
    }
    try:
        settings = load_settings()
        supabase_client = create_client(
            settings["SUPABASE_URL"], settings["SUPABASE_SERVICE_ROLE_KEY"]
        )
        rows = fetch_diagnosticos(supabase_client, logger)
        log_and_print(logger, f"Etapa 1/3: {len(rows)} diagnósticos carregados.")
        df = build_dataframe(rows)
        log_and_print(logger, "Etapa 2/3: iniciando cálculo de métricas...")
        metrics = calcular_metricas_hexagono(df)
        log_and_print(logger, "Etapa 2/3: cálculo de métricas concluído.")

        narrativa = ""
        try:
            log_and_print(logger, "Etapa 3/3: gerando narrativa via Gemini...")
            gemini_client = genai.Client(api_key=settings["GEMINI_API_KEY"])
            narrativa = gerar_narrativa(gemini_client, metrics)
            log_and_print(logger, "Etapa 3/3: narrativa gerada.")
        except Exception:
            logger.error("Falha ao gerar narrativa:\n%s", traceback.format_exc())

        try:
            salvar_analise(supabase_client, metrics, narrativa)
            log_and_print(logger, "Análise persistida em analises_hexagono.")
        except Exception:
            logger.error("Falha ao salvar análise:\n%s", traceback.format_exc())
    except Exception:
        logger.error("Falha geral na análise agregada:\n%s", traceback.format_exc())

    gargalo = metrics.get("gargalo_sistemico_atual") or "dados insuficientes"
    print(f"Diagnósticos analisados: {metrics.get('total_diagnosticos', 0)}")
    print(f"Gargalo sistêmico atual: {gargalo}")
    print("Top 3 tags mais frequentes:")
    for item in metrics.get("top_3_tags", []):
        print(f"  - {item['tag']}: {item['contagem']}")


if __name__ == "__main__":
    main()
