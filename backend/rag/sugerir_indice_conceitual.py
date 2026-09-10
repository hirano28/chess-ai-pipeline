"""Sugere entradas de indice_conceitual via Gemini a partir de livros_chunks.

Este script APENAS gera sugestões (arquivo JSON local); não insere nada em
indice_conceitual nem em nenhuma outra tabela do Supabase.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import google.genai as genai
from dotenv import load_dotenv
from pydantic import BaseModel, TypeAdapter, ValidationError
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.agente2_analista import TAGS_VOCABULARY  # noqa: E402
from backend.common.progress import configurar_encoding_utf8, log_and_print  # noqa: E402

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "sugerir_indice_conceitual.log"
SUGESTOES_DIR = PROJECT_ROOT / "backend" / "rag" / "sugestoes"
MODEL_NAME = "gemini-flash-latest"
PAGE_SIZE = 1000
AMOSTRA_MAX_PALAVRAS = 800
AMOSTRA_MIN_PALAVRAS = 150
RUIDO_EDITORIAL_MARCADORES = ("printed in", "copyright", "isbn", "catalogação", "catalogacao")
SERVER_ERROR_RETRY_LIMIT = 3
SERVER_ERROR_BACKOFF_SECONDS = (5, 15, 45)


class ConceitoSugerido(BaseModel):
    """Um conceito de xadrez sugerido, com resumo curto."""

    conceito: str
    resumo_curto: str


@dataclass(frozen=True)
class Settings:
    """Configurações do Supabase e do Gemini."""

    supabase_url: str
    supabase_service_role_key: str
    gemini_api_key: str


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do sugeridor de índice conceitual."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("sugerir_indice_conceitual")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


def load_settings() -> Settings:
    """Carrega e valida as configurações do ambiente."""

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
    return Settings(
        supabase_url=required["SUPABASE_URL"],  # type: ignore[arg-type]
        supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],  # type: ignore[arg-type]
        gemini_api_key=required["GEMINI_API_KEY"],  # type: ignore[arg-type]
    )


def eh_capitulo_indice(capitulo: str) -> bool:
    """Filtra capítulos de índice/sumário, mesmo critério do processamento."""

    normalizado = capitulo.casefold()
    return "índice de" in normalizado or "indice de" in normalizado


def eh_capitulo_ruido_editorial(capitulo: str) -> bool:
    """Filtra capítulos sem conteúdo instrucional real (ficha técnica, copyright etc.)."""

    normalizado = capitulo.casefold()
    return any(marcador in normalizado for marcador in RUIDO_EDITORIAL_MARCADORES)


def fetch_capitulos_distintos(
    client: Client, livro: str, logger: logging.Logger
) -> list[dict[str, Any]]:
    """Busca capítulos distintos do livro, com min/max de pagina_aprox."""

    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            client.table("livros_chunks")
            .select("capitulo, pagina_aprox")
            .eq("livro", livro)
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        rows.extend(page)
        logger.info(
            "Página de livros_chunks carregada: %d registros (offset %d)",
            len(page),
            offset,
        )
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    agrupado: dict[str, dict[str, int]] = {}
    for row in rows:
        capitulo = row.get("capitulo")
        pagina = row.get("pagina_aprox")
        if (
            not capitulo
            or pagina is None
            or eh_capitulo_indice(capitulo)
            or eh_capitulo_ruido_editorial(capitulo)
        ):
            continue
        info = agrupado.setdefault(capitulo, {"min": pagina, "max": pagina})
        info["min"] = min(info["min"], pagina)
        info["max"] = max(info["max"], pagina)

    return [
        {"capitulo": capitulo, "pagina_min": info["min"], "pagina_max": info["max"]}
        for capitulo, info in sorted(agrupado.items(), key=lambda item: item[1]["min"])
    ]


def fetch_primeiros_chunks(
    client: Client, livro: str, capitulo: str
) -> list[dict[str, Any]]:
    """Busca os 2 primeiros chunks do capítulo, ordenados por pagina_aprox."""

    response = (
        client.table("livros_chunks")
        .select("conteudo, pagina_aprox")
        .eq("livro", livro)
        .eq("capitulo", capitulo)
        .order("pagina_aprox")
        .limit(2)
        .execute()
    )
    return response.data or []


def montar_amostra(chunks: list[dict[str, Any]]) -> str:
    """Concatena os chunks e limita a ~800 palavras."""

    texto = " ".join(chunk.get("conteudo") or "" for chunk in chunks)
    palavras = texto.split()
    return " ".join(palavras[:AMOSTRA_MAX_PALAVRAS])


def build_prompt(amostra: str) -> str:
    """Monta o prompt de sugestão de conceitos para o Gemini."""

    tags_formatadas = "\n".join(f'- "{tag}"' for tag in TAGS_VOCABULARY)
    return f"""Leia este trecho de um livro de xadrez e sugira de 2 a 4 conceitos de
xadrez que ele ensina, cada um com um resumo curto de uma frase.

Responda em português. Os conceitos devem estar em minúsculas e ser curtos
(2 a 4 palavras), como "peça cravada" ou "xeque descoberto".

Considere, quando fizer sentido, alinhar com estes termos já usados no sistema:
{tags_formatadas}

Não é obrigatório usar exatamente esses termos, mas dê preferência quando o
conceito realmente corresponder a um deles.

Responda ESTRITAMENTE com um único JSON válido — uma LISTA de objetos, sem
texto antes ou depois e sem markdown fences, no formato:
[
  {{"conceito": "string", "resumo_curto": "string"}}
]

