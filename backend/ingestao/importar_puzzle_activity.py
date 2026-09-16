"""Importa o histórico de atividade de puzzles do Lichess de cada usuário conectado.

Cada linha do NDJSON de /api/puzzle/activity já traz o objeto `puzzle`
completo (id, rating, themes) - não é necessário cruzar com o dump público
de puzzles do Lichess.

Desde D-34 (Estágio 2 do OAuth do Lichess, D-33), este script percorre
`lichess_oauth_tokens` em vez de depender de um único `LICHESS_STUDY_TOKEN` no
`.env`: `/api/puzzle/activity` sempre devolveu só a atividade de quem é dono
do token usado - antes disso só existia UM token (o do Edson), então só uma
pessoa podia ter puzzles importados. Agora cada usuário logado que conectou a
própria conta (fluxo OAuth) tem seu próprio token em `lichess_oauth_tokens`, e
o loop por usuário (mesmo padrão de D-28/D-31) importa a atividade de cada um
isoladamente - um token expirado ou revogado não derruba os outros.

`LICHESS_STUDY_TOKEN` continua existindo no `.env` para outros usos ainda não
migrados (`importar_anotacoes_lichess.py`, que precisa do escopo `study:write`,
fora do escopo do Estágio 1/2), mas este script específico não o lê mais.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from supabase import Client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.lichess_oauth import (  # noqa: E402
    listar_usuarios_com_token_lichess_valido,
    obter_access_token_lichess,
)
from backend.common.progress import (  # noqa: E402
    configurar_encoding_utf8,
    format_progress,
    log_and_print,
)
from backend.common.settings import carregar_variaveis_obrigatorias  # noqa: E402
from backend.ingestao.common_ingestao import (  # noqa: E402
    configure_logging,
    create_supabase_client,
    with_retry,
)
import os  # noqa: E402

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "importar_puzzle_activity.log"
PUZZLE_ACTIVITY_URL = "https://lichess.org/api/puzzle/activity"
INSPECIONAR_MAX_LINHAS = 20
TOP_TEMAS = 5


@dataclass(frozen=True)
class Settings:
    """Configurações do Supabase. O token de cada usuário vem do banco, não daqui."""

    supabase_url: str
    supabase_service_role_key: str


def load_settings() -> Settings:
    """Carrega e valida as configurações do ambiente."""

    required = carregar_variaveis_obrigatorias(
        PROJECT_ROOT, "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"
    )
    return Settings(
        supabase_url=required["SUPABASE_URL"],
        supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],
    )


class TokenRevogadoError(Exception):
    """O Lichess recusou o token com 401 - revogado do lado de lá, mesmo não expirado aqui."""


def fetch_puzzle_activity_lines(
    access_token: str, logger: logging.Logger, max_lines: int | None = None
) -> list[bytes]:
    """Chama /api/puzzle/activity com o token de UM usuário e devolve as linhas NDJSON."""

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/x-ndjson",
    }

    def request() -> list[bytes]:
        linhas: list[bytes] = []
        with requests.get(
            PUZZLE_ACTIVITY_URL, headers=headers, timeout=30, stream=True
        ) as response:
            if response.status_code == 401:
                raise TokenRevogadoError(
                    "Lichess recusou o token com 401 (revogado do lado de lá)."
                )
            response.raise_for_status()
            for linha in response.iter_lines():
                if not linha:
                    continue
                linhas.append(linha)
                if max_lines is not None and len(linhas) >= max_lines:
                    break
        return linhas

    return with_retry(request, logger, "Busca do histórico de atividade de puzzles")


def inspecionar(user_id: str | None) -> None:
    """Busca uma amostra real de UM usuário conectado e imprime o NDJSON bruto."""

    logger = configure_logging(LOG_PATH, "importar_puzzle_activity")
    settings = load_settings()
    client = create_supabase_client(
        settings.supabase_url, settings.supabase_service_role_key
    )

    alvo = user_id
    if not alvo:
        conectados = listar_usuarios_com_token_lichess_valido(client)
        if not conectados:
            print("Nenhum usuário com o Lichess conectado (lichess_oauth_tokens vazia).")
            return
        alvo = conectados[0]["user_id"]

    access_token = obter_access_token_lichess(client, alvo)
    if not access_token:
        print(f"Usuário {alvo} não tem um token do Lichess válido no momento.")
        return

    linhas = fetch_puzzle_activity_lines(
        access_token, logger, max_lines=INSPECIONAR_MAX_LINHAS
    )
    print(f"Usuário: {alvo}")
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


def upsert_puzzle_atividade(client: Client, registro: dict[str, Any], user_id: str) -> None:
    """Faz upsert de um registro em puzzle_atividade, sem duplicar."""

    client.table("puzzle_atividade").upsert(
        {**registro, "user_id": user_id}, on_conflict="puzzle_id,data"
    ).execute()


def importar_para_usuario(
    client: Client, user_id: str, logger: logging.Logger
) -> tuple[list[dict[str, Any]], int, int]:
    """Importa a atividade de puzzles de UM usuário. Nunca lança - isola o erro.

    Retorna (registros_importados, falhas_parsing, falhas_upsert). Uma lista
    vazia sem falhas pode significar tanto "sem token válido" quanto "token
    revogado" quanto "sem puzzles" - o motivo específico já foi logado aqui.
    """

    access_token = obter_access_token_lichess(client, user_id)
    if not access_token:
        log_and_print(
            logger,
            f"Usuário {user_id}: sem token do Lichess válido (ausente ou "
            "expirado) - pulando.",
        )
        return [], 0, 0

    try:
        linhas = fetch_puzzle_activity_lines(access_token, logger)
    except TokenRevogadoError:
        log_and_print(
            logger,
            f"Usuário {user_id}: token revogado no Lichess (401 apesar de não "
            "expirado na nossa tabela) - precisa reconectar a conta em /perfil.",
        )
        return [], 0, 0
    except Exception as error:
        logger.exception("Usuário %s: falha ao buscar atividade de puzzles", user_id)
        log_and_print(logger, f"Usuário {user_id}: falha ao buscar atividade: {error}")
        return [], 0, 0

    registros: list[dict[str, Any]] = []
    falhas_parsing = 0
    for index, linha in enumerate(linhas, start=1):
        try:
            registros.append(parse_puzzle_activity_line(linha))
        except Exception as error:
            falhas_parsing += 1
            logger.exception("Usuário %s: falha ao parsear a linha %d", user_id, index)
            log_and_print(
                logger, f"Usuário {user_id}: linha {index} falhou no parsing: {error}"
            )

    registros_importados: list[dict[str, Any]] = []
    falhas_upsert = 0
    for registro in registros:
        try:
            upsert_puzzle_atividade(client, registro, user_id)
            registros_importados.append(registro)
        except Exception as error:
            falhas_upsert += 1
            logger.exception(
                "Usuário %s: falha ao gravar o puzzle %s", user_id, registro.get("puzzle_id")
            )
            log_and_print(
                logger,
                f"Usuário {user_id}: puzzle {registro.get('puzzle_id')} falhou ao gravar: {error}",
            )

    return registros_importados, falhas_parsing, falhas_upsert


def imprimir_resumo(
    logger: logging.Logger,
    registros_importados: list[dict[str, Any]],
    falhas_parsing: int,
    falhas_upsert: int,
    usuarios_processados: int,
    usuarios_pulados: int,
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
        f"Resumo: {usuarios_processados} usuário(s) processado(s), "
        f"{usuarios_pulados} pulado(s) (sem token válido ou revogado). "
        f"{total} puzzles importados, {falhas_parsing} falhas de parsing, "
        f"{falhas_upsert} falhas ao gravar. Taxa de acerto geral: {taxa_geral:.1f}%.",
    )

    if contagem_temas:
        print(f"\nTop {TOP_TEMAS} temas mais frequentes:")
        for tema, quantidade in contagem_temas.most_common(TOP_TEMAS):
            taxa_tema = acertos_por_tema[tema] / quantidade * 100
            print(f"  - {tema}: {quantidade} ocorrências, {taxa_tema:.1f}% de acerto")


def importar() -> None:
    """Percorre todos os usuários com Lichess conectado e importa a atividade de cada um."""

    logger = configure_logging(LOG_PATH, "importar_puzzle_activity")
    settings = load_settings()
    client = create_supabase_client(
        settings.supabase_url, settings.supabase_service_role_key
    )

    usuarios = listar_usuarios_com_token_lichess_valido(client)
    log_and_print(
        logger, f"Usuários com o Lichess conectado (token não expirado): {len(usuarios)}."
    )
    if not usuarios:
        print("Nenhum usuário com o Lichess conectado. Nada a importar.")
        return

    todos_registros: list[dict[str, Any]] = []
    total_falhas_parsing = 0
    total_falhas_upsert = 0
    usuarios_processados = 0
    usuarios_pulados = 0
    start_time = time.time()

    for index, usuario in enumerate(usuarios, start=1):
        user_id = usuario["user_id"]
        try:
            registros, falhas_parsing, falhas_upsert = importar_para_usuario(
                client, user_id, logger
            )
            if registros or falhas_parsing or falhas_upsert:
                usuarios_processados += 1
            else:
                usuarios_pulados += 1
            todos_registros.extend(registros)
            total_falhas_parsing += falhas_parsing
            total_falhas_upsert += falhas_upsert
        except Exception as error:
            usuarios_pulados += 1
            logger.exception("Falha inesperada ao processar o usuário %s", user_id)
            log_and_print(logger, f"Usuário {user_id} falhou de forma inesperada: {error}")
        log_and_print(
            logger,
            format_progress(
                "Importação de puzzles", "usuários", index, len(usuarios), time.time() - start_time
            ),
        )

    imprimir_resumo(
        logger,
        todos_registros,
        total_falhas_parsing,
        total_falhas_upsert,
        usuarios_processados,
        usuarios_pulados,
    )


def main() -> None:
    """Ponto de entrada do script: --inspecionar (amostra) ou importação real."""

    parser = argparse.ArgumentParser(
        description="Importa o histórico de atividade de puzzles do Lichess de cada usuário conectado."
    )
    parser.add_argument(
        "--inspecionar",
        action="store_true",
        help="Imprime uma amostra do NDJSON bruto de /api/puzzle/activity de um usuário.",
    )
    parser.add_argument(
        "--user-id",
        help="user_id específico para --inspecionar (default: o primeiro usuário conectado).",
    )
    args = parser.parse_args()

    if args.inspecionar:
        inspecionar(args.user_id)
        return

    importar()


if __name__ == "__main__":
    main()
