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
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import configurar_encoding_utf8, log_and_print  # noqa: E402
from backend.common.settings import carregar_variaveis_obrigatorias  # noqa: E402

configurar_encoding_utf8()

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

    return carregar_variaveis_obrigatorias(
        PROJECT_ROOT, "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY"
    )


def listar_usuarios_com_partidas(client: Client) -> list[str]:
    """Lista, sem repetir, os donos que têm ao menos uma partida cadastrada.

    Fonte de "quem tem hexágono pra calcular" (D-28): times a `partidas`, não
    a `perfis_usuario`, porque um perfil recém-cadastrado sem partida
    ingerida ainda não tem diagnóstico nenhum pra analisar.
    """

    response = client.table("partidas").select("user_id").execute()
    return sorted({row["user_id"] for row in response.data or [] if row.get("user_id")})


def fetch_diagnosticos(
    client: Client, logger: logging.Logger, user_id: str
) -> list[dict[str, Any]]:
    """Busca os diagnósticos de `user_id`, com dados do lance e da partida.

    `!inner` nos dois embeds (D-28) transforma o embed num join de verdade,
    o que permite filtrar a tabela de fora (`diagnosticos`) pela coluna
    aninhada `lances_criticos.partidas.user_id` - sem isso, o `.eq` só
    filtraria o que aparece dentro do embed, não as linhas retornadas.
    """

    rows: list[dict[str, Any]] = []
    offset = 0
    # `partida_id` e `cadencia` entraram no D-63: o primeiro para contar
    # partidas distintas (o hexágono é de diagnósticos, e "N diagnósticos em M
    # partidas" é o que dá escala ao número), o segundo para o recorte.
    select = (
        "*, lances_criticos!inner(queda_win_percent, numero_lance, partida_id, "
        "partidas!inner(data_partida, eco_abertura, user_id, cadencia))"
    )
    while True:
        response = (
            client.table("diagnosticos")
            .select(select)
            .eq("lances_criticos.partidas.user_id", user_id)
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
                "queda_win_percent": lance.get("queda_win_percent"),
                "numero_lance": lance.get("numero_lance"),
                "partida_id": lance.get("partida_id"),
                "data_partida": partida.get("data_partida"),
                "eco_abertura": partida.get("eco_abertura"),
                "cadencia": partida.get("cadencia"),
            }
        )
    return pd.DataFrame(
        records,
        columns=[
            "diagnostico_id",
            "tags_falha",
            "queda_win_percent",
            "numero_lance",
            "partida_id",
            "data_partida",
            "eco_abertura",
            "cadencia",
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
        "frequencia_por_categoria_recente": {name: 0 for name in HEXAGON_CATEGORIES},
        "gravidade_media_por_categoria_recente": {name: None for name in HEXAGON_CATEGORIES},
        "gargalo_sistemico_atual": None,
    }
    if total_diagnosticos == 0:
        return metrics

    exploded = df.explode("tags_falha").dropna(subset=["tags_falha"])
    exploded = exploded[exploded["tags_falha"].isin(TAGS_VOCABULARY)]
    exploded["queda_win_percent"] = pd.to_numeric(
        exploded["queda_win_percent"], errors="coerce"
    )

    # --- Métricas cumulativas (todo o histórico — alimentam o radar) ---
    total_counts = exploded["tags_falha"].value_counts()
    for tag, count in total_counts.items():
        metrics["frequencia_tags_total"][tag] = int(count)

    gravity_by_tag = exploded.groupby("tags_falha")["queda_win_percent"].mean()
    for tag, gravity in gravity_by_tag.items():
        metrics["gravidade_media_por_tag"][tag] = _to_native(round(gravity, 2))

    tag_to_category = {
        tag: category
        for category, tags in HEXAGON_CATEGORIES.items()
        for tag in tags
    }
    exploded["categoria"] = exploded["tags_falha"].map(tag_to_category)
    category_counts = exploded["categoria"].value_counts()
    category_gravity = exploded.groupby("categoria")["queda_win_percent"].mean()
    for category in HEXAGON_CATEGORIES:
        metrics["frequencia_por_categoria"][category] = int(
            category_counts.get(category, 0)
        )
        if category in category_gravity and not pd.isna(category_gravity[category]):
            metrics["gravidade_media_por_categoria"][category] = _to_native(
                round(category_gravity[category], 2)
            )

    # --- Métricas recentes (últimos RECENT_WINDOW_DAYS dias — decidem o gargalo) ---
    parsed_dates = pd.to_datetime(
        exploded["data_partida"], errors="coerce", utc=True
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_WINDOW_DAYS)
    recent = exploded[parsed_dates >= cutoff]

    recent_tag_counts = recent["tags_falha"].value_counts()
    for tag, count in recent_tag_counts.items():
        metrics["frequencia_tags_recente"][tag] = int(count)

    recent_cat_counts = recent["categoria"].value_counts()
    recent_cat_gravity = recent.groupby("categoria")["queda_win_percent"].mean()
    for category in HEXAGON_CATEGORIES:
        metrics["frequencia_por_categoria_recente"][category] = int(
            recent_cat_counts.get(category, 0)
        )
        if category in recent_cat_gravity and not pd.isna(recent_cat_gravity[category]):
            metrics["gravidade_media_por_categoria_recente"][category] = _to_native(
                round(recent_cat_gravity[category], 2)
            )

    # --- Top 3 tags: usa contagens RECENTES para refletir o estado atual ---
    metrics["top_3_tags"] = [
        {
            "tag": tag,
            "contagem": int(count),
            "gravidade_media": metrics["gravidade_media_por_tag"].get(tag),
        }
        for tag, count in recent_tag_counts.head(3).items()
    ]

    # --- Frequência por ECO (cumulativa, uso informativo) ---
    eco_df = exploded.dropna(subset=["eco_abertura"])
    for eco, group in eco_df.groupby("eco_abertura"):
        metrics["frequencia_tags_por_eco"][str(eco)] = {
            str(tag): int(count)
            for tag, count in group["tags_falha"].value_counts().items()
        }

    # --- Gargalo: usa métricas RECENTES ---
    metrics["gargalo_sistemico_atual"] = _identify_bottleneck(metrics)
    return metrics


# Mínimo de partidas distintas para uma cadência ganhar o próprio recorte
# (D-63). Uma ou duas partidas não sustentam hexágono nenhum, e um chip
# "Cadência desconhecida · 1 partida" no seletor da tela seria ruído permanente
# para quem colou um único PGN à mão.
CADENCIA_MIN_PARTIDAS = 3


def _contar_partidas(df: pd.DataFrame) -> int:
    """Partidas distintas por trás dos diagnósticos do DataFrame."""

    if "partida_id" not in df.columns:
        return 0
    return int(df["partida_id"].dropna().nunique())


def calcular_metricas_por_cadencia(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Um hexágono completo para cada cadência presente nos diagnósticos (D-63).

    Por que isto existe: 72% das partidas do dono principal são blitz, e o
    hexágono somado dizia "seu gargalo é tática" sem conseguir separar "calcula
    mal" de "joga rápido demais". O D-57 pôs a ressalva na tela; este recorte é
    o que permite ao usuário RESPONDER à ressalva, olhando o hexágono só das
    rápidas ou só das blitz.

    Cada bloco tem exatamente o shape de `calcular_metricas_hexagono()`, de
    propósito: a tela reaproveita o mesmo código de render para o total e para
    qualquer recorte. Só `frequencia_tags_por_eco` sai — é informativo, pesa no
    jsonb e ninguém lê por cadência. Diagnóstico sem cadência conta no total e
    em bloco nenhum, e cadência com menos de `CADENCIA_MIN_PARTIDAS` partidas
    não ganha bloco.
    """

    if df.empty or "cadencia" not in df.columns:
        return {}

    por_cadencia: dict[str, dict[str, Any]] = {}
    for cadencia, grupo in df.dropna(subset=["cadencia"]).groupby("cadencia"):
        partidas = _contar_partidas(grupo)
        if partidas < CADENCIA_MIN_PARTIDAS:
            continue
        bloco = calcular_metricas_hexagono(grupo.reset_index(drop=True))
        bloco.pop("frequencia_tags_por_eco", None)
        bloco["partidas_distintas"] = partidas
        por_cadencia[str(cadencia)] = bloco
    return por_cadencia


def calcular_metricas_completas(df: pd.DataFrame) -> dict[str, Any]:
    """Hexágono do total mais o recorte por cadência, no mesmo dicionário.

    O gargalo de primeiro nível continua sendo o de TODAS as partidas: é ele
    que o Agente 3 lê para prescrever e que `medir_eficacia.py` acompanha, e
    mudar isso é decisão de produto (treinar para qual cadência?), não de
    cálculo — ver D-63. O recorte informa; ainda não prescreve.
    """

    metrics = calcular_metricas_hexagono(df)
    metrics["partidas_distintas"] = _contar_partidas(df)
    metrics["por_cadencia"] = calcular_metricas_por_cadencia(df)
    return metrics


def _identify_bottleneck(metrics: dict[str, Any]) -> str | None:
    """Escolhe a categoria com pior combinação de frequência e gravidade recentes."""

    eligible = {
        category: count
        for category, count in metrics["frequencia_por_categoria_recente"].items()
        if count >= CATEGORY_MIN_DIAGNOSTICS
    }
    if not eligible:
        return None

    max_count = max(eligible.values())
    gravities = [
        metrics["gravidade_media_por_categoria_recente"][category] or 0.0
        for category in eligible
    ]
    max_gravity = max(gravities) or 1.0

    best_category = None
    best_score = float("-inf")
    for category, count in eligible.items():
        gravity = metrics["gravidade_media_por_categoria_recente"][category] or 0.0
        score = (count / max_count) + (gravity / max_gravity)
        if score > best_score:
            best_score = score
            best_category = category
    return best_category


def build_prompt(metrics: dict[str, Any]) -> str:
    """Monta um prompt curto com apenas os números já calculados."""

    por_cadencia = metrics.get("por_cadencia") or {}
    resumo = {
        "total_diagnosticos": metrics["total_diagnosticos"],
        "partidas_distintas": metrics.get("partidas_distintas"),
        "top_3_tags_recentes": metrics["top_3_tags"],
        "frequencia_por_categoria_total": metrics["frequencia_por_categoria"],
        "frequencia_por_categoria_recente": metrics["frequencia_por_categoria_recente"],
        "gravidade_media_por_categoria_recente": metrics["gravidade_media_por_categoria_recente"],
        "gargalo_sistemico_atual": metrics["gargalo_sistemico_atual"],
        # D-63: o único dado novo que o narrador recebe. Deixar o modelo ver os
        # gargalos lado a lado é o que permite a frase que mais vale para o
        # jogador ("em rápidas o seu problema é outro").
        "gargalo_por_cadencia": {
            cadencia: bloco.get("gargalo_sistemico_atual")
            for cadencia, bloco in por_cadencia.items()
        },
        "partidas_por_cadencia": {
            cadencia: bloco.get("partidas_distintas")
            for cadencia, bloco in por_cadencia.items()
        },
        "janela_recente_dias": RECENT_WINDOW_DAYS,
    }
    return (
        "Você é um treinador de xadrez. Com base APENAS nos números abaixo "
        "(já calculados a partir dos diagnósticos), escreva de 2 a 3 parágrafos "
        "em linguagem natural explicando o que esses padrões significam para o "
        "jogador e onde ele deve focar seus estudos. Compare a situação recente "
        f"(últimos {RECENT_WINDOW_DAYS} dias) com o acumulado geral para "
        "identificar se houve evolução ou regressão. Se o gargalo mudar de uma "
        "cadência para outra em `gargalo_por_cadencia`, diga isso "
        "explicitamente: é a informação mais útil para o jogador, porque separa "
        "erro de entendimento de erro sob pressão de relógio. Se for igual em "
        "todas, não force uma diferença. Não invente dados além dos "
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
    client: Client, metrics: dict[str, Any], narrativa: str, user_id: str
) -> None:
    """Persiste as métricas e a narrativa na tabela analises_hexagono."""

    client.table("analises_hexagono").insert(
        {
            "metricas": metrics,
            "narrativa": narrativa,
            "gargalo_sistemico_atual": metrics["gargalo_sistemico_atual"],
            "user_id": user_id,
        }
    ).execute()


def analisar_usuario(
    client: Client,
    gemini_client: Any,
    logger: logging.Logger,
    user_id: str,
) -> dict[str, Any]:
    """Roda as 3 etapas da análise para um único usuário e persiste o resultado."""

    rows = fetch_diagnosticos(client, logger, user_id)
    log_and_print(
        logger, f"Usuário {user_id}: {len(rows)} diagnósticos carregados."
    )
    df = build_dataframe(rows)
    metrics = calcular_metricas_completas(df)
    if metrics["total_diagnosticos"] == 0:
        log_and_print(
            logger, f"Usuário {user_id}: sem diagnósticos ainda; análise pulada."
        )
        return metrics

    narrativa = ""
    try:
        narrativa = gerar_narrativa(gemini_client, metrics)
    except Exception:
        logger.error(
            "Falha ao gerar narrativa do usuário %s:\n%s",
            user_id,
            traceback.format_exc(),
        )

    salvar_analise(client, metrics, narrativa, user_id)
    log_and_print(logger, f"Usuário {user_id}: análise persistida em analises_hexagono.")
    return metrics


def main() -> None:
    """Executa a análise agregada de cada usuário e imprime o resumo final."""

    logger = configure_logging()
    resultados_por_usuario: dict[str, dict[str, Any]] = {}
    try:
        settings = load_settings()
        supabase_client = create_client(
            settings["SUPABASE_URL"], settings["SUPABASE_SERVICE_ROLE_KEY"]
        )
        gemini_client = genai.Client(api_key=settings["GEMINI_API_KEY"])

        usuarios = listar_usuarios_com_partidas(supabase_client)
        log_and_print(logger, f"Etapa 1/2: {len(usuarios)} usuário(s) com partidas.")
        for user_id in usuarios:
            try:
                resultados_por_usuario[user_id] = analisar_usuario(
                    supabase_client, gemini_client, logger, user_id
                )
            except Exception:
                logger.error(
                    "Falha ao analisar o usuário %s:\n%s",
                    user_id,
                    traceback.format_exc(),
                )
        log_and_print(logger, "Etapa 2/2: análise de todos os usuários concluída.")
    except Exception:
        logger.error("Falha geral na análise agregada:\n%s", traceback.format_exc())

    print(f"Usuários analisados: {len(resultados_por_usuario)}")
    for user_id, metrics in resultados_por_usuario.items():
        gargalo = metrics.get("gargalo_sistemico_atual") or "dados insuficientes"
        print(f"- {user_id}: {metrics.get('total_diagnosticos', 0)} diagnósticos, gargalo {gargalo}")


if __name__ == "__main__":
    main()
