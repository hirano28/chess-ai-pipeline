"""Prescreve sprints de treino a partir do gargalo do hexágono."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import google.genai as genai
import requests
from dotenv import load_dotenv
from google.genai import types
from pydantic import BaseModel, ValidationError
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.progress import configurar_encoding_utf8, log_and_print  # noqa: E402
from backend.common.tenant import obter_default_user_id  # noqa: E402

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "agente3_prescritor.log"
MODEL_NAME = "gemini-flash-latest"
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768
SERVER_ERROR_RETRY_LIMIT = 3
SERVER_ERROR_BACKOFF_SECONDS = (5, 15, 45)
RAG_MATCH_COUNT = 5
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_MAX_RESULTS = 2

CATEGORY_SEARCH_TERMS: dict[str, list[str]] = {
    "TATICA": [
        "tática",
        "cálculo",
        "peça cravada",
        "peça indefesa",
        "xeque descoberto",
        "segurança do rei",
        "perda de material",
    ],
    "ESTRATEGIA": ["estratégia", "jogo posicional", "centro", "avaliação"],
    "FINAIS": ["final", "finais", "rei ativo", "peão passado"],
    "ESTRUTURA_DE_PEOES": [
        "peão isolado",
        "peão dobrado",
        "cadeia de peões",
        "estrutura de peões",
    ],
    "GESTAO_DE_TEMPO": ["desenvolvimento", "tempo", "iniciativa"],
    "CALCULO": ["segurança do rei", "iniciativa", "profilaxia", "restrição"],
}


class ModuloTreino(BaseModel):
    """Módulo individual de uma sprint de treino."""

    nome: str
    duracao_min: int
    conteudo: str
    livro: str
    capitulo: str
    pagina_aprox: int


class SprintTreino(BaseModel):
    """Sprint de treino estruturada gerada pelo agente."""

    titulo: str
    duracao_total_min: int
    modulos: list[ModuloTreino]


@dataclass(frozen=True)
class Settings:
    """Configurações do agente prescritor."""

    supabase_url: str
    supabase_service_role_key: str
    gemini_api_key: str
    youtube_api_key: str


class EtapaPrescricaoError(RuntimeError):
    """Indica que uma etapa crítica da prescrição não pôde ser concluída."""


class ReferenciaFonteError(ValueError):
    """Indica que uma referência gerada não corresponde ao contexto RAG."""


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do agente prescritor."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("agente3_prescritor")
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
        "YOUTUBE_API_KEY": os.getenv("YOUTUBE_API_KEY"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(missing))
        )
    return Settings(
        supabase_url=required["SUPABASE_URL"],
        supabase_service_role_key=required["SUPABASE_SERVICE_ROLE_KEY"],
        gemini_api_key=required["GEMINI_API_KEY"],
        youtube_api_key=required["YOUTUBE_API_KEY"],
    )


def fetch_latest_analysis(client: Client) -> dict[str, Any] | None:
    """Busca a análise de hexágono mais recente."""

    response = (
        client.table("analises_hexagono")
        .select("*")
        .order("data_analise", desc=True)
        .limit(1)
        .execute()
    )
    data = response.data or []
    return data[0] if data else None


def buscar_conceitos(client: Client, categoria: str) -> list[dict[str, Any]]:
    """Busca conceitos do índice relacionados à categoria via ILIKE."""

    termos = CATEGORY_SEARCH_TERMS.get(categoria, [])
    encontrados: dict[Any, dict[str, Any]] = {}
    for termo in termos:
        response = (
            client.table("indice_conceitual")
            .select("*")
            .ilike("conceito", f"%{termo}%")
            .execute()
        )
        for row in response.data or []:
            chave = row.get("id", row.get("conceito"))
            encontrados[chave] = row
    return list(encontrados.values())


def extrair_livros_capitulos(
    conceitos: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """Extrai livros e capítulos distintos dos conceitos encontrados."""

    livros = sorted({row["livro"] for row in conceitos if row.get("livro")})
    capitulos = sorted({row["capitulo"] for row in conceitos if row.get("capitulo")})
    return livros, capitulos


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


def gerar_embedding_consulta(client: Any, texto: str) -> list[float]:
    """Gera o embedding da consulta com a mesma config do RAG."""

    for attempt in range(SERVER_ERROR_RETRY_LIMIT):
        try:
            result = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=texto,
                config=types.EmbedContentConfig(
                    output_dimensionality=EMBEDDING_DIMENSION
                ),
            )
            return list(result.embeddings[0].values)
        except Exception as error:
            if not is_retryable_error(error) or attempt == SERVER_ERROR_RETRY_LIMIT - 1:
                raise
            time.sleep(SERVER_ERROR_BACKOFF_SECONDS[attempt])
    raise RuntimeError("Geração de embedding encerrada sem resultado")


def buscar_chunks_similares(
    client: Client,
    embedding: list[float],
    livros: list[str],
    capitulos: list[str],
) -> list[dict[str, Any]]:
    """Busca chunks similares via RPC pgvector restrita a livro/capítulo."""

    response = client.rpc(
        "match_livros_chunks",
        {
            "query_embedding": embedding,
            "filtro_livros": livros or None,
            "filtro_capitulos": capitulos or None,
            "match_count": RAG_MATCH_COUNT,
        },
    ).execute()
    chunks = response.data or []
    if not chunks:
        raise ValueError("A busca vetorial no RAG não retornou nenhum trecho")
    return chunks


def buscar_videos_youtube(
    api_key: str, query: str, logger: logging.Logger
) -> list[dict[str, str]]:
    """Busca vídeos curtos/médios no YouTube; falha não interrompe o fluxo."""

    try:
        response = requests.get(
            YOUTUBE_SEARCH_URL,
            params={
                "key": api_key,
                "q": query,
                "part": "snippet",
                "type": "video",
                "videoDuration": "medium",
                "maxResults": 5,
                "order": "relevance",
            },
            timeout=30,
        )
        response.raise_for_status()
        videos: list[dict[str, str]] = []
        for item in response.json().get("items", []):
            video_id = (item.get("id") or {}).get("videoId")
            snippet = item.get("snippet") or {}
            if not video_id:
                continue
            videos.append(
                {
                    "titulo": snippet.get("title", ""),
                    "canal": snippet.get("channelTitle", ""),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
            )
            if len(videos) >= YOUTUBE_MAX_RESULTS:
                break
        return videos
    except Exception:
        log_and_print(
            logger,
            "ERRO na Etapa 3/6 (busca de vídeos no YouTube); "
            "seguindo sem vídeos, pois esta etapa é opcional.\n"
            f"{traceback.format_exc()}",
        )
        return []


def top_tags(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrai as top 3 tags das métricas da análise."""

    metricas = analysis.get("metricas") or {}
    if isinstance(metricas, str):
        try:
            metricas = json.loads(metricas)
        except json.JSONDecodeError:
            metricas = {}
    return metricas.get("top_3_tags", []) if isinstance(metricas, dict) else []


