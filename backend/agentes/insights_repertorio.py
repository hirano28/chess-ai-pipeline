"""Agregações de repertório de abertura: leitura pura, sem Stockfish nem Gemini.

Tudo aqui é estatística simples sobre dado já persistido pelo resto do
pipeline: `partidas.abertura_normalizada` (ver `normalizar_aberturas.py` e
D-12 em `DECISOES.md`), `metricas_lichess_partida` (precisão por fase, D-12/
ver `enriquecer_partidas_lichess.py`), `lances_criticos` e `diagnosticos`.

Só `LICHESS` e `CHESSCOM` entram em qualquer agregação daqui. Partidas
`MANUAL` são PGN colado à mão no Analisador de Partida (qualquer partida,
não necessariamente do próprio jogador) e misturá-las distorceria "minha taxa
de vitória" e "meu repertório".

Limiar de amostra: agrupamentos com menos de `MIN_AMOSTRA` partidas ou eventos
viram ruído estatístico. Onde faz sentido (item 2, por abertura+cor) os grupos
pequenos são somados num bucket `"outras"` em vez de simplesmente descartados,
pra não perder partidas da contagem total. Onde não faz sentido somar (item 3,
lance de PICO; item 4, distribuição de categoria) o grupo abaixo do limiar é
só omitido do resultado.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Any

from supabase import Client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.agente2_analista import HEXAGON_CATEGORIES  # noqa: E402

PAGE_SIZE = 1000
MIN_AMOSTRA = 5
PLATAFORMAS_CONSIDERADAS = ("LICHESS", "CHESSCOM")
OUTRAS = "outras"

_TAG_PARA_CATEGORIA = {
    tag: categoria for categoria, tags in HEXAGON_CATEGORIES.items() for tag in tags
}


# ---------------------------------------------------------------------------
# Busca no Supabase (paginada, como o resto do pipeline)
# ---------------------------------------------------------------------------


def fetch_partidas_repertorio(client: Client) -> list[dict[str, Any]]:
    """Busca as partidas LICHESS/CHESSCOM usadas em toda agregação deste módulo."""

    partidas: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            client.table("partidas")
            .select("id, plataforma, cor_jogada, resultado, abertura_normalizada")
            .in_("plataforma", list(PLATAFORMAS_CONSIDERADAS))
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        partidas.extend(page)
        if len(page) < PAGE_SIZE:
            return partidas
        offset += PAGE_SIZE


def fetch_metricas_por_partida(client: Client) -> dict[str, dict[str, Any]]:
    """Indexa `metricas_lichess_partida` por `partida_id`."""

    metricas: dict[str, dict[str, Any]] = {}
    offset = 0
    while True:
        response = (
            client.table("metricas_lichess_partida")
            .select("partida_id, precisao_abertura, precisao_meiojogo, precisao_final")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        for row in page:
            metricas[row["partida_id"]] = row
        if len(page) < PAGE_SIZE:
            return metricas
        offset += PAGE_SIZE


def fetch_lances_pico(client: Client) -> list[dict[str, Any]]:
    """Busca todos os eventos `PICO` (`partida_id`, `numero_lance`)."""

    lances: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            client.table("lances_criticos")
            .select("partida_id, numero_lance")
            .eq("tipo_evento", "PICO")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        lances.extend(page)
        if len(page) < PAGE_SIZE:
            return lances
        offset += PAGE_SIZE


def fetch_diagnosticos_com_partida(client: Client) -> list[dict[str, Any]]:
    """Busca `tags_falha` de cada diagnóstico junto do `partida_id` do lance."""

    rows: list[dict[str, Any]] = []
    offset = 0
    select = "tags_falha, lances_criticos(partida_id)"
    while True:
        response = (
            client.table("diagnosticos")
            .select(select)
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


# ---------------------------------------------------------------------------
# Cálculo puro (testável com dados sintéticos, sem tocar o banco)
# ---------------------------------------------------------------------------


def _media(valores: list[Any]) -> float | None:
    """Média de uma lista que pode ter `None` misturado; `None` se vazia."""

    validos = [v for v in valores if v is not None]
    if not validos:
        return None
    return round(statistics.mean(validos), 2)


def calcular_taxa_vitoria_por_cor(
    partidas: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Total e % de vitória por `cor_jogada`, entre as partidas informadas."""

    contagem: dict[str, dict[str, int]] = {}
    for partida in partidas:
        cor = partida.get("cor_jogada")
        if not cor:
            continue
        bucket = contagem.setdefault(cor, {"total": 0, "vitorias": 0})
        bucket["total"] += 1
        if partida.get("resultado") == "VITORIA":
            bucket["vitorias"] += 1

    return {
        cor: {
            "total": dados["total"],
            "vitorias": dados["vitorias"],
            "taxa_vitoria_pct": round(dados["vitorias"] / dados["total"] * 100, 2),
        }
        for cor, dados in contagem.items()
    }


