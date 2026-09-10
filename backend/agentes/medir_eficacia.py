"""Mede a eficácia das sessões de treino concluídas."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.agente2_analista import HEXAGON_CATEGORIES  # noqa: E402
from backend.common.progress import configurar_encoding_utf8, log_and_print  # noqa: E402

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "medir_eficacia.log"
WINDOW_DAYS = 15
MIN_POST_DIAGNOSTICS = 3
PAGE_SIZE = 1000


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_service_role_key: str


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log da medição de eficácia."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("medir_eficacia")
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


def calcular_reducao_percentual(
    frequencia_antes: int, frequencia_depois: int
) -> float | None:
    """Calcula a redução percentual, ou None quando não há base anterior."""

    if frequencia_antes == 0:
        return None
    return ((frequencia_antes - frequencia_depois) / frequencia_antes) * 100


def extrair_categoria(diagnostico_gargalo: str) -> str:
    """Extrai e valida a categoria antes dos dois pontos."""

    categoria, separador, _ = diagnostico_gargalo.partition(":")
    categoria = categoria.strip().upper()
    if not separador or categoria not in HEXAGON_CATEGORIES:
        raise ValueError(
            f"Diagnóstico de gargalo em formato inválido: {diagnostico_gargalo!r}"
        )
    return categoria


def buscar_sessoes_elegiveis(client: Client) -> list[dict[str, Any]]:
    """Busca sessões concluídas que ainda não tiveram eficácia medida."""

    response = (
        client.table("sessoes_treino")
        .select("id, diagnostico_gargalo, data_concluida")
        .not_.is_("data_concluida", "null")
        .is_("eficacia_medida", "null")
        .order("data_concluida")
        .execute()
    )
    return response.data or []


def contar_diagnosticos_categoria(
    client: Client,
    categoria: str,
    inicio: datetime,
    fim: datetime,
) -> int:
    """Conta diagnósticos da categoria no intervalo temporal informado."""

    tags_categoria = set(HEXAGON_CATEGORIES[categoria])
    total = 0
    offset = 0
    select = (
        "id, tags_falha, "
        "lances_criticos!inner(partidas!inner(data_partida))"
    )

    while True:
        response = (
            client.table("diagnosticos")
            .select(select)
            .gte("lances_criticos.partidas.data_partida", inicio.isoformat())
            .lt("lances_criticos.partidas.data_partida", fim.isoformat())
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        total += sum(
            1
            for diagnostico in page
            if tags_categoria.intersection(diagnostico.get("tags_falha") or [])
        )
        if len(page) < PAGE_SIZE:
            return total
        offset += PAGE_SIZE


def montar_observacao(
    categoria: str,
    frequencia_antes: int,
    frequencia_depois: int,
    reducao: float,
) -> str:
    """Resume a variação observada depois do treino."""

    if frequencia_depois < frequencia_antes:
        movimento = "caiu"
    elif frequencia_depois > frequencia_antes:
        movimento = "subiu"
    else:
        movimento = "permaneceu"
    return (
        f"Frequência de {categoria} {movimento} de {frequencia_antes} para "
        f"{frequencia_depois} ocorrências ({reducao:.1f}% de redução) nas "
        f"partidas dos {WINDOW_DAYS} dias seguintes."
    )


def processar_sessao(
    client: Client, sessao: dict[str, Any], logger: logging.Logger
) -> bool:
    """Avalia uma sessão; retorna False quando ainda faltam dados."""

    sessao_id = sessao["id"]
    categoria = extrair_categoria(str(sessao.get("diagnostico_gargalo") or ""))
    data_concluida = datetime.fromisoformat(
        str(sessao["data_concluida"]).replace("Z", "+00:00")
    )
    inicio_antes = data_concluida - timedelta(days=WINDOW_DAYS)
    fim_depois = data_concluida + timedelta(days=WINDOW_DAYS)

    frequencia_antes = contar_diagnosticos_categoria(
        client, categoria, inicio_antes, data_concluida
    )
    frequencia_depois = contar_diagnosticos_categoria(
        client, categoria, data_concluida, fim_depois
    )

    if frequencia_depois < MIN_POST_DIAGNOSTICS:
        log_and_print(
            logger,
            f"Sessão {sessao_id} ({categoria}): aguardando mais dados "
            f"pós-treino ({frequencia_depois}/{MIN_POST_DIAGNOSTICS} diagnósticos).",
        )
        return False

    reducao = calcular_reducao_percentual(frequencia_antes, frequencia_depois)
    if reducao is None:
        log_and_print(
            logger,
            f"Sessão {sessao_id} ({categoria}): aguardando mais dados "
            "anteriores ao treino (frequência igual a zero).",
        )
        return False

    observacao = montar_observacao(
        categoria, frequencia_antes, frequencia_depois, reducao
    )
    (
        client.table("sessoes_treino")
        .update({"eficacia_medida": reducao, "observacoes": observacao})
        .eq("id", sessao_id)
        .execute()
    )
    log_and_print(
        logger,
        f"Sessão {sessao_id} ({categoria}) avaliada: "
        f"{frequencia_antes} antes, {frequencia_depois} depois, "
        f"redução de {reducao:.1f}%.",
    )
    return True


def run() -> None:
    """Executa a medição das sessões pendentes."""

    logger = configure_logging()
    settings = load_settings()
    client = create_client(
        settings.supabase_url, settings.supabase_service_role_key
    )
    sessoes = buscar_sessoes_elegiveis(client)

    if not sessoes:
        log_and_print(logger, "Nenhuma sessão pendente de avaliação.")
        return

    log_and_print(logger, f"Sessões elegíveis encontradas: {len(sessoes)}.")
    avaliadas = 0
    aguardando = 0
    falhas = 0

    for sessao in sessoes:
        try:
            if processar_sessao(client, sessao, logger):
                avaliadas += 1
            else:
                aguardando += 1
        except Exception as error:
            falhas += 1
            sessao_id = sessao.get("id", "desconhecida")
            logger.exception("Falha ao avaliar a sessão %s", sessao_id)
            log_and_print(
                logger, f"Sessão {sessao_id} falhou: {error}"
            )

    log_and_print(
        logger,
        "Resumo: "
        f"{avaliadas} avaliadas com sucesso, "
        f"{aguardando} aguardando mais dados, {falhas} falharam.",
    )


if __name__ == "__main__":
    run()