Trecho do livro:
\"\"\"{amostra}\"\"\"
"""


def strip_json_fences(text: str) -> str:
    """Remove fences markdown caso o modelo as inclua apesar da instrução."""

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def is_server_error_503(error: Exception) -> bool:
    """Identifica erro 503 ou mensagem de alta demanda do SDK Gemini."""

    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    text = str(error).lower()
    return status_code == 503 or "503" in text or "high demand" in text


def call_gemini(client: Any, prompt: str, logger: logging.Logger) -> str:
    """Chama o Gemini, repetindo erros 503 com backoff exponencial."""

    for attempt in range(SERVER_ERROR_RETRY_LIMIT):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME, contents=prompt
            )
            if not response.text:
                raise ValueError("Resposta do Gemini não contém texto")
            return response.text
        except Exception as error:
            if not is_server_error_503(error) or attempt == SERVER_ERROR_RETRY_LIMIT - 1:
                raise
            delay = SERVER_ERROR_BACKOFF_SECONDS[attempt]
            logger.warning(
                "Gemini retornou 503 na tentativa %d/%d; nova tentativa em %ds: %s",
                attempt + 1,
                SERVER_ERROR_RETRY_LIMIT,
                delay,
                error,
            )
            time.sleep(delay)
    raise RuntimeError("Chamada ao Gemini encerrada sem resultado")


def correction_prompt(original_prompt: str, error: ValidationError) -> str:
    """Solicita correção quando o primeiro JSON não valida no Pydantic."""

    return f"""{original_prompt}

A resposta anterior falhou na validação Pydantic com este erro específico:
{error}

Corrija todos os problemas e responda novamente apenas com o JSON válido
(uma lista), sem markdown e sem explicações externas."""


def parse_sugestoes(text: str) -> list[ConceitoSugerido]:
    """Limpa a resposta e valida o JSON (lista) contra ConceitoSugerido."""

    return TypeAdapter(list[ConceitoSugerido]).validate_json(strip_json_fences(text))


def gerar_sugestoes(
    client: Any, prompt: str, logger: logging.Logger
) -> list[ConceitoSugerido]:
    """Chama o Gemini e valida, com uma tentativa extra de correção."""

    response_text = call_gemini(client, prompt, logger)
    try:
        return parse_sugestoes(response_text)
    except ValidationError as validation_error:
        response_text = call_gemini(
            client, correction_prompt(prompt, validation_error), logger
        )
        return parse_sugestoes(response_text)


def sanitize_filename(nome: str) -> str:
    """Converte o nome do livro em um nome de arquivo seguro."""

    return re.sub(r"[^\w\-]+", "_", nome).strip("_")


def imprimir_resumo_capitulo(
    capitulo_info: dict[str, Any], conceitos: list[ConceitoSugerido]
) -> None:
    """Imprime o resumo legível de um capítulo processado."""

    print(
        f"\n{capitulo_info['capitulo']} (páginas {capitulo_info['pagina_min']}"
        f"–{capitulo_info['pagina_max']})"
    )
    for conceito in conceitos:
        print(f"  - {conceito.conceito}: {conceito.resumo_curto}")


def run(livro: str) -> None:
    """Executa a geração de sugestões de índice conceitual para um livro."""

    logger = configure_logging()
    settings = load_settings()
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    gemini_client = genai.Client(api_key=settings.gemini_api_key)

    capitulos = fetch_capitulos_distintos(client, livro, logger)
    log_and_print(logger, f"Capítulos elegíveis em '{livro}': {len(capitulos)}.")

    resultado: list[dict[str, Any]] = []
    processados = falhas = total_sugestoes = 0
    pulados_amostra_curta = 0
    for capitulo_info in capitulos:
        capitulo = capitulo_info["capitulo"]
        try:
            chunks = fetch_primeiros_chunks(client, livro, capitulo)
            amostra = montar_amostra(chunks)
            if len(amostra.split()) < AMOSTRA_MIN_PALAVRAS:
                pulados_amostra_curta += 1
                log_and_print(
                    logger,
                    f"Capítulo '{capitulo}' pulado: amostra com menos de "
                    f"{AMOSTRA_MIN_PALAVRAS} palavras (sem conteúdo instrucional real).",
                )
                continue

            prompt = build_prompt(amostra)
            conceitos = gerar_sugestoes(gemini_client, prompt, logger)

            resultado.append(
                {
                    "capitulo": capitulo,
                    "pagina_min": capitulo_info["pagina_min"],
                    "pagina_max": capitulo_info["pagina_max"],
                    "conceitos_sugeridos": [
                        conceito.model_dump() for conceito in conceitos
                    ],
                }
            )
            imprimir_resumo_capitulo(capitulo_info, conceitos)
            processados += 1
            total_sugestoes += len(conceitos)
            log_and_print(
                logger,
                f"Capítulo '{capitulo}' processado: {len(conceitos)} sugestões.",
            )
        except Exception as error:
            falhas += 1
            logger.exception("Falha ao processar o capítulo '%s'", capitulo)
            log_and_print(logger, f"Capítulo '{capitulo}' falhou: {error}")

    SUGESTOES_DIR.mkdir(parents=True, exist_ok=True)
    saida_path = SUGESTOES_DIR / f"{sanitize_filename(livro)}.json"
    saida_path.write_text(
        json.dumps({"livro": livro, "capitulos": resultado}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log_and_print(
        logger,
        f"Resumo: {processados} capítulos processados, {falhas} falharam, "
        f"{pulados_amostra_curta} pulados por amostra curta, "
        f"{total_sugestoes} sugestões totais geradas. Arquivo: {saida_path}",
    )


def parse_args() -> argparse.Namespace:
    """Interpreta os argumentos de linha de comando."""

    parser = argparse.ArgumentParser(
        description="Sugere entradas de indice_conceitual via Gemini, sem gravar no banco."
    )
    parser.add_argument(
        "--livro", required=True, help="Nome exato do livro em livros_chunks.livro."
    )
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args().livro)
