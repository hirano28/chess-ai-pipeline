"""Gera perguntas fixas para lances críticos ainda sem pensamento registrado."""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import format_progress, log_and_print  # noqa: E402

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "gerar_perguntas_pendentes.log"
PAGE_SIZE = 1000


@dataclass(frozen=True)
class Settings:
    """Configurações do Supabase."""

    supabase_url: str
    supabase_service_role_key: str


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do gerador de perguntas."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("gerar_perguntas_pendentes")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


def load_settings() -> Settings:
    """Carrega e valida as credenciais do Supabase."""

    load_dotenv(PROJECT_ROOT / ".env")
    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    missing = [
        name
        for name, value in {
            "SUPABASE_URL": supabase_url,
            "SUPABASE_SERVICE_ROLE_KEY": service_role_key,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )
    return Settings(
        supabase_url=supabase_url,  # type: ignore[arg-type]
        supabase_service_role_key=service_role_key,  # type: ignore[arg-type]
    )


def fetch_lances_criticos(client: Client, logger: logging.Logger) -> list[dict[str, Any]]:
    """Busca todos os lances críticos, em páginas."""

    lances: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            client.table("lances_criticos")
            .select("id, partida_id, numero_lance, numero_lance_fim, lance_notacao, tipo_evento")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        lances.extend(page)
        logger.info(
            "Página de lances críticos carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            return lances
        offset += PAGE_SIZE


def fetch_anotadas(client: Client, logger: logging.Logger) -> set[tuple[Any, int]]:
    """Busca o conjunto (partida_id, numero_lance) já anotado, em páginas."""

    anotadas: set[tuple[Any, int]] = set()
    offset = 0
    while True:
        response = (
            client.table("anotacoes_pensamento")
            .select("partida_id, numero_lance")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        anotadas.update((row["partida_id"], row["numero_lance"]) for row in page)
        logger.info(
            "Página de anotações carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            return anotadas
        offset += PAGE_SIZE


def fetch_partidas_com_anotacao(client: Client, logger: logging.Logger) -> set[Any]:
    """Busca o conjunto de partida_id com pelo menos 1 anotação, em páginas.

    Isso identifica partidas em "modo de revisão ativa": o jogador já voltou
    a essa partida para registrar pensamento em pelo menos um lance.
    """

    partidas_com_anotacao: set[Any] = set()
    offset = 0
    while True:
        response = (
            client.table("anotacoes_pensamento")
            .select("partida_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        partidas_com_anotacao.update(row["partida_id"] for row in page)
        logger.info(
            "Página de partidas com anotação carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            return partidas_com_anotacao
        offset += PAGE_SIZE


def fetch_lance_ids_com_pergunta(client: Client, logger: logging.Logger) -> set[Any]:
    """Busca o conjunto de lance_id que já possuem pergunta, em páginas."""

    lance_ids: set[Any] = set()
    offset = 0
    while True:
        response = (
            client.table("perguntas_pendentes")
            .select("lance_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        lance_ids.update(
            row["lance_id"] for row in page if row.get("lance_id") is not None
        )
        logger.info(
            "Página de perguntas pendentes carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            return lance_ids
        offset += PAGE_SIZE


def selecionar_elegiveis(
    lances: list[dict[str, Any]],
    anotadas: set[tuple[Any, int]],
    lance_ids_com_pergunta: set[Any],
    partidas_com_anotacao: set[Any],
) -> list[dict[str, Any]]:
    """Filtra lances sem anotação própria, sem pergunta já gerada, cuja partida
    já tenha pelo menos uma anotação de pensamento em outro lance.
    """

    return [
        lance
        for lance in lances
        if (lance["partida_id"], lance["numero_lance"]) not in anotadas
        and lance["id"] not in lance_ids_com_pergunta
        and lance["partida_id"] in partidas_com_anotacao
    ]


def gerar_pergunta(lance: dict[str, Any]) -> str:
    """Gera o texto fixo da pergunta, sem LLM, para nunca vazar dica do erro."""

    if str(lance.get("tipo_evento") or "PICO").upper() == "EROSAO":
        return (
            f"Entre os lances {lance.get('numero_lance')} e {lance.get('numero_lance_fim')}, "
            "você sentiu que tinha um plano claro? Em algum momento nesse trecho você ficou "
            "em dúvida sobre o que fazer?"
        )
    return (
        f"No lance {lance.get('numero_lance')} ({lance.get('lance_notacao')}), o que você "
        "estava pensando nesse momento? Quais alternativas você considerou e por que "
        "descartou as outras (se descartou alguma)?"
    )


def inserir_pergunta(client: Client, lance: dict[str, Any], pergunta_texto: str) -> None:
    """Insere a pergunta pendente vinculada ao lance."""

    client.table("perguntas_pendentes").insert(
        {
            "lance_id": lance["id"],
            "pergunta_texto": pergunta_texto,
            "status": "PENDENTE",
        }
    ).execute()


def run() -> None:
    """Executa a geração de perguntas pendentes."""

    logger = configure_logging()
    settings = load_settings()
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    lances = fetch_lances_criticos(client, logger)
    anotadas = fetch_anotadas(client, logger)
    lance_ids_com_pergunta = fetch_lance_ids_com_pergunta(client, logger)
    partidas_com_anotacao = fetch_partidas_com_anotacao(client, logger)
    elegiveis = selecionar_elegiveis(
        lances, anotadas, lance_ids_com_pergunta, partidas_com_anotacao
    )

    log_and_print(logger, f"Lances elegíveis para nova pergunta: {len(elegiveis)}.")

    geradas = 0
    puladas = len(lances) - len(elegiveis)
    start_time = time.time()
    for index, lance in enumerate(elegiveis, start=1):
        pergunta_texto = gerar_pergunta(lance)
        inserir_pergunta(client, lance, pergunta_texto)
        geradas += 1
        log_and_print(
            logger,
            format_progress(
                "Geração de perguntas", "lances", index, len(elegiveis), time.time() - start_time
            ),
        )

    log_and_print(
        logger,
        f"Resumo: {geradas} perguntas novas geradas, {puladas} lances pulados "
        "(já anotados, já com pergunta, ou de partidas ainda sem nenhuma "
        "anotação de pensamento).",
    )


if __name__ == "__main__":
    run()
