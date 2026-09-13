"""Preenche `partidas.abertura_normalizada` agrupando aberturas por família.

Cada plataforma expõe o nome da abertura de um jeito diferente:

- Chess.com grava a URL do artigo na tag ``[ECOUrl "..."]`` do próprio PGN
  salvo — o nome já está ali, só precisa ser extraído.
- Lichess não grava nada disso no PGN armazenado (nem a tag ``[Opening]``,
  nem o ECO em texto). O nome só existe na resposta da API de exportação de
  partida (``GET /game/export/{id}?opening=1``) — o mesmo endpoint já usado
  por ``enriquecer_partidas_lichess.py`` (ver D-4 em DECISOES.md: consumir o
  que o Lichess já calcula em vez de recalcular).
- Partidas ``MANUAL`` (PGN colado à mão) às vezes trazem a tag
  ``[Opening "..."]`` direto, dependendo de onde o PGN foi copiado.

O agrupamento em si é um dicionário de regras simples e extensível: qualquer
nome que bata com um padrão reconhecido vira o nome da família em português;
sem correspondência, o nome original é mantido (nunca inventamos uma família
que o dado não sustenta).
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import chess.pgn
import requests
from dotenv import load_dotenv
from supabase import Client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import (  # noqa: E402
    configurar_encoding_utf8,
    format_progress,
    log_and_print,
)
from backend.ingestao.common_ingestao import (  # noqa: E402
    configure_logging,
    create_supabase_client,
    with_retry,
)

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "normalizar_aberturas.log"
GAME_EXPORT_URL = "https://lichess.org/game/export/{external_id}?opening=1"
PAGE_SIZE = 1000
SEM_NOME = "Desconhecida"

ECOURL_PATTERN = re.compile(r'\[ECOUrl\s+"https://www\.chess\.com/openings/([^"]+)"\]')

# Ordem importa: padrões mais específicos primeiro. Ex.: "Giuoco Piano" tem
# que virar Italiana antes de qualquer regra genérica de peão de rei.
MAPEAMENTO_FAMILIAS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ruy lopez|spanish game", re.I), "Espanhola"),
    (re.compile(r"giuoco piano|italian game", re.I), "Italiana"),
    (re.compile(r"london system", re.I), "Sistema Londres"),
    (re.compile(r"queen'?s?\s*gambit", re.I), "Gambito da Dama"),
    (re.compile(r"king'?s?\s*gambit", re.I), "Gambito do Rei"),
    (re.compile(r"englund gambit", re.I), "Gambito Englund"),
    (re.compile(r"sicilian", re.I), "Siciliana"),
    (re.compile(r"caro.?kann", re.I), "Caro-Kann"),
    (re.compile(r"french defen[cs]e", re.I), "Francesa"),
    (re.compile(r"scandinavian", re.I), "Escandinava"),
    (re.compile(r"pirc defen[cs]e", re.I), "Pirc"),
    (re.compile(r"modern defen[cs]e", re.I), "Moderna"),
    (re.compile(r"english opening", re.I), "Inglesa"),
    (re.compile(r"scotch game", re.I), "Escocesa"),
    (re.compile(r"four knights", re.I), "Quatro Cavalos"),
    (re.compile(r"philidor defen[cs]e", re.I), "Philidor"),
    (re.compile(r"vienna game", re.I), "Vienense"),
    (re.compile(r"cent(?:er|re) game", re.I), "Jogo do Centro"),
    (re.compile(r"king'?s?\s*indian", re.I), "Índia do Rei"),
    (re.compile(r"nimzo.?indian", re.I), "Nimzo-Índia"),
    (re.compile(r"gr[uü]nfeld", re.I), "Grünfeld"),
    (re.compile(r"dutch defen[cs]e", re.I), "Holandesa"),
    (re.compile(r"bird'?s?\s*opening", re.I), "Bird"),
    (re.compile(r"alekhine'?s?\s*defen[cs]e", re.I), "Alekhine"),
    (re.compile(r"r[eé]ti opening", re.I), "Réti"),
    (re.compile(r"queen'?s?\s*pawn", re.I), "Peão de Dama"),
    (re.compile(r"king'?s?\s*pawn opening", re.I), "Peão de Rei"),
]


def normalizar_abertura(nome: str | None) -> str:
    """Agrupa um nome de abertura em texto livre numa família reconhecida.

    Sem correspondência (ou sem nome algum), devolve o próprio nome original
    — o fallback nunca inventa uma família, só preserva o que já se sabia.
    """

    if not nome or not nome.strip():
        return SEM_NOME
    nome = nome.strip()
    for padrao, nome_pt in MAPEAMENTO_FAMILIAS:
        if padrao.search(nome):
            return nome_pt
    return nome


def extrair_nome_do_pgn(pgn: str) -> str | None:
    """Lê a tag ``[Opening]`` quando presente no PGN (avulsas/MANUAL)."""

    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return None
    nome = game.headers.get("Opening")
    return nome.strip() if nome and nome != "?" else None


def extrair_nome_de_ecourl(pgn: str) -> str | None:
    """Deriva o nome legível da abertura a partir da tag ``[ECOUrl]`` (Chess.com)."""

    match = ECOURL_PATTERN.search(pgn)
    if not match:
        return None
    slug = match.group(1)
    nome = slug.replace("-", " ").replace("...", " ").strip()
    return nome or None


def buscar_nome_via_lichess(external_id: str, logger: logging.Logger) -> str | None:
    """Busca o nome da abertura na API do Lichess quando o PGN não o guarda."""

    def request() -> dict[str, Any]:
        response = requests.get(
            GAME_EXPORT_URL.format(external_id=external_id),
            headers={"Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    try:
        game_export = with_retry(request, logger, f"Abertura da partida {external_id}")
    except requests.RequestException:
        return None
    opening = game_export.get("opening")
    nome = opening.get("name") if isinstance(opening, dict) else None
    return str(nome).strip() if nome else None


def resolver_nome_abertura(
    plataforma: str,
    pgn: str,
    external_id: str | None,
    logger: logging.Logger,
) -> str | None:
    """Encontra o melhor nome de abertura disponível para uma partida."""

    nome = extrair_nome_do_pgn(pgn)
    if nome:
        return nome
    nome = extrair_nome_de_ecourl(pgn)
    if nome:
        return nome
    if plataforma == "LICHESS" and external_id:
        return buscar_nome_via_lichess(external_id, logger)
    return None


def fetch_partidas_pendentes(client: Client) -> list[dict[str, Any]]:
    """Busca partidas ainda sem `abertura_normalizada`, paginando a tabela."""

    partidas: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            client.table("partidas")
            .select("id, plataforma, pgn, external_id")
            .is_("abertura_normalizada", "null")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        partidas.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return partidas


def atualizar_abertura(client: Client, partida_id: Any, abertura: str) -> None:
    """Grava a abertura normalizada de uma única partida."""

    (
        client.table("partidas")
        .update({"abertura_normalizada": abertura})
        .eq("id", partida_id)
        .execute()
    )


def processar(
    client: Client, logger: logging.Logger, dry_run: bool = False
) -> tuple[dict[str, int], int]:
    """Normaliza todas as partidas pendentes; devolve a distribuição e falhas."""

    partidas = fetch_partidas_pendentes(client)
    total = len(partidas)
    log_and_print(logger, f"Partidas a normalizar: {total}")

    distribuicao: dict[str, int] = {}
    falhas = 0
    start_time = time.time()
    for index, partida in enumerate(partidas, start=1):
        try:
            nome = resolver_nome_abertura(
                partida.get("plataforma") or "",
                partida.get("pgn") or "",
                partida.get("external_id"),
                logger,
            )
            abertura = normalizar_abertura(nome)
            distribuicao[abertura] = distribuicao.get(abertura, 0) + 1
            if not dry_run:
                atualizar_abertura(client, partida["id"], abertura)
        except Exception as error:
            falhas += 1
            logger.exception(
                "Falha ao normalizar abertura da partida %s: %s",
                partida.get("id"),
                error,
            )
        log_and_print(
            logger,
            format_progress(
                "Normalização", "partidas", index, total, time.time() - start_time
            ),
        )

    return distribuicao, falhas


def load_settings() -> tuple[str, str]:
    """Carrega as credenciais do Supabase a partir do `.env`."""

    load_dotenv(PROJECT_ROOT / ".env")
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError(
            "Variáveis de ambiente ausentes: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY"
        )
    return url, key


def main() -> None:
    """Executa a normalização e imprime a distribuição resultante."""

    parser = argparse.ArgumentParser(
        description="Preenche partidas.abertura_normalizada agrupando por família."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calcula e imprime a distribuição, sem gravar no banco.",
    )
    args = parser.parse_args()

    logger = configure_logging(LOG_PATH, "normalizar_aberturas")
    supabase_url, supabase_key = load_settings()
    client = create_supabase_client(supabase_url, supabase_key)

    distribuicao, falhas = processar(client, logger, dry_run=args.dry_run)

    prefixo = "[DRY-RUN] " if args.dry_run else ""
    print(f"\n{prefixo}Distribuição de abertura_normalizada:")
    for nome, quantidade in sorted(distribuicao.items(), key=lambda item: -item[1]):
        print(f"  {quantidade:>4}  {nome}")
    print(f"\n{prefixo}Total: {sum(distribuicao.values())} partidas, {falhas} falhas.")


if __name__ == "__main__":
    main()