def build_query_text(categoria: str, tags: list[dict[str, Any]]) -> str:
    """Monta o texto de consulta a partir da categoria e das tags."""

    nomes = " ".join(str(tag.get("tag", "")).replace("_", " ") for tag in tags)
    return f"xadrez {categoria.replace('_', ' ').lower()} {nomes}".strip()


def strip_json_fences(text: str) -> str:
    """Remove fences markdown caso o modelo as inclua."""

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def call_gemini(client: Any, prompt: str, logger: logging.Logger) -> str:
    """Chama o Gemini repetindo erros 503/429 com backoff."""

    for attempt in range(SERVER_ERROR_RETRY_LIMIT):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME, contents=prompt
            )
            if not response.text:
                raise ValueError("Resposta do Gemini vazia")
            return response.text
        except Exception as error:
            if not is_retryable_error(error) or attempt == SERVER_ERROR_RETRY_LIMIT - 1:
                raise
            delay = SERVER_ERROR_BACKOFF_SECONDS[attempt]
            logger.warning(
                "Gemini falhou (503/429) tentativa %d/%d; retry em %ds: %s",
                attempt + 1,
                SERVER_ERROR_RETRY_LIMIT,
                delay,
                error,
            )
            time.sleep(delay)
    raise RuntimeError("Chamada ao Gemini encerrada sem resultado")


def build_prompt(
    categoria: str,
    tags: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    videos: list[dict[str, str]],
) -> str:
    """Monta o prompt da sprint com contexto de RAG e vídeos."""

    contexto = {
        "gargalo": categoria,
        "top_3_tags": tags,
        "trechos_livro": [
            {
                "livro": chunk.get("livro"),
                "capitulo": chunk.get("capitulo"),
                "pagina_aprox": chunk.get("pagina_aprox"),
                "conteudo": chunk.get("conteudo"),
            }
            for chunk in chunks
        ],
        "videos": videos,
    }
    return (
        "Você é um treinador de xadrez. Monte uma sprint de treino de 45 a 60 "
        "minutos dividida em até 3 módulos (Teoria, Prática, Fixação) para "
        "atacar o gargalo do aluno.\n\n"
        "Regras:\n"
        "- Responda ESTRITAMENTE em JSON compatível com o schema abaixo, sem "
        "markdown fences e sem texto antes ou depois.\n"
        "- Em cada módulo, preencha livro, capitulo e pagina_aprox usando uma "
        "referência fornecida no contexto.\n"
        "- Use EXCLUSIVAMENTE os valores de livro, capitulo e pagina_aprox "
        "fornecidos no contexto abaixo para qualquer citação. NÃO use "
        "conhecimento próprio sobre o livro, mesmo que você reconheça a obra "
        "ou ache que sabe o nome 'correto' do capítulo ou a página real. "
        "Copie o valor de capitulo e pagina_aprox literalmente como aparecem "
        "no contexto, mesmo que pareçam malformados por OCR.\n"
        "- A soma das durações dos módulos deve ficar entre 45 e 60.\n\n"
        "Schema:\n"
        "{\n"
        '  "titulo": "string",\n'
        '  "duracao_total_min": int,\n'
        '  "modulos": [\n'
        '    {"nome": "string", "duracao_min": int, "conteudo": "string", '
        '"livro": "string", "capitulo": "string", '
        '"pagina_aprox": int}\n'
        "  ]\n"
        "}\n\n"
        f"Contexto:\n{json.dumps(contexto, ensure_ascii=False, indent=2)}"
    )


