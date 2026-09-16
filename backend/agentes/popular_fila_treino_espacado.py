"""Popula a fila de repetição espaçada (D-48) com os lances críticos PICO já
diagnosticados de cada usuário, aguardando revisão.

Roda no pipeline diário, DEPOIS do agente1_linter.py (depende de
`diagnosticos` já existir). Sem chamada a LLM: a citação de livro é resolvida
uma única vez aqui via `buscar_conceitos()` (ILIKE puro sobre
`indice_conceitual`, `agente3_prescritor.py` — sem embedding, sem Gemini) e
cacheada na linha da fila, para o endpoint `POST /treino/{id}/responder` não
pagar esse custo a cada repetição.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.agente2_analista import HEXAGON_CATEGORIES  # noqa: E402
from backend.agentes.agente3_prescritor import buscar_conceitos  # noqa: E402
from backend.common.progress import configurar_encoding_utf8, log_and_print  # noqa: E402

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "popular_fila_treino_espacado.log"
PAGE_SIZE = 1000

# Quantos cards NOVOS entram "hoje" na fila de um usuário, por execução. Evita
# que o primeiro run despeje o backlog histórico inteiro de uma vez - o
# restante é escalonado nos dias seguintes (ver montar_linhas_novas). Mesmo
# padrão de configuração por env var de LIMITE_DIARIO_* em D-32.
TREINO_NOVOS_POR_DIA = int(os.getenv("TREINO_NOVOS_POR_DIA", "10"))

# tag_falha -> categoria do hexágono, invertendo HEXAGON_CATEGORIES.
TAG_PARA_CATEGORIA: dict[str, str] = {
    tag: categoria
    for categoria, tags in HEXAGON_CATEGORIES.items()
    for tag in tags
}

# Cache em memória (uma execução do script cobre vários usuários, e a mesma
# categoria tende a se repetir entre eles) - buscar_conceitos já é barato
# (ILIKE), mas não há motivo pra repetir a mesma busca várias vezes.
_CACHE_CITACAO: dict[str, dict[str, Any] | None] = {}


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do script."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("popular_fila_treino_espacado")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def load_settings() -> dict[str, str]:
    """Carrega e valida as configurações do ambiente."""

    load_dotenv(PROJECT_ROOT / ".env")
    required = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError("Variáveis de ambiente ausentes: " + ", ".join(sorted(missing)))
    return {name: value for name, value in required.items()}  # type: ignore[misc]


def listar_usuarios_com_diagnostico(client: Client) -> list[str]:
    """Lista, sem repetir, os donos que têm ao menos um diagnóstico gerado.

    Times a `partidas` via o embed (mesmo raciocínio de D-28 em
    `agente2_analista.listar_usuarios_com_partidas`): um usuário sem nenhum
    diagnóstico ainda não tem nada pra enfileirar.
    """

    response = (
        client.table("diagnosticos")
        .select("lances_criticos!inner(partidas!inner(user_id))")
        .execute()
    )
    usuarios: set[str] = set()
    for row in response.data or []:
        lance = row.get("lances_criticos") or {}
        if isinstance(lance, list):
            lance = lance[0] if lance else {}
        partida = lance.get("partidas") or {}
        if isinstance(partida, list):
            partida = partida[0] if partida else {}
        user_id = partida.get("user_id")
        if user_id:
            usuarios.add(user_id)
    return sorted(usuarios)


def buscar_diagnosticos_elegiveis(
    client: Client, logger: logging.Logger, user_id: str
) -> list[dict[str, Any]]:
    """Busca diagnósticos de lances PICO com posição registrada, de 1 usuário.

    Filtra `tipo_evento='PICO'` - EROSAO é uma janela de vários lances, sem um
    único "lance certo" bem definido pro formato de drill, fica fora do v1 -
    e `fen_antes_lance` não nulo - a coluna existe desde D-27, linhas mais
    antigas podem não ter sido reprocessadas e ficam sem posição pra mostrar.
    """

    rows: list[dict[str, Any]] = []
    offset = 0
    select = (
        "id, tags_falha, "
        "lances_criticos!inner(id, tipo_evento, fen_antes_lance, "
        "partidas!inner(user_id))"
    )
    while True:
        response = (
            client.table("diagnosticos")
            .select(select)
            .eq("lances_criticos.partidas.user_id", user_id)
            .eq("lances_criticos.tipo_evento", "PICO")
            .not_.is_("lances_criticos.fen_antes_lance", "null")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    logger.info(
        "Usuário %s: %d diagnóstico(s) elegível(is) (PICO, com posição).",
        user_id,
        len(rows),
    )
    return rows


def lances_ja_na_fila(client: Client, user_id: str) -> set[str]:
    """IDs de lances_criticos que este usuário já tem na fila (evita duplicar)."""

    response = (
        client.table("fila_treino_espacado")
        .select("lance_id")
        .eq("user_id", user_id)
        .execute()
    )
    return {row["lance_id"] for row in response.data or [] if row.get("lance_id")}


def resolver_citacao(client: Client, categoria: str | None) -> dict[str, Any] | None:
    """Resolve a 1ª citação de livro pra uma categoria, com cache em memória.

    Sem citação disponível (categoria sem conceito indexado) não é erro -
    devolve None e a linha da fila fica com os 3 campos de citação nulos.
    """

    if not categoria:
        return None
    if categoria in _CACHE_CITACAO:
        return _CACHE_CITACAO[categoria]

    conceitos = buscar_conceitos(client, categoria)
    citacao = conceitos[0] if conceitos else None
    _CACHE_CITACAO[categoria] = citacao
    return citacao


def montar_linhas_novas(
    diagnosticos: list[dict[str, Any]],
    ja_na_fila: set[str],
    client: Client,
    user_id: str,
    hoje: date,
) -> list[dict[str, Any]]:
    """Monta as linhas a inserir, escalonando no máximo TREINO_NOVOS_POR_DIA/dia.

    Os primeiros TREINO_NOVOS_POR_DIA candidatos (na ordem em que vieram do
    banco) entram pra hoje; o resto recebe proxima_revisao_data em dias
    seguintes, TREINO_NOVOS_POR_DIA por dia - evita que um backlog grande
    (ex: primeira execução, com meses de diagnósticos acumulados) vire uma
    fila de centenas de cards "vencidos" no mesmo dia.
    """

    candidatos: list[tuple[str, dict[str, Any]]] = []
    for diagnostico in diagnosticos:
        lance = diagnostico.get("lances_criticos") or {}
        if isinstance(lance, list):
            lance = lance[0] if lance else {}
        lance_id = lance.get("id")
        if not lance_id or lance_id in ja_na_fila:
            continue
        candidatos.append((lance_id, diagnostico))

    linhas: list[dict[str, Any]] = []
    for indice, (lance_id, diagnostico) in enumerate(candidatos):
        dias_de_espera = indice // TREINO_NOVOS_POR_DIA
        tags = diagnostico.get("tags_falha") or []
        categoria = TAG_PARA_CATEGORIA.get(tags[0]) if tags else None
        citacao = resolver_citacao(client, categoria)
        linhas.append(
            {
                "user_id": user_id,
                "lance_id": lance_id,
                "proxima_revisao_data": (hoje + timedelta(days=dias_de_espera)).isoformat(),
                "livro_citado": citacao.get("livro") if citacao else None,
                "capitulo_citado": citacao.get("capitulo") if citacao else None,
                "pagina_citada": citacao.get("pagina_aprox") if citacao else None,
            }
        )
    return linhas


def popular_para_usuario(
    client: Client, logger: logging.Logger, user_id: str, hoje: date
) -> int:
    """Popula a fila de um usuário; devolve quantas linhas novas foram inseridas."""

    diagnosticos = buscar_diagnosticos_elegiveis(client, logger, user_id)
    if not diagnosticos:
        return 0

    ja_na_fila = lances_ja_na_fila(client, user_id)
    linhas = montar_linhas_novas(diagnosticos, ja_na_fila, client, user_id, hoje)
    if not linhas:
        log_and_print(logger, f"Usuário {user_id}: fila já em dia, nada novo.")
        return 0

    client.table("fila_treino_espacado").upsert(
        linhas, on_conflict="user_id,lance_id"
    ).execute()
    log_and_print(
        logger, f"Usuário {user_id}: {len(linhas)} card(s) novo(s) enfileirado(s)."
    )
    return len(linhas)


def main() -> None:
    """Popula a fila de todos os usuários com diagnóstico disponível."""

    logger = configure_logging()
    hoje = date.today()
    total_inseridos = 0
    total_falhas = 0
    try:
        settings = load_settings()
        client = create_client(
            settings["SUPABASE_URL"], settings["SUPABASE_SERVICE_ROLE_KEY"]
        )
        usuarios = listar_usuarios_com_diagnostico(client)
        log_and_print(logger, f"{len(usuarios)} usuário(s) com diagnóstico disponível.")
        for user_id in usuarios:
            try:
                total_inseridos += popular_para_usuario(client, logger, user_id, hoje)
            except Exception:
                total_falhas += 1
                logger.error(
                    "Falha ao popular a fila do usuário %s:\n%s",
                    user_id,
                    traceback.format_exc(),
                )
    except Exception:
        total_falhas += 1
        logger.error(
            "Falha geral ao popular a fila de treino:\n%s", traceback.format_exc()
        )

    print(f"Cards novos enfileirados: {total_inseridos}")
    print(f"Falhas: {total_falhas}")


if __name__ == "__main__":
    main()
