"""Importa o histórico de atividade de puzzles do Lichess.

Cada linha do NDJSON de /api/puzzle/activity já traz o objeto `puzzle`
completo (id, rating, themes) - não é necessário cruzar com o dump público
de puzzles do Lichess.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import format_progress, log_and_print  # noqa: E402
from backend.ingestao.common_ingestao import configure_logging, with_retry  # noqa: E402

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "importar_puzzle_activity.log"
PUZZLE_ACTIVITY_URL = "https://lichess.org/api/puzzle/activity"
INSPECIONAR_MAX_LINHAS = 20
TOP_TEMAS = 5


@dataclass(frozen=True)
class Settings:
    """Configurações do Supabase e do token de puzzle do Lichess."""

    supabase_url: str
    supabase_service_role_key: str
    lichess_study_token: str


def load_settings() -> Settings:
    """Carrega e valida as configurações do ambiente."""

    load_dotenv(PROJECT_ROOT / ".env")
    required = {
        "LICHESS_STUDY_TOKEN": os.getenv("LICHESS_STUDY_TOKEN"),
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )
    return Settings(
        supabase_url=required["SUPABASE_URL"],  # type: ignore[arg-type]
        supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],  # type: ignore[arg-type]
        lichess_study_token=required["LICHESS_STUDY_TOKEN"],  # type: ignore[arg-type]
    )


def fetch_puzzle_activity_lines(
    settings: Settings, logger: logging.Logger, max_lines: int | None = None
) -> list[bytes]:
    """Chama /api/puzzle/activity e retorna as linhas NDJSON brutas (bytes)."""

    headers = {
        "Authorization": f"Bearer {settings.lichess_study_token}",
        "Accept": "application/x-ndjson",
    }

    def request() -> list[bytes]:
        linhas: list[bytes] = []
        with requests.get(
            PUZZLE_ACTIVITY_URL, headers=headers, timeout=30, stream=True
        ) as response:
            response.raise_for_status()
            for linha in response.iter_lines():
                if not linha:
                    continue
                linhas.append(linha)
                if max_lines is not None and len(linhas) >= max_lines:
                    break
        return linhas

    return with_retry(request, logger, "Busca do histórico de atividade de puzzles")


def inspecionar() -> None:
    """Busca uma amostra real e imprime o NDJSON bruto (Etapa 1)."""

    logger = configure_logging(LOG_PATH, "importar_puzzle_activity")
    settings = load_settings()
    linhas = fetch_puzzle_activity_lines(
        settings, logger, max_lines=INSPECIONAR_MAX_LINHAS
    )
    print(f"Total de linhas recebidas: {len(linhas)}\n")
    for linha in linhas:
        print(linha.decode("utf-8"))


def parse_puzzle_activity_line(linha: bytes) -> dict[str, Any]:
    """Decodifica uma linha NDJSON e monta o registro de puzzle_atividade."""

    dados = json.loads(linha.decode("utf-8"))
    puzzle = dados["puzzle"]
    data_iso = datetime.fromtimestamp(
        dados["date"] / 1000, tz=timezone.utc
    ).isoformat()
    return {
        "puzzle_id": puzzle["id"],
        "data": data_iso,
        "acertou": bool(dados["win"]),
        "temas": puzzle.get("themes") or [],
        "rating_puzzle": puzzle.get("rating"),
    }


def upsert_puzzle_atividade(client: Client, registro: dict[str, Any]) -> None:
    """Faz upsert de um registro em puzzle_atividade, sem duplicar."""

    client.table("puzzle_atividade").upsert(
        registro, on_conflict="puzzle_id,data"
    ).execute()


def imprimir_resumo(
    logger: logging.Logger,
    registros_importados: list[dict[str, Any]],
    falhas_parsing: int,
    falhas_upsert: int,
) -> None:
    """Calcula e imprime o resumo final: total, taxa geral e por tema."""

    total = len(registros_importados)
    acertos = sum(1 for registro in registros_importados if registro["acertou"])
    taxa_geral = (acertos / total * 100) if total else 0.0

    contagem_temas: Counter[str] = Counter()
    acertos_por_tema: Counter[str] = Counter()
    for registro in registros_importados:
        for tema in registro["temas"]:
            contagem_temas[tema] += 1
            if registro["acertou"]:
                acertos_por_tema[tema] += 1

    log_and_print(
        logger,
        f"Resumo: {total} puzzles importados, {falhas_parsing} falhas de parsing, "
        f"{falhas_upsert} falhas ao gravar. Taxa de acerto geral: {taxa_geral:.1f}%.",
    )

    print(f"\nTop {TOP_TEMAS} temas mais frequentes:")
    for tema, quantidade in contagem_temas.most_common(TOP_TEMAS):
        taxa_tema = acertos_por_tema[tema] / quantidade * 100
        print(f"  - {tema}: {quantidade} ocorrências, {taxa_tema:.1f}% de acerto")


def importar() -> None:
    """Executa a Etapa 2: importa e grava toda a atividade de puzzles."""

    logger = configure_logging(LOG_PATH, "importar_puzzle_activity")
    settings = load_settings()
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    linhas = fetch_puzzle_activity_lines(settings, logger)
    log_and_print(logger, f"Linhas recebidas da API: {len(linhas)}.")

    registros: list[dict[str, Any]] = []
    falhas_parsing = 0
    for index, linha in enumerate(linhas, start=1):
        try:
            registros.append(parse_puzzle_activity_line(linha))
        except Exception as error:
            falhas_parsing += 1
            logger.exception("Falha ao parsear a linha %d", index)
            log_and_print(logger, f"Linha {index} falhou no parsing: {error}")

    registros_importados: list[dict[str, Any]] = []
    falhas_upsert = 0
    start_time = time.time()
    for index, registro in enumerate(registros, start=1):
        try:
            upsert_puzzle_atividade(client, registro)
            registros_importados.append(registro)
        except Exception as error:
            falhas_upsert += 1
            logger.exception("Falha ao gravar o puzzle %s", registro.get("puzzle_id"))
            log_and_print(
                logger, f"Puzzle {registro.get('puzzle_id')} falhou ao gravar: {error}"
            )
        log_and_print(
            logger,
            format_progress(
                "Importação de puzzles", "registros", index, len(registros), time.time() - start_time
            ),
        )

    imprimir_resumo(logger, registros_importados, falhas_parsing, falhas_upsert)


def main() -> None:
    """Ponto de entrada do script: --inspecionar (Etapa 1) ou importação real (Etapa 2)."""

    parser = argparse.ArgumentParser(
        description="Importa o histórico de atividade de puzzles do Lichess."
    )
    parser.add_argument(
        "--inspecionar",
        action="store_true",
        help="Imprime uma amostra do NDJSON bruto de /api/puzzle/activity.",
    )
    args = parser.parse_args()

    if args.inspecionar:
        inspecionar()
        return

    importar()


if __name__ == "__main__":
    main()