def calcular_metricas_por_abertura_e_cor(
    partidas: list[dict[str, Any]],
    metricas_por_partida: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Total, % de vitória e precisão média por (`abertura_normalizada`, `cor_jogada`).

    Combos com menos de `MIN_AMOSTRA` partidas são somados num bucket
    `"outras"` — por `cor_jogada`, pra não misturar taxa de vitória de brancas
    com a de pretas dentro do mesmo "outras".
    """

    grupos: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for partida in partidas:
        abertura = partida.get("abertura_normalizada")
        cor = partida.get("cor_jogada")
        if not abertura or not cor:
            continue
        grupos.setdefault((abertura, cor), []).append(partida)

    finais: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for (abertura, cor), lista in grupos.items():
        chave = (abertura, cor) if len(lista) >= MIN_AMOSTRA else (OUTRAS, cor)
        finais.setdefault(chave, []).extend(lista)

    resultado: list[dict[str, Any]] = []
    for (abertura, cor), lista in finais.items():
        total = len(lista)
        vitorias = sum(1 for p in lista if p.get("resultado") == "VITORIA")
        resultado.append(
            {
                "abertura_normalizada": abertura,
                "cor_jogada": cor,
                "total": total,
                "vitorias": vitorias,
                "taxa_vitoria_pct": round(vitorias / total * 100, 2),
                "precisao_media_abertura": _media(
                    [metricas_por_partida.get(p["id"], {}).get("precisao_abertura") for p in lista]
                ),
                "precisao_media_meiojogo": _media(
                    [metricas_por_partida.get(p["id"], {}).get("precisao_meiojogo") for p in lista]
                ),
                "precisao_media_final": _media(
                    [metricas_por_partida.get(p["id"], {}).get("precisao_final") for p in lista]
                ),
            }
        )

    resultado.sort(
        key=lambda item: (-item["total"], item["abertura_normalizada"], item["cor_jogada"])
    )
    return resultado


def calcular_lance_medio_pico_por_abertura(
    partidas: list[dict[str, Any]],
    lances_pico: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Lance médio/mediano de eventos `PICO` por abertura, com >= `MIN_AMOSTRA` eventos."""

    abertura_por_partida = {
        p["id"]: p.get("abertura_normalizada") for p in partidas if p.get("abertura_normalizada")
    }

    lances_por_abertura: dict[str, list[int]] = {}
    for lance in lances_pico:
        abertura = abertura_por_partida.get(lance.get("partida_id"))
        numero_lance = lance.get("numero_lance")
        if abertura is None or numero_lance is None:
            continue
        lances_por_abertura.setdefault(abertura, []).append(numero_lance)

    resultado = [
        {
            "abertura_normalizada": abertura,
            "total_eventos": len(numeros),
            "lance_medio": round(statistics.mean(numeros), 2),
            "lance_mediano": statistics.median(numeros),
        }
        for abertura, numeros in lances_por_abertura.items()
        if len(numeros) >= MIN_AMOSTRA
    ]
    resultado.sort(key=lambda item: -item["total_eventos"])
    return resultado


def calcular_categorias_por_abertura(
    partidas: list[dict[str, Any]],
    diagnosticos: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    """Distribuição das categorias do hexágono entre os diagnósticos de cada abertura.

    Reaproveita `HEXAGON_CATEGORIES` de `agente2_analista.py` — mesmo
    vocabulário e mesmo mapeamento tag → categoria usados no resto do pipeline,
    sem duplicar a fonte de verdade. Abertura com menos de `MIN_AMOSTRA`
    diagnósticos no total fica de fora, mesmo motivo dos outros dois limiares.
    """

    abertura_por_partida = {
        p["id"]: p.get("abertura_normalizada") for p in partidas if p.get("abertura_normalizada")
    }

    contagem: dict[str, dict[str, int]] = {}
    total_diagnosticos_por_abertura: dict[str, int] = {}
    for diagnostico in diagnosticos:
        lance = diagnostico.get("lances_criticos") or {}
        if isinstance(lance, list):
            lance = lance[0] if lance else {}
        abertura = abertura_por_partida.get(lance.get("partida_id"))
        if abertura is None:
            continue
        # Conta o diagnóstico na amostra mesmo se nenhuma tag dele mapear pra
        # categoria conhecida — o limiar mede "quantos diagnósticos temos
        # dessa abertura", não "quantos incrementos válidos".
        total_diagnosticos_por_abertura[abertura] = (
            total_diagnosticos_por_abertura.get(abertura, 0) + 1
        )
        bucket = contagem.setdefault(abertura, {nome: 0 for nome in HEXAGON_CATEGORIES})
        for tag in diagnostico.get("tags_falha") or []:
            categoria = _TAG_PARA_CATEGORIA.get(tag)
            if categoria is not None:
                bucket[categoria] += 1

    return {
        abertura: bucket
        for abertura, bucket in contagem.items()
        if total_diagnosticos_por_abertura[abertura] >= MIN_AMOSTRA
    }


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------


def calcular_insights_repertorio(client: Client) -> dict[str, Any]:
    """Busca tudo que essas 4 agregações precisam e monta o payload completo."""

    partidas = fetch_partidas_repertorio(client)
    metricas_por_partida = fetch_metricas_por_partida(client)
    lances_pico = fetch_lances_pico(client)
    diagnosticos = fetch_diagnosticos_com_partida(client)

    return {
        "taxa_vitoria_por_cor": calcular_taxa_vitoria_por_cor(partidas),
        "por_abertura_e_cor": calcular_metricas_por_abertura_e_cor(
            partidas, metricas_por_partida
        ),
        "lance_pico_por_abertura": calcular_lance_medio_pico_por_abertura(
            partidas, lances_pico
        ),
        "categorias_por_abertura": calcular_categorias_por_abertura(partidas, diagnosticos),
    }
