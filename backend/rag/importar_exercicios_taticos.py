"""Importa um subconjunto curado do dump público de puzzles do Lichess (CC0)
para o catálogo `exercicios_taticos` (D-49), re-taggeado em
`HEXAGON_CATEGORIES` (a NOSSA taxonomia, não a taxonomia solta de temas do
Lichess). Alimenta `POST /treino/foco/{categoria}`, que insere exercícios do
catálogo na mesma fila de repetição espaçada do D-48
(`fila_treino_espacado`).

Import ocasional/manual - não roda no pipeline diário. Uso:
  python backend/rag/importar_exercicios_taticos.py

Não guarda a "resposta certa" do puzzle: o `fen` gravado já é a posição real
a resolver (o FEN bruto do Lichess mais o primeiro lance do CSV, que é o
lance de preparo automático do adversário). A qualidade da resposta do
usuário é avaliada dinamicamente pelo Stockfish em `POST /treino/{id}/
responder`, igual ao que já acontece com `lances_criticos` - sem duplicar
gabarito.

Achado honesto (ver D-49 em docs/DECISOES.md): o Lichess não tem temas de
puzzle equivalentes a ESTRATEGIA (avaliação posicional) nem GESTAO_DE_TEMPO
(os puzzles são posições estáticas, sem relógio) - só TATICA, CALCULO,
FINAIS e ESTRUTURA_DE_PEOES recebem exercícios de catálogo nesta v1.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import chess
import requests
import zstandard
from dotenv import load_dotenv
from supabase import Client, create_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.agente2_analista import HEXAGON_CATEGORIES  # noqa: E402
from backend.common.progress import configurar_encoding_utf8, log_and_print  # noqa: E402

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "importar_exercicios_taticos.log"
PUZZLE_DUMP_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
BATCH_SIZE = 500

# Faixa de qualidade dos puzzles aceitos - configurável por env var, mesmo
# padrão de LIMITE_DIARIO_*/TREINO_NOVOS_POR_DIA (D-32/D-48).
EXERCICIO_RATING_MIN = int(os.getenv("EXERCICIO_RATING_MIN", "1000"))
EXERCICIO_RATING_MAX = int(os.getenv("EXERCICIO_RATING_MAX", "2200"))
EXERCICIO_POPULARIDADE_MIN = int(os.getenv("EXERCICIO_POPULARIDADE_MIN", "50"))
EXERCICIOS_POR_CATEGORIA = int(os.getenv("EXERCICIOS_POR_CATEGORIA", "300"))

# Tema do Lichess -> categoria do hexágono (HEXAGON_CATEGORIES). Cada linha
# usa o PRIMEIRO tema da lista que bate aqui; linhas sem nenhum tema mapeado
# são puladas. Ponto de partida: os mesmos temas já catalogados em
# TEMAS_PUZZLE_INFO (backend/agentes/insights_puzzles.py), remapeados pra
# HEXAGON_CATEGORIES em vez da categoria solta usada lá.
TEMA_LICHESS_PARA_CATEGORIA: dict[str, str] = {
    # TATICA: calculo_tatico_deficiente, visao_em_tunel, perda_de_material
    "fork": "TATICA",
    "pin": "TATICA",
    "skewer": "TATICA",
    "discoveredAttack": "TATICA",
    "hangingPiece": "TATICA",
    "trappedPiece": "TATICA",
    "attraction": "TATICA",
    "deflection": "TATICA",
    "overload": "TATICA",
    "intermezzo": "TATICA",
    "quietMove": "TATICA",
    "sacrifice": "TATICA",
    "clearance": "TATICA",
    "interference": "TATICA",
    "enPassant": "TATICA",
    # CALCULO: perda_de_iniciativa, seguranca_do_rei, negligencia_profilatica,
    # passividade_excessiva, falta_de_coordenacao_de_pecas
    "exposedKing": "CALCULO",
    "kingsideAttack": "CALCULO",
    "queensideAttack": "CALCULO",
    "discoveredCheck": "CALCULO",
    "doubleCheck": "CALCULO",
    "mateIn1": "CALCULO",
    "mateIn2": "CALCULO",
    "mateIn3": "CALCULO",
    "mateIn4": "CALCULO",
    "veryLong": "CALCULO",
    # FINAIS: erro_tecnico_de_final
    "pawnEndgame": "FINAIS",
    "bishopEndgame": "FINAIS",
    "rookEndgame": "FINAIS",
    "queenEndgame": "FINAIS",
    "endgame": "FINAIS",
    "promotion": "FINAIS",
    "underPromotion": "FINAIS",
    "zugzwang": "FINAIS",
    # ESTRUTURA_DE_PEOES: fraqueza_estrutural_de_peoes, abertura_de_linhas_desfavoravel
    "advancedPawn": "ESTRUTURA_DE_PEOES",
}

CATEGORIAS_APLICAVEIS: frozenset[str] = frozenset(TEMA_LICHESS_PARA_CATEGORIA.values())
CATEGORIAS_SEM_COBERTURA: frozenset[str] = frozenset(HEXAGON_CATEGORIES) - CATEGORIAS_APLICAVEIS


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do script."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("importar_exercicios_taticos")
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


# ---------------------------------------------------------------------------
# Funções puras - testáveis sem rede nem banco
# ---------------------------------------------------------------------------


def categoria_do_tema(temas: list[str]) -> str | None:
    """Devolve a categoria do hexágono do PRIMEIRO tema mapeado, ou None."""

    for tema in temas:
        categoria = TEMA_LICHESS_PARA_CATEGORIA.get(tema)
        if categoria:
            return categoria
    return None


def fen_apos_lance_preparo(fen: str, lance_preparo_uci: str) -> str:
    """Aplica o lance de preparo (1º lance do CSV) ao FEN bruto do Lichess.

    O FEN do dump é a posição ANTES do lance automático do adversário que
    leva à posição real a resolver - aplicar esse lance é o que dá a posição
    que o usuário efetivamente vê no card de treino.
    """

    board = chess.Board(fen)
    board.push_uci(lance_preparo_uci)
    return board.fen()


def linha_atende_filtros(
    rating: int | None,
    popularidade: int | None,
    rating_min: int = EXERCICIO_RATING_MIN,
    rating_max: int = EXERCICIO_RATING_MAX,
    popularidade_min: int = EXERCICIO_POPULARIDADE_MIN,
) -> bool:
    """Filtro de qualidade: faixa de rating + popularidade mínima."""

    if rating is None or not (rating_min <= rating <= rating_max):
        return False
    if popularidade is None or popularidade < popularidade_min:
        return False
    return True


def processar_linha(
    row: dict[str, str],
    rating_min: int = EXERCICIO_RATING_MIN,
    rating_max: int = EXERCICIO_RATING_MAX,
    popularidade_min: int = EXERCICIO_POPULARIDADE_MIN,
) -> dict[str, Any] | None:
    """Converte uma linha crua do CSV do Lichess num registro de
    `exercicios_taticos`, ou None se a linha deve ser pulada (tema não
    mapeado, fora da faixa de qualidade, ou FEN/lance inválido)."""

    temas = (row.get("Themes") or "").split()
    categoria = categoria_do_tema(temas)
    if not categoria:
        return None

    try:
        rating = int(row["Rating"])
        popularidade = int(row["Popularity"])
    except (KeyError, ValueError, TypeError):
        return None
    if not linha_atende_filtros(rating, popularidade, rating_min, rating_max, popularidade_min):
        return None

    lances = (row.get("Moves") or "").split()
    puzzle_id = row.get("PuzzleId")
    fen_bruto = row.get("FEN")
    if not lances or not puzzle_id or not fen_bruto:
        return None

    try:
        fen_exercicio = fen_apos_lance_preparo(fen_bruto, lances[0])
    except ValueError:
        return None

    return {
        "puzzle_id_lichess": puzzle_id,
        "fen": fen_exercicio,
        "categoria_hexagono": categoria,
        "temas_lichess": temas,
        "rating": rating,
        "popularidade": popularidade,
    }


def categoria_ainda_aceita(contador_por_categoria: dict[str, int], categoria: str, teto: int) -> bool:
    """True se a categoria ainda não bateu o teto de exercícios importados."""

    return contador_por_categoria.get(categoria, 0) < teto


def todas_categorias_completas(
    contador_por_categoria: dict[str, int],
    categorias_aplicaveis: frozenset[str],
    teto: int,
) -> bool:
    """True quando todas as categorias com tema mapeado já bateram o teto -
    sinal pra parar de ler o stream antes do fim do arquivo."""

    return all(
        contador_por_categoria.get(categoria, 0) >= teto for categoria in categorias_aplicaveis
    )


# ---------------------------------------------------------------------------
# Streaming do dump público (sem salvar o arquivo bruto em disco)
# ---------------------------------------------------------------------------


def iterar_linhas_dump(logger: logging.Logger) -> Iterator[dict[str, str]]:
    """Baixa e descomprime o dump em streaming, linha a linha (NDJSON-like via CSV)."""

    log_and_print(logger, f"Conectando em {PUZZLE_DUMP_URL}...")
    with requests.get(PUZZLE_DUMP_URL, stream=True, timeout=60) as response:
        response.raise_for_status()
        descompressor = zstandard.ZstdDecompressor()
        with descompressor.stream_reader(response.raw) as leitor:
            texto = io.TextIOWrapper(leitor, encoding="utf-8", newline="")
            yield from csv.DictReader(texto)


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------


def importar(
    client: Client,
    logger: logging.Logger,
    rating_min: int = EXERCICIO_RATING_MIN,
    rating_max: int = EXERCICIO_RATING_MAX,
    popularidade_min: int = EXERCICIO_POPULARIDADE_MIN,
    teto_por_categoria: int = EXERCICIOS_POR_CATEGORIA,
) -> dict[str, int]:
    """Faz o streaming do dump, filtra/mapeia e faz upsert em lote.

    Para de ler o stream assim que todas as categorias aplicáveis baterem o
    teto (evita descomprimir/ler o arquivo inteiro, que tem milhões de
    linhas) - ou quando o arquivo acabar antes disso.
    """

    contador_por_categoria: dict[str, int] = {}
    registros: list[dict[str, Any]] = []
    total_lidas = 0
    total_pulos = 0

    for row in iterar_linhas_dump(logger):
        total_lidas += 1
        registro = processar_linha(row, rating_min, rating_max, popularidade_min)
        if registro is None:
            total_pulos += 1
            continue

        categoria = registro["categoria_hexagono"]
        if not categoria_ainda_aceita(contador_por_categoria, categoria, teto_por_categoria):
            continue

        registros.append(registro)
        contador_por_categoria[categoria] = contador_por_categoria.get(categoria, 0) + 1

        if total_lidas % 50000 == 0:
            log_and_print(
                logger,
                f"{total_lidas} linhas lidas do dump, {len(registros)} exercícios "
                f"aceitos até agora ({dict(contador_por_categoria)}).",
            )

        if todas_categorias_completas(contador_por_categoria, CATEGORIAS_APLICAVEIS, teto_por_categoria):
            log_and_print(logger, "Todas as categorias bateram o teto - encerrando a leitura do stream.")
            break

    for inicio in range(0, len(registros), BATCH_SIZE):
        lote = registros[inicio : inicio + BATCH_SIZE]
        client.table("exercicios_taticos").upsert(lote, on_conflict="puzzle_id_lichess").execute()

    resumo = {
        "linhas_lidas": total_lidas,
        "exercicios_importados": len(registros),
        "linhas_puladas": total_pulos,
        **contador_por_categoria,
    }
    return resumo


def main() -> None:
    """Ponto de entrada: importa o catálogo de exercícios táticos."""

    logger = configure_logging()
    settings = load_settings()
    client = create_client(settings["SUPABASE_URL"], settings["SUPABASE_SERVICE_ROLE_KEY"])

    resumo = importar(client, logger)

    print(f"Linhas lidas do dump: {resumo['linhas_lidas']}")
    print(f"Exercícios importados: {resumo['exercicios_importados']}")
    print(f"Linhas puladas (tema não mapeado ou fora da faixa de qualidade): {resumo['linhas_puladas']}")
    for categoria in sorted(CATEGORIAS_APLICAVEIS):
        print(f"  {categoria}: {resumo.get(categoria, 0)}")
    if CATEGORIAS_SEM_COBERTURA:
        print(
            "Sem cobertura de catálogo (sem tema equivalente no Lichess): "
            + ", ".join(sorted(CATEGORIAS_SEM_COBERTURA))
        )


if __name__ == "__main__":
    main()
