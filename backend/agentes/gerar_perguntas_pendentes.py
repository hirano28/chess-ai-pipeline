"""Gera perguntas fixas para lances críticos ainda sem pensamento registrado."""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import (  # noqa: E402
    configurar_encoding_utf8,
    format_progress,
    log_and_print,
)
from backend.common.settings import carregar_variaveis_obrigatorias  # noqa: E402

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "gerar_perguntas_pendentes.log"
PAGE_SIZE = 1000

# Por quantos dias após a partida uma pergunta faz sentido (D-64).
#
# A pergunta é sempre a mesma: "no lance 16, o que você estava pensando?".
# Ela só tem resposta enquanto o jogador ainda lembra do momento. Medido em
# 17/09/2026: 6 perguntas pendentes, **todas de partidas de 10 dias atrás**,
# **nenhuma respondida desde que a funcionalidade existe** — e permanentes no
# topo do dashboard, acima do próprio diagnóstico.
#
# Uma pergunta que não tem mais resposta possível não é uma tarefa pendente, é
# entulho que finge ser tarefa. A régua é a data da PARTIDA, não a da pergunta:
# perguntar hoje sobre um jogo de três meses atrás nasce morto do mesmo jeito.
# Por isso o mesmo número governa as duas pontas — não gerar, e expirar.
PERGUNTA_VALIDADE_DIAS = int(os.getenv("PERGUNTA_VALIDADE_DIAS", "14"))

STATUS_PENDENTE = "PENDENTE"
STATUS_EXPIRADA = "EXPIRADA"


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

    required = carregar_variaveis_obrigatorias(
        PROJECT_ROOT, "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"
    )
    return Settings(
        supabase_url=required["SUPABASE_URL"],
        supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],
    )


def fetch_lances_criticos(client: Client, logger: logging.Logger) -> list[dict[str, Any]]:
    """Busca todos os lances críticos, em páginas."""

    lances: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            client.table("lances_criticos")
            .select(
                "id, partida_id, numero_lance, numero_lance_fim, lance_notacao, "
                # `data_partida` entrou no D-64: é ela que diz se ainda dá para
                # lembrar do lance, e portanto se a pergunta vale a pena.
                "tipo_evento, partidas!inner(data_partida)"
            )
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


def data_da_partida(linha: dict[str, Any]) -> date | None:
    """Extrai a data da partida de uma linha com o embed `partidas`.

    Devolve None quando o embed não veio ou a data é ilegível — e quem chama
    trata isso como "não sei a idade", deixando a pergunta passar. Sumir com
    uma pergunta por causa de um campo que não conseguimos ler seria pior que
    deixar uma pergunta velha na tela.
    """

    partida = linha.get("partidas") or {}
    if isinstance(partida, list):
        partida = partida[0] if partida else {}
    bruta = partida.get("data_partida")
    if not bruta:
        return None
    try:
        return datetime.fromisoformat(str(bruta).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def dentro_da_validade(
    linha: dict[str, Any], hoje: date, validade_dias: int = PERGUNTA_VALIDADE_DIAS
) -> bool:
    """True se a partida é recente o bastante para a pergunta ter resposta."""

    data = data_da_partida(linha)
    if data is None:
        return True
    return (hoje - data).days <= validade_dias


def selecionar_elegiveis(
    lances: list[dict[str, Any]],
    anotadas: set[tuple[Any, int]],
    lance_ids_com_pergunta: set[Any],
    partidas_com_anotacao: set[Any],
    hoje: date | None = None,
    validade_dias: int = PERGUNTA_VALIDADE_DIAS,
) -> list[dict[str, Any]]:
    """Filtra lances sem anotação própria, sem pergunta já gerada, cuja partida
    já tenha pelo menos uma anotação de pensamento em outro lance — e que ainda
    esteja dentro da janela de memória (D-64).
    """

    referencia = hoje or datetime.now(timezone.utc).date()
    return [
        lance
        for lance in lances
        if (lance["partida_id"], lance["numero_lance"]) not in anotadas
        and lance["id"] not in lance_ids_com_pergunta
        and lance["partida_id"] in partidas_com_anotacao
        and dentro_da_validade(lance, referencia, validade_dias)
    ]


def expirar_perguntas_vencidas(
    client: Client,
    logger: logging.Logger,
    hoje: date | None = None,
    validade_dias: int = PERGUNTA_VALIDADE_DIAS,
) -> int:
    """Marca como EXPIRADA toda pergunta PENDENTE de partida velha demais.

    Não apaga: `EXPIRADA` preserva o registro de que a pergunta existiu e não
    foi respondida, que é justamente o dado interessante sobre a
    funcionalidade. A tela lista só as PENDENTES, então elas somem de lá.
    """

    referencia = hoje or datetime.now(timezone.utc).date()
    resposta = (
        client.table("perguntas_pendentes")
        .select("id, lances_criticos!inner(partidas!inner(data_partida))")
        .eq("status", STATUS_PENDENTE)
        .execute()
    )

    vencidas: list[Any] = []
    for linha in resposta.data or []:
        lance = linha.get("lances_criticos") or {}
        if isinstance(lance, list):
            lance = lance[0] if lance else {}
        if not dentro_da_validade(lance, referencia, validade_dias):
            vencidas.append(linha["id"])

    if not vencidas:
        return 0

    client.table("perguntas_pendentes").update({"status": STATUS_EXPIRADA}).in_(
        "id", vencidas
    ).execute()
    log_and_print(
        logger,
        f"{len(vencidas)} pergunta(s) expirada(s): a partida tem mais de "
        f"{validade_dias} dias e o jogador não teria como lembrar do lance.",
    )
    return len(vencidas)


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

    hoje = datetime.now(timezone.utc).date()
    expiradas = expirar_perguntas_vencidas(client, logger, hoje)

    lances = fetch_lances_criticos(client, logger)
    anotadas = fetch_anotadas(client, logger)
    lance_ids_com_pergunta = fetch_lance_ids_com_pergunta(client, logger)
    partidas_com_anotacao = fetch_partidas_com_anotacao(client, logger)
    elegiveis = selecionar_elegiveis(
        lances, anotadas, lance_ids_com_pergunta, partidas_com_anotacao, hoje
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
        f"Resumo: {geradas} perguntas novas geradas, {expiradas} expiradas, "
        f"{puladas} lances pulados (já anotados, já com pergunta, de partidas "
        "ainda sem nenhuma anotação de pensamento, ou de partida antiga demais "
        f"para lembrar — mais de {PERGUNTA_VALIDADE_DIAS} dias).",
    )


if __name__ == "__main__":
    run()