def format_referencias_aceitas(chunks: list[dict[str, Any]]) -> str:
    """Formata os metadados RAG que podem ser usados pelo modelo."""

    referencias = [
        {
            "livro": chunk.get("livro"),
            "capitulo": chunk.get("capitulo"),
            "pagina_aprox": chunk.get("pagina_aprox"),
        }
        for chunk in chunks
    ]
    return json.dumps(referencias, ensure_ascii=False, indent=2)


def validar_referencias_sprint(
    sprint: SprintTreino, chunks: list[dict[str, Any]]
) -> None:
    """Garante que as referências geradas correspondem aos chunks recuperados."""

    for indice_modulo, modulo in enumerate(sprint.modulos, start=1):
        referencia_valida = any(
            modulo.livro == chunk.get("livro")
            and modulo.capitulo == chunk.get("capitulo")
            and isinstance(chunk.get("pagina_aprox"), int)
            and abs(modulo.pagina_aprox - chunk["pagina_aprox"]) <= 2
            for chunk in chunks
        )
        if not referencia_valida:
            raise ReferenciaFonteError(
                f"Módulo {indice_modulo} contém referência não encontrada nos "
                f"chunks: livro={modulo.livro!r}, capitulo={modulo.capitulo!r}, "
                f"pagina_aprox={modulo.pagina_aprox!r}."
            )


def correction_prompt(
    original_prompt: str,
    error: Exception,
    chunks: list[dict[str, Any]],
) -> str:
    """Solicita correção quando o JSON não valida no Pydantic."""

    return (
        f"{original_prompt}\n\n"
        "A resposta anterior falhou na validação Pydantic com este erro:\n"
        f"{error}\n\n"
        "Use somente estas referências aceitas, copiando livro e capitulo "
        "literalmente e usando pagina_aprox igual ou no máximo 2 páginas "
        "distante do valor correspondente:\n"
        f"{format_referencias_aceitas(chunks)}\n\n"
        "Corrija e responda novamente apenas com o JSON válido, sem markdown."
    )


def parse_sprint(text: str) -> SprintTreino:
    """Valida a resposta contra o schema SprintTreino."""

    return SprintTreino.model_validate_json(strip_json_fences(text))


def gerar_resposta_sprint(
    gemini_client: Any,
    categoria: str,
    tags: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    videos: list[dict[str, str]],
    logger: logging.Logger,
) -> tuple[str, str]:
    """Gera a resposta inicial do Gemini para a sprint."""

    prompt = build_prompt(categoria, tags, chunks, videos)
    return prompt, call_gemini(gemini_client, prompt, logger)


def validar_sprint(
    gemini_client: Any,
    prompt: str,
    response_text: str,
    chunks: list[dict[str, Any]],
    logger: logging.Logger,
) -> SprintTreino:
    """Valida schema e referências, solicitando uma correção uma vez."""

    try:
        sprint = parse_sprint(response_text)
        validar_referencias_sprint(sprint, chunks)
        return sprint
    except (ValidationError, ReferenciaFonteError) as error:
        response_text = call_gemini(
            gemini_client, correction_prompt(prompt, error, chunks), logger
        )
        sprint = parse_sprint(response_text)
        validar_referencias_sprint(sprint, chunks)
        return sprint


def executar_etapa_critica(
    logger: logging.Logger, etapa: int, descricao: str, acao: Callable[[], Any]
) -> Any:
    """Executa uma etapa crítica, registrando o traceback e interrompendo o fluxo."""

    try:
        return acao()
    except Exception as error:
        log_and_print(
            logger,
            f"ERRO na Etapa {etapa}/6 ({descricao}); execução interrompida.\n"
            f"{traceback.format_exc()}",
        )
        raise EtapaPrescricaoError(
            f"Etapa {etapa}/6 falhou: {descricao}. Consulte o traceback acima."
        ) from error


