"""Processa um livro em PDF em chunks com embeddings para o RAG."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
import traceback
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import google.genai as genai
from google.genai import types
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from dotenv import load_dotenv
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import (  # noqa: E402
    format_duration,
    format_progress,
    log_and_print,
)
LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "processar_livro.log"
EMBEDDING_MODEL = "gemini-embedding-001"
CHUNK_TARGET_WORDS = 500
CHUNK_OVERLAP_WORDS = 50
PROGRESS_EVERY = 20
RETRY_LIMIT = 3
RETRY_BACKOFF_SECONDS = (5, 15, 45)
EXPECTED_EMBEDDING_DIMENSION = 768
OCR_TEXT_THRESHOLD = 500
OCR_DPI = 300
OCR_LANG = "por"
OCR_PROGRESS_EVERY = 10
OCR_CACHE_DIR = PROJECT_ROOT / "backend" / "rag" / ".ocr_cache"
MIN_CHUNK_WORDS = 200
UPPERCASE_TITLE_MIN_CHARS = 15
MIN_TITLE_ALPHA_RATIO = 0.7
MAX_CHUNKS_PER_BOOK = 1000
INDICE_MARKERS = ("índice de capítulos", "índice de jogadores")

CHAPTER_PATTERNS = (
    re.compile(
        r"^\s*(CAP[IÍ]TULO|PARTE)\s+[\dIVXLC]+\s*(?:[-—]\s*.+)?$",
        re.IGNORECASE,
    ),
)
NUMBERED_CHAPTER_PATTERN = re.compile(
    r"^\s*[1-9]\s*[-—]\s+[A-ZÁÉÍÓÚÂÊÔÃÕÀÇ].*$"
)


def numbered_chapter_number(line: str) -> int | None:
    """Extrai o número de um candidato de capítulo numerado."""

    match = re.match(r"^\s*([1-9])\s*[-—]\s+", line)
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class Chunk:
    """Trecho de texto associado ao capítulo e à página de origem."""

    conteudo: str
    capitulo: str | None
    pagina_aprox: int


@dataclass(frozen=True)
class PageText:
    """Texto extraído de uma página específica do PDF."""

    numero: int
    texto: str


class EmbeddingDimensionError(ValueError):
    """Indica que o vetor não tem a dimensão exigida pela tabela."""


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do processador de livros."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("processar_livro")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


def load_settings() -> dict[str, str]:
    """Carrega e valida as variáveis de ambiente necessárias."""

    load_dotenv(PROJECT_ROOT / ".env")
    required = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )
    settings = {name: value for name, value in required.items()}
    settings["TESSERACT_PATH"] = os.getenv("TESSERACT_PATH", "")
    settings["POPPLER_PATH"] = os.getenv("POPPLER_PATH", "")
    return settings  # type: ignore[return-value]


def ocr_cache_path(pdf_path: Path) -> Path:
    """Retorna o caminho estável do cache OCR de um PDF."""

    digest = hashlib.sha256(str(pdf_path.resolve()).encode("utf-8")).hexdigest()[:16]
    return OCR_CACHE_DIR / f"{pdf_path.stem}_{digest}.json"


def load_ocr_cache(pdf_path: Path, logger: logging.Logger) -> list[PageText] | None:
    """Carrega cache somente quando ele é mais recente que o PDF."""

    cache_path = ocr_cache_path(pdf_path)
    if not cache_path.exists() or cache_path.stat().st_mtime < pdf_path.stat().st_mtime:
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        pages = [PageText(numero=int(item["numero"]), texto=item["texto"]) for item in payload]
        logger.info("Cache OCR carregado: %s (%d páginas)", cache_path, len(pages))
        return pages
    except Exception:
        logger.warning("Cache OCR inválido; será refeito:\n%s", traceback.format_exc())
        return None


def save_ocr_cache(pdf_path: Path, pages: list[PageText], logger: logging.Logger) -> None:
    """Salva o OCR em JSON fora do fluxo de embeddings."""

    cache_path = ocr_cache_path(pdf_path)
    OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = [{"numero": page.numero, "texto": page.texto} for page in pages]
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Cache OCR salvo: %s", cache_path)


def extract_pages_ocr(
    pdf_path: Path,
    poppler_path: str,
    tesseract_cmd: str,
    logger: logging.Logger,
) -> list[PageText]:
    """Renderiza cada página e extrai texto por OCR em português."""

    cached_pages = load_ocr_cache(pdf_path, logger)
    if cached_pages is not None:
        return cached_pages
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    images = convert_from_path(
        str(pdf_path),
        dpi=OCR_DPI,
        poppler_path=poppler_path or None,
    )
    total = len(images)
    pages: list[PageText] = []
    ocr_start = time.time()
    for index, image in enumerate(images, start=1):
        try:
            text = pytesseract.image_to_string(image, lang=OCR_LANG)
        except Exception:
            logger.error(
                "OCR falhou na página %d:\n%s", index, traceback.format_exc()
            )
            text = ""
        pages.append(PageText(numero=index, texto=text))
        if index % OCR_PROGRESS_EVERY == 0:
            log_and_print(
                logger,
                format_progress(
                    "OCR", "páginas", index, total, time.time() - ocr_start
                ),
            )
    save_ocr_cache(pdf_path, pages, logger)
    return pages


def resolve_pages(
    pdf_path: Path,
    settings: dict[str, str],
    forcar_ocr: bool,
    logger: logging.Logger,
) -> list[PageText]:
    """Escolhe entre extração nativa e OCR conforme o conteúdo do PDF."""

    if forcar_ocr:
        logger.info("Flag --forcar-ocr ativa; extraindo diretamente via OCR...")
        return extract_pages_ocr(
            pdf_path,
            settings["POPPLER_PATH"],
            settings["TESSERACT_PATH"],
            logger,
        )

    pages = extract_pages(pdf_path)
    total_chars = sum(len(page.texto) for page in pages)
    if total_chars < OCR_TEXT_THRESHOLD:
        logger.warning("PDF sem texto nativo detectado, iniciando OCR...")
        return extract_pages_ocr(
            pdf_path,
            settings["POPPLER_PATH"],
            settings["TESSERACT_PATH"],
            logger,
        )
    return pages


def extract_pages(pdf_path: Path) -> list[PageText]:
    """Extrai o texto de cada página preservando o número da página."""

    pages: list[PageText] = []
    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append(PageText(numero=index, texto=text))
    return pages


def detect_chapter(line: str, allow_numbered: bool = True) -> str | None:
    """Detecta se uma linha é um título real de capítulo ou parte."""

    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return None
    for pattern in CHAPTER_PATTERNS:
        if pattern.match(stripped):
            if "," in stripped or "." in stripped or (
                stripped.endswith(tuple(str(number) for number in range(10)))
                and not re.search(r"\b(?:[IVXLC]+|\d+)\s*$", stripped)
            ):
                return None
            return stripped
    if allow_numbered and NUMBERED_CHAPTER_PATTERN.fullmatch(stripped):
        if "," not in stripped and "." not in stripped:
            if not re.search(r"[-—]\s*\d+\s*$", stripped):
                return stripped
    if (
        len(stripped) >= UPPERCASE_TITLE_MIN_CHARS
        and stripped == stripped.upper()
        and not any(char.isdigit() for char in stripped)
    ):
        letters = sum(1 for char in stripped if char.isalpha())
        non_space = sum(1 for char in stripped if not char.isspace())
        if non_space and letters / non_space >= MIN_TITLE_ALPHA_RATIO:
            return stripped
    return None


def _normalized_header(line: str) -> str:
    """Normaliza uma linha para comparar cabeçalhos de páginas."""

    return re.sub(r"\s+", " ", line.strip()).casefold()


def _is_index_page(lines: list[str]) -> bool:
    """Indica página referencial que não deve criar capítulos numerados."""

    text = " ".join(lines).casefold()
    return "índice de" in text or "indice de" in text


def remove_repeated_headers(
    pages: list[PageText],
    logger: logging.Logger,
    protected_titles: set[tuple[int, int]] | None = None,
) -> list[PageText]:
    """Remove linhas repetidas no topo/rodapé sem remover títulos detectados."""

    candidates: list[tuple[int, str, str]] = []
    for page in pages:
        lines = [line for line in page.texto.splitlines() if line.strip()]
        for line in lines[:3] + lines[-3:]:
            normalized = _normalized_header(line)
            if normalized:
                candidates.append((page.numero, line, normalized))
    pages_by_header: dict[str, set[int]] = {}
    for page_number, _, normalized in candidates:
        pages_by_header.setdefault(normalized, set()).add(page_number)
    repeated = {
        value for value, page_numbers in pages_by_header.items() if len(page_numbers) >= 2
    }
    if not repeated:
        return pages

    cleaned_pages: list[PageText] = []
    removed = 0
    for page in pages:
        raw_lines = page.texto.splitlines()
        nonempty_indexes = [index for index, line in enumerate(raw_lines) if line.strip()]
        top_bottom = set(nonempty_indexes[:3] + nonempty_indexes[-3:])
        cleaned: list[str] = []
        for index, line in enumerate(raw_lines):
            is_repeated = (
                index in top_bottom and _normalized_header(line) in repeated
            )
            is_title = protected_titles and (page.numero, index) in protected_titles
            if is_repeated and not is_title:
                removed += 1
                continue
            cleaned.append(line)
        cleaned_pages.append(PageText(numero=page.numero, texto="\n".join(cleaned)))
    logger.info("Cabeçalhos repetidos removidos: %d linhas", removed)
    return cleaned_pages


def _majority_page(pages: list[int]) -> int:
    """Retorna a página predominante de um chunk, priorizando a mais antiga."""

    counter = Counter(pages)
    max_count = max(counter.values())
    return min(page for page, count in counter.items() if count == max_count)


def split_words_with_overlap(
    word_pages: list[tuple[str, int]], capitulo: str | None
) -> list[Chunk]:
    """Divide palavras rotuladas por página em chunks sem cortar frases."""

    if not word_pages:
        return []

    words = [word for word, _ in word_pages]
    pages = [page for _, page in word_pages]
    chunks: list[Chunk] = []
    start = 0
    while start < len(words):
        window_words = words[start : start + CHUNK_TARGET_WORDS]
        window_pages = pages[start : start + CHUNK_TARGET_WORDS]
        if start + CHUNK_TARGET_WORDS >= len(words):
            # Último trecho da seção vira um único chunk (sem loop de cauda).
            chunk_text = " ".join(window_words).strip()
            if chunk_text:
                chunks.append(
                    Chunk(
                        conteudo=chunk_text,
                        capitulo=capitulo,
                        pagina_aprox=_majority_page(window_pages),
                    )
                )
            break
        window_text = " ".join(window_words)
        last_period = window_text.rfind(".")
        if last_period != -1:
            window_text = window_text[: last_period + 1]
        chunk_text = window_text.strip()
        consumed = len(window_text.split())
        if consumed <= 0:
            consumed = len(window_words)
        if chunk_text:
            chunks.append(
                Chunk(
                    conteudo=chunk_text,
                    capitulo=capitulo,
                    pagina_aprox=_majority_page(window_pages[:consumed]),
                )
            )
        advance = max(1, consumed - CHUNK_OVERLAP_WORDS)
        start += advance
    return chunks


def build_chunks(pages: list[PageText]) -> list[Chunk]:
    """Quebra o livro por seção lógica rastreando a página de cada palavra."""

    protected_titles = {
        (page.numero, index)
        for page in pages
        for index, line in enumerate(page.texto.splitlines())
        if detect_chapter(line) is not None
    }
    pages = remove_repeated_headers(
        pages, logging.getLogger("processar_livro"), protected_titles
    )
    chunks: list[Chunk] = []
    current_chapter: str | None = None
    buffer: list[tuple[str, int]] = []
    next_numbered_chapter = 1

    def flush() -> None:
        nonlocal buffer
        if buffer:
            chunks.extend(split_words_with_overlap(buffer, current_chapter))
        buffer = []

    for page in pages:
        meaningful_lines = [line for line in page.texto.splitlines() if line.strip()]
        index_page = _is_index_page(meaningful_lines)
        numbered_seen = False
        meaningful_position = 0
        for line in page.texto.splitlines():
            if line.strip():
                chapter = detect_chapter(
                    line,
                    allow_numbered=(
                        not index_page
                        and meaningful_position < 2
                        and not numbered_seen
                    ),
                )
                meaningful_position += 1
            else:
                chapter = None
            numbered = numbered_chapter_number(line) if chapter is not None else None
            if numbered is not None and numbered != next_numbered_chapter:
                chapter = None
            if chapter is not None:
                if NUMBERED_CHAPTER_PATTERN.fullmatch(line.strip()):
                    numbered_seen = True
                    next_numbered_chapter = numbered + 1
                # Só protege a seção quando ela já começou e ainda é curta.
                if buffer and len(buffer) < MIN_CHUNK_WORDS:
                    buffer.extend((word, page.numero) for word in line.split())
                    continue
                flush()
                current_chapter = chapter
                continue
            buffer.extend((word, page.numero) for word in line.split())
    flush()
    return chunks


def is_retryable_error(error: Exception) -> bool:
    """Identifica erros 503/429 elegíveis para nova tentativa."""

    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    text = str(error).lower()
    return (
        status_code in (503, 429)
        or "503" in text
        or "429" in text
        or "high demand" in text
        or "resource has been exhausted" in text
    )


def embed_chunk(client: Any, text: str, logger: logging.Logger) -> list[float]:
    """Gera o embedding de um chunk com retry para erros 503/429."""

    for attempt in range(RETRY_LIMIT):
        try:
            result = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(
                    output_dimensionality=EXPECTED_EMBEDDING_DIMENSION
                ),
            )
            embedding = list(result.embeddings[0].values)
            logger.info("Dimensão do embedding retornado: %d", len(embedding))
            if len(embedding) != EXPECTED_EMBEDDING_DIMENSION:
                raise EmbeddingDimensionError(
                    "Dimensão de embedding incompatível: recebido "
                    f"{len(embedding)}, esperado "
                    f"{EXPECTED_EMBEDDING_DIMENSION} para livros_chunks.embedding"
                )
            return embedding
        except Exception as error:
            if not is_retryable_error(error) or attempt == RETRY_LIMIT - 1:
                raise
            delay = RETRY_BACKOFF_SECONDS[attempt]
            logger.warning(
                "Embedding falhou na tentativa %d/%d; nova tentativa em %ds: %s",
                attempt + 1,
                RETRY_LIMIT,
                delay,
                error,
            )
            time.sleep(delay)
    raise RuntimeError("Geração de embedding encerrada sem resultado")


def insert_chunk(
    client: Client, livro: str, chunk: Chunk, embedding: list[float]
) -> None:
    """Insere um chunk e seu embedding na tabela livros_chunks."""

    client.table("livros_chunks").insert(
        {
            "livro": livro,
            "capitulo": chunk.capitulo,
            "pagina_aprox": chunk.pagina_aprox,
            "conteudo": chunk.conteudo,
            "embedding": embedding,
        }
    ).execute()


def parse_args() -> argparse.Namespace:
    """Interpreta os argumentos de linha de comando."""

    parser = argparse.ArgumentParser(
        description="Processa um livro em PDF em chunks com embeddings."
    )
    parser.add_argument("--pdf", required=True, help="Caminho do arquivo PDF.")
    parser.add_argument("--nome", required=True, help="Nome do livro.")
    parser.add_argument(
        "--forcar-ocr",
        action="store_true",
        help="Pula a extração nativa e usa OCR diretamente.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Extrai e faz chunking sem chamar embedding nem inserir no banco.",
    )
    return parser.parse_args()


def is_indice_chapter(capitulo: str | None) -> bool:
    """Indica se o capítulo é uma seção de índice referencial."""

    if not capitulo:
        return False
    normalized = capitulo.casefold()
    return any(marker in normalized for marker in INDICE_MARKERS)


def filtrar_chunks_indexaveis(chunks: list[Chunk]) -> list[Chunk]:
    """Remove chunks de seções de índice antes de embedding/inserção."""

    return [chunk for chunk in chunks if not is_indice_chapter(chunk.capitulo)]


def resumo_preview(chunks: list[Chunk]) -> dict[str, Any]:
    """Calcula estatísticas de chunking para o modo preview."""

    word_counts = [len(chunk.conteudo.split()) for chunk in chunks]
    total = len(word_counts)
    capitulos: dict[str, dict[str, int]] = {}
    for chunk in chunks:
        key = chunk.capitulo or "(sem capítulo)"
        info = capitulos.setdefault(
            key,
            {
                "chunks": 0,
                "pagina_min": chunk.pagina_aprox,
                "pagina_max": chunk.pagina_aprox,
            },
        )
        info["chunks"] += 1
        info["pagina_min"] = min(info["pagina_min"], chunk.pagina_aprox)
        info["pagina_max"] = max(info["pagina_max"], chunk.pagina_aprox)
    return {
        "total_chunks": total,
        "media_palavras": int(sum(word_counts) / total) if total else 0,
        "min_palavras": min(word_counts) if total else 0,
        "max_palavras": max(word_counts) if total else 0,
        "chunks_abaixo_de_100": sum(1 for count in word_counts if count < 100),
        "capitulos": [
            {
                "capitulo": key,
                "chunks": info["chunks"],
                "pagina_min": info["pagina_min"],
                "pagina_max": info["pagina_max"],
            }
            for key, info in capitulos.items()
        ],
    }


def main() -> None:
    """Executa a extração, o chunking e a ingestão do livro."""

    logger = configure_logging()
    args = parse_args()
    inserted = with_chapter = without_chapter = 0
    embedding_dimension: int | None = None
    try:
        settings = load_settings()
        supabase_client = create_client(
            settings["SUPABASE_URL"], settings["SUPABASE_SERVICE_ROLE_KEY"]
        )
        gemini_client = genai.Client(api_key=settings["GEMINI_API_KEY"])

        pages = resolve_pages(Path(args.pdf), settings, args.forcar_ocr, logger)
        chunks = filtrar_chunks_indexaveis(build_chunks(pages))
        logger.info("Livro '%s' gerou %d chunks", args.nome, len(chunks))

        if args.preview:
            stats = resumo_preview(chunks)
            print(f"Total de chunks gerados: {stats['total_chunks']}")
            print(f"Tamanho médio (palavras): {stats['media_palavras']}")
            print(f"Tamanho mínimo (palavras): {stats['min_palavras']}")
            print(f"Tamanho máximo (palavras): {stats['max_palavras']}")
            print(f"Chunks com menos de 100 palavras: {stats['chunks_abaixo_de_100']}")
            print("Capítulos detectados:")
            for item in stats["capitulos"]:
                print(
                    f"  - {item['capitulo']}: {item['chunks']} chunks, "
                    f"páginas {item['pagina_min']}-{item['pagina_max']}"
                )
            return

        if len(chunks) > MAX_CHUNKS_PER_BOOK:
            logger.error(
                "Chunking gerou %d chunks (limite %d) para '%s'; "
                "abortando antes de qualquer embedding. Revise manualmente.",
                len(chunks),
                MAX_CHUNKS_PER_BOOK,
                args.nome,
            )
            print(
                f"Abortado: {len(chunks)} chunks excedem o limite de "
                f"{MAX_CHUNKS_PER_BOOK}. Revise o chunking antes de reprocessar."
            )
            return

        embed_start = time.time()
        for index, chunk in enumerate(chunks, start=1):
            try:
                embedding = embed_chunk(gemini_client, chunk.conteudo, logger)
                if embedding_dimension is None:
                    embedding_dimension = len(embedding)
                    logger.info(
                        "Dimensão do embedding do primeiro chunk: %d",
                        embedding_dimension,
                    )
                insert_chunk(supabase_client, args.nome, chunk, embedding)
                inserted += 1
                if chunk.capitulo is not None:
                    with_chapter += 1
                else:
                    without_chapter += 1
            except EmbeddingDimensionError:
                logger.error(
                    "Processamento abortado por dimensão de embedding inválida "
                    "no chunk %d:\n%s",
                    index,
                    traceback.format_exc(),
                )
                raise
            except Exception:
                logger.error(
                    "Falha ao processar chunk %d:\n%s",
                    index,
                    traceback.format_exc(),
                )
            if index % PROGRESS_EVERY == 0:
                log_and_print(
                    logger,
                    format_progress(
                        "Embeddings",
                        "chunks",
                        index,
                        len(chunks),
                        time.time() - embed_start,
                    ),
                )
    except Exception:
        logger.error("Falha geral ao processar o livro:\n%s", traceback.format_exc())

    print(f"Chunks inseridos: {inserted}")
    print(f"Chunks com capítulo detectado: {with_chapter}")
    print(f"Chunks sem capítulo identificado: {without_chapter}")
    print(f"Dimensão do embedding: {embedding_dimension if embedding_dimension else 'N/A'}")


if __name__ == "__main__":
    main()
