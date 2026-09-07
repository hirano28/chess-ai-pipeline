"""Importa anotações de pensamento escritas em capítulos de Lichess Studies."""

from __future__ import annotations

import argparse
import io
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import berserk
import chess.pgn
from dotenv import load_dotenv
from supabase import Client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.ingestao.common_ingestao import (  # noqa: E402
    configure_logging,
    create_supabase_client,
)

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "importar_anotacoes_lichess.log"
# Remove tags de anotação do Lichess (%clk, %eval etc.) para checar se sobra texto real.
ANNOTATION_TAG_PATTERN = re.compile(r"\[%[^\]]*\]")
GAME_ID_PATTERN = re.compile(r"lichess\.org/([A-Za-z0-9]{8})")
# Comentário de resultado que o Lichess anexa automaticamente ao último lance.
RESULT_COMMENT_PATTERN = re.compile(r"^\s*(1-0|0-1|1/2-1/2)\b")


@dataclass(frozen=True)
class Settings:
    """Configurações do Supabase e do token de estudo do Lichess."""

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


def eh_comentario_sem_texto_real(comment: str) -> bool:
    """True quando não sobra nenhum texto após remover tags como %clk."""

    return ANNOTATION_TAG_PATTERN.sub("", comment).strip() == ""


def eh_comentario_de_resultado_automatico(texto: str) -> bool:
    """Identifica o comentário de resultado que o Lichess anexa automaticamente."""

    return bool(RESULT_COMMENT_PATTERN.match(texto))


def extrair_comentarios(
    pgn_text: str,
) -> tuple[list[tuple[int, str]], dict[str, str], int]:
    """Extrai (numero_lance, texto) de cada lance comentado, headers e total pulado."""

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Não foi possível fazer parse do PGN do capítulo.")

    comentarios: list[tuple[int, str]] = []
    pulados = 0
    board = game.board()
    for node in game.mainline():
        move_number = board.fullmove_number
        board.push(node.move)
        comment = (node.comment or "").strip()
        if not comment:
            continue
        if eh_comentario_sem_texto_real(comment):
            pulados += 1
            continue
        texto = ANNOTATION_TAG_PATTERN.sub("", comment).strip()
        if eh_comentario_de_resultado_automatico(texto):
            pulados += 1
            continue
        comentarios.append((move_number, texto))
    return comentarios, dict(game.headers), pulados


def mesclar_comentarios_por_lance(
    comentarios: list[tuple[int, str]],
) -> list[tuple[int, str]]:
    """Mescla comentários que caem no mesmo numero_lance (branca e preta).

    A tabela anotacoes_pensamento não distingue cor, então dois comentários no
    mesmo numero_lance colidiriam na constraint (partida_id, numero_lance).
    """

    agrupados: dict[int, list[str]] = {}
    for numero_lance, texto in comentarios:
        agrupados.setdefault(numero_lance, []).append(texto)
    return [
        (numero_lance, " / ".join(textos))
        for numero_lance, textos in sorted(agrupados.items())
    ]


def extrair_external_id(headers: dict[str, str]) -> str | None:
    """Extrai o external_id da partida a partir dos headers [GameId]/[Site] do PGN."""

    game_id = headers.get("GameId")
    if game_id:
        return game_id.strip()
    site = headers.get("Site") or ""
    match = GAME_ID_PATTERN.search(site)
    return match.group(1) if match else None


def buscar_partida(client: Client, external_id: str) -> dict[str, Any] | None:
    """Busca a partida correspondente ao external_id extraído do PGN do estudo."""

    response = (
        client.table("partidas")
        .select("id, external_id")
        .eq("plataforma", "LICHESS")
        .eq("external_id", external_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def importar_capitulo(
    supabase_client: Client,
    berserk_client: Any,
    study_id: str,
    chapter_id: str,
    logger: logging.Logger,
) -> None:
    """Importa as anotações de pensamento de um capítulo específico do estudo."""

    pgn_text = berserk_client.studies.export_chapter(study_id, chapter_id)
    comentarios, headers, pulados = extrair_comentarios(pgn_text)
    external_id = extrair_external_id(headers)
    partida = buscar_partida(supabase_client, external_id) if external_id else None

    if partida is None:
        logger.warning(
            "Partida não encontrada (study=%s chapter=%s external_id=%s)",
            study_id,
            chapter_id,
            external_id,
        )
        print(
            f"Capítulo {chapter_id}: partida NÃO encontrada no banco "
            f"(external_id={external_id!r}). Nenhuma anotação importada. "
            f"Comentários com texto real detectados: {len(comentarios)} "
            f"(pulados só-relógio/sem texto: {pulados})."
        )
        return

    comentarios = mesclar_comentarios_por_lance(comentarios)
    rows = [
        {
            "partida_id": partida["id"],
            "numero_lance": numero_lance,
            "texto_pensamento": texto,
            "origem": "LICHESS_STUDY",
        }
        for numero_lance, texto in comentarios
    ]
    if rows:
        supabase_client.table("anotacoes_pensamento").upsert(
            rows, on_conflict="partida_id,numero_lance"
        ).execute()

    logger.info(
        "Capítulo %s importado: %d comentários, %d pulados, partida_id=%s",
        chapter_id,
        len(rows),
        pulados,
        partida["id"],
    )
    print(
        f"Capítulo {chapter_id} (partida {external_id}, encontrada no banco): "
        f"{len(rows)} comentários importados, {pulados} pulados (só relógio/sem texto)."
    )


def main() -> None:
    """Ponto de entrada: importa um capítulo específico de um estudo do Lichess."""

    parser = argparse.ArgumentParser(
        description="Importa anotações de pensamento de um capítulo de Lichess Study."
    )
    parser.add_argument("--study-id", required=True, help="ID do study no Lichess.")
    parser.add_argument("--chapter-id", required=True, help="ID do capítulo no study.")
    args = parser.parse_args()

    logger = configure_logging(LOG_PATH, "importar_anotacoes_lichess")
    settings = load_settings()
    supabase_client = create_supabase_client(
        settings.supabase_url, settings.supabase_service_role_key
    )
    berserk_client = berserk.Client(
        session=berserk.TokenSession(settings.lichess_study_token)
    )

    importar_capitulo(
        supabase_client, berserk_client, args.study_id, args.chapter_id, logger
    )


if __name__ == "__main__":
    main()