def referencia_livro(chunks: list[dict[str, Any]]) -> str:
    """Monta uma referência textual do primeiro chunk recuperado."""

    if not chunks:
        return "sem referência de livro"
    chunk = chunks[0]
    return (
        f"{chunk.get('livro', '?')} - {chunk.get('capitulo', '?')} "
        f"(pág. {chunk.get('pagina_aprox', '?')})"
    )


def salvar_sessao(
    client: Client, categoria: str, sprint: SprintTreino
) -> None:
    """Persiste a sprint gerada na tabela sessoes_treino."""

    client.table("sessoes_treino").insert(
        {
            "diagnostico_gargalo": f"{categoria}: {sprint.titulo}",
            "modulos": sprint.model_dump(),
            "user_id": obter_default_user_id(),
        }
    ).execute()


def main() -> None:
    """Executa a prescrição de treino e imprime o resumo final."""

    logger = configure_logging()
    categoria = ""
    sprint: SprintTreino | None = None
    videos: list[dict[str, str]] = []
    referencia = "sem referência de livro"
    try:
        settings = load_settings()
        supabase_client = create_client(
            settings.supabase_url, settings.supabase_service_role_key
        )
        gemini_client = genai.Client(api_key=settings.gemini_api_key)

        analysis = fetch_latest_analysis(supabase_client)
        categoria = (analysis or {}).get("gargalo_sistemico_atual") or ""
        if not categoria:
            log_and_print(
                logger,
                "Nenhum gargalo sistêmico identificado (dados insuficientes); "
                "sprint não gerada.",
            )
            return

        log_and_print(logger, f"Etapa 1/6: buscando conceitos para {categoria}...")
        conceitos, livros, capitulos = executar_etapa_critica(
            logger,
            1,
            "busca de conceitos no índice conceitual",
            lambda: (
                conceitos := buscar_conceitos(supabase_client, categoria),
                *extrair_livros_capitulos(conceitos),
            ),
        )
        log_and_print(
            logger,
            f"Etapa 1/6: {len(conceitos)} conceitos, {len(livros)} livros.",
        )

        tags = top_tags(analysis)
        log_and_print(logger, "Etapa 2/6: busca vetorial no RAG...")
        chunks = executar_etapa_critica(
            logger,
            2,
            "busca vetorial no RAG via RPC match_livros_chunks",
            lambda: buscar_chunks_similares(
                supabase_client,
                gerar_embedding_consulta(
                    gemini_client, build_query_text(categoria, tags)
                ),
                livros,
                capitulos,
            ),
        )
        referencia = referencia_livro(chunks)
        log_and_print(logger, f"Etapa 2/6: {len(chunks)} trechos recuperados.")

        query_video = (
            f"xadrez {categoria.replace('_', ' ').lower()} "
            f"{tags[0]['tag'].replace('_', ' ') if tags else ''}".strip()
        )
        log_and_print(logger, "Etapa 3/6: busca de vídeos no YouTube...")
        videos = buscar_videos_youtube(settings.youtube_api_key, query_video, logger)
        log_and_print(logger, f"Etapa 3/6: {len(videos)} vídeos encontrados.")

        log_and_print(logger, "Etapa 4/6: gerando sprint via Gemini...")
        prompt, response_text = executar_etapa_critica(
            logger,
            4,
            "geração da sprint via Gemini",
            lambda: gerar_resposta_sprint(
                gemini_client, categoria, tags, chunks, videos, logger
            ),
        )
        sprint = executar_etapa_critica(
            logger,
            5,
            "validação da sprint gerada",
            lambda: validar_sprint(
                gemini_client, prompt, response_text, chunks, logger
            ),
        )
        log_and_print(logger, "Etapa 5/6: sprint validada com sucesso.")

        executar_etapa_critica(
            logger,
            6,
            "persistência da sessão em sessoes_treino",
            lambda: salvar_sessao(supabase_client, categoria, sprint),
        )
        log_and_print(logger, "Etapa 6/6: sessão persistida em sessoes_treino.")
    except EtapaPrescricaoError as error:
        log_and_print(logger, str(error))
        return
    except Exception:
        log_and_print(
            logger,
            "ERRO antes ou fora das seis etapas da prescrição; execução "
            "interrompida.\n"
            f"{traceback.format_exc()}",
        )
        return

    print(f"Gargalo: {categoria or 'dados insuficientes'}")
    if sprint is not None:
        print(f"Sprint: {sprint.titulo}")
        print(f"Módulos: {len(sprint.modulos)}")
    else:
        print("Sprint: não gerada")
    print(f"Vídeo do YouTube: {'sim' if videos else 'não'}")
    print(f"Referência de livro citada: {referencia}")


if __name__ == "__main__":
    main()
