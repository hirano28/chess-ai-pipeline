"""Pergunta em texto livre respondida com os livros já indexados (D-81).

Diferença essencial para o Agente 3 (`agente3_prescritor.py`): lá a busca
vetorial é RESTRITA aos livros e capítulos que `buscar_conceitos()` devolveu
para a categoria do gargalo — é uma prescrição, e o recorte é justamente o
ponto. Aqui a busca varre o corpus inteiro, sem filtro, porque a pergunta é
de quem está na frente da tela e não há como saber de antemão em que livro
está a resposta.

O embedding, o retry de 503/429 e a limpeza de fences são importados do
Agente 3 de propósito: o vetor da pergunta PRECISA sair do mesmo modelo e da
mesma dimensionalidade com que os chunks foram gravados, senão a distância
`<=>` compara dois espaços diferentes e a busca devolve lixo plausível.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from supabase import Client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.agente3_prescritor import (  # noqa: E402
    call_gemini,
    gerar_embedding_consulta,
    strip_json_fences,
)

MODEL_NAME = "gemini-flash-latest"
RAG_MATCH_COUNT = 6
# Tolerância de página ao conferir uma citação contra o chunk de origem. Mesmo
# valor do Agente 3: `pagina_aprox` é aproximada por construção (o chunk cobre
# mais de uma página), então exigir igualdade exata reprovaria citação correta.
TOLERANCIA_PAGINA = 2
PERGUNTA_MAX_CARACTERES = 500
TRECHO_FALLBACK_CARACTERES = 400


class FonteBiblioteca(BaseModel):
    """Referência a um trecho real de livro."""

    livro: str
    capitulo: str | None = None
    pagina_aprox: int | None = None


class RespostaBiblioteca(BaseModel):
    """Resposta redigida pelo modelo, ancorada nos trechos recuperados."""

    resposta: str
    fontes: list[FonteBiblioteca]


class FonteBibliotecaError(ValueError):
    """Uma fonte citada não corresponde a nenhum trecho recuperado."""


class PerguntaInvalidaError(ValueError):
    """A pergunta chegou vazia ou longa demais."""


def normalizar_pergunta(pergunta: str) -> str:
    """Valida e normaliza a pergunta do usuário."""

    limpa = (pergunta or "").strip()
    if not limpa:
        raise PerguntaInvalidaError("Escreva uma pergunta para consultar os livros.")
    if len(limpa) > PERGUNTA_MAX_CARACTERES:
        raise PerguntaInvalidaError(
            f"Pergunta longa demais (máximo {PERGUNTA_MAX_CARACTERES} caracteres)."
        )
    return limpa


def buscar_trechos(
    client: Client, embedding: list[float], match_count: int = RAG_MATCH_COUNT
) -> list[dict[str, Any]]:
    """Busca os trechos mais próximos no corpus INTEIRO, sem filtro de livro."""

    response = client.rpc(
        "match_livros_chunks",
        {
            "query_embedding": embedding,
            "filtro_livros": None,
            "filtro_capitulos": None,
            "match_count": match_count,
        },
    ).execute()
    return response.data or []


def build_prompt(pergunta: str, trechos: list[dict[str, Any]]) -> str:
    """Monta o prompt com os trechos recuperados como única fonte permitida."""

    contexto = [
        {
            "livro": trecho.get("livro"),
            "capitulo": trecho.get("capitulo"),
            "pagina_aprox": trecho.get("pagina_aprox"),
            "conteudo": trecho.get("conteudo"),
        }
        for trecho in trechos
    ]
    return (
        "Você é um treinador de xadrez respondendo à pergunta de um aluno "
        "usando APENAS os trechos de livro fornecidos abaixo.\n\n"
        "Regras:\n"
        "- Responda ESTRITAMENTE em JSON compatível com o schema abaixo, sem "
        "markdown fences e sem texto antes ou depois.\n"
        "- Baseie a resposta somente nos trechos fornecidos. Se eles não "
        "responderem à pergunta, diga isso na resposta em vez de completar "
        "com conhecimento próprio.\n"
        "- Em `fontes`, liste apenas os trechos que você de fato usou, "
        "copiando `livro`, `capitulo` e `pagina_aprox` LITERALMENTE como "
        "aparecem no contexto, mesmo que pareçam malformados por OCR. NÃO "
        "use conhecimento próprio sobre a obra para 'corrigir' um nome de "
        "capítulo ou um número de página.\n"
        "- Escreva a resposta em português do Brasil, em 1 a 3 parágrafos.\n\n"
        "Schema:\n"
        "{\n"
        '  "resposta": "string",\n'
        '  "fontes": [{"livro": "string", "capitulo": "string", '
        '"pagina_aprox": int}]\n'
        "}\n\n"
        f"Pergunta do aluno:\n{pergunta}\n\n"
        f"Trechos disponíveis:\n{json.dumps(contexto, ensure_ascii=False, indent=2)}"
    )


def _fonte_confere(fonte: FonteBiblioteca, trecho: dict[str, Any]) -> bool:
    """Diz se a fonte citada corresponde a este trecho recuperado."""

    if fonte.livro != trecho.get("livro"):
        return False
    capitulo_real = trecho.get("capitulo")
    if (fonte.capitulo or None) != (capitulo_real or None):
        return False
    pagina_real = trecho.get("pagina_aprox")
    if fonte.pagina_aprox is None or not isinstance(pagina_real, int):
        return fonte.pagina_aprox is None and pagina_real is None
    return abs(fonte.pagina_aprox - pagina_real) <= TOLERANCIA_PAGINA


def validar_fontes(
    resposta: RespostaBiblioteca, trechos: list[dict[str, Any]]
) -> None:
    """Garante que toda fonte citada existe entre os trechos recuperados (R2)."""

    for indice, fonte in enumerate(resposta.fontes, start=1):
        if not any(_fonte_confere(fonte, trecho) for trecho in trechos):
            raise FonteBibliotecaError(
                f"Fonte {indice} não corresponde a nenhum trecho recuperado: "
                f"livro={fonte.livro!r}, capitulo={fonte.capitulo!r}, "
                f"pagina_aprox={fonte.pagina_aprox!r}."
            )


def correction_prompt(
    prompt_original: str, erro: Exception, trechos: list[dict[str, Any]]
) -> str:
    """Pede correção informando quais referências são aceitáveis."""

    referencias = [
        {
            "livro": trecho.get("livro"),
            "capitulo": trecho.get("capitulo"),
            "pagina_aprox": trecho.get("pagina_aprox"),
        }
        for trecho in trechos
    ]
    return (
        f"{prompt_original}\n\n"
        "A resposta anterior foi rejeitada com este erro:\n"
        f"{erro}\n\n"
        "Use somente estas referências, copiando livro e capitulo "
        "literalmente e usando pagina_aprox igual ou no máximo "
        f"{TOLERANCIA_PAGINA} páginas distante do valor correspondente:\n"
        f"{json.dumps(referencias, ensure_ascii=False, indent=2)}\n\n"
        "Corrija e responda novamente apenas com o JSON válido, sem markdown."
    )


def resposta_de_fallback(trechos: list[dict[str, Any]]) -> RespostaBiblioteca:
    """Formata os trechos reais literalmente, sem LLM (fallback da R2).

    Usado quando o modelo erra a citação duas vezes seguidas. Devolver o
    material cru é pior de ler, mas é honesto: cada linha aqui saiu do banco,
    não do modelo.
    """

    linhas: list[str] = [
        "Não consegui redigir uma resposta confiável para esta pergunta. "
        "Estes são os trechos mais próximos que existem nos livros indexados:"
    ]
    fontes: list[FonteBiblioteca] = []
    for trecho in trechos:
        conteudo = (trecho.get("conteudo") or "").strip()
        if len(conteudo) > TRECHO_FALLBACK_CARACTERES:
            conteudo = conteudo[:TRECHO_FALLBACK_CARACTERES].rstrip() + "..."
        cabecalho = str(trecho.get("livro") or "?")
        if trecho.get("capitulo"):
            cabecalho += f" — {trecho['capitulo']}"
        if trecho.get("pagina_aprox") is not None:
            cabecalho += f" (pág. {trecho['pagina_aprox']})"
        linhas.append(f"\n{cabecalho}\n{conteudo}")
        fontes.append(
            FonteBiblioteca(
                livro=str(trecho.get("livro") or "?"),
                capitulo=trecho.get("capitulo"),
                pagina_aprox=trecho.get("pagina_aprox"),
            )
        )
    return RespostaBiblioteca(resposta="\n".join(linhas), fontes=fontes)


def gerar_resposta(
    gemini_client: Any,
    pergunta: str,
    trechos: list[dict[str, Any]],
    logger: logging.Logger | None = None,
) -> RespostaBiblioteca:
    """Gera a resposta, valida as citações e corrige uma vez antes de desistir."""

    prompt = build_prompt(pergunta, trechos)
    texto = call_gemini(gemini_client, prompt, logger or logging.getLogger(__name__))
    try:
        resposta = RespostaBiblioteca.model_validate_json(strip_json_fences(texto))
        validar_fontes(resposta, trechos)
        return resposta
    except (ValidationError, FonteBibliotecaError) as erro:
        texto = call_gemini(
            gemini_client,
            correction_prompt(prompt, erro, trechos),
            logger or logging.getLogger(__name__),
        )
    try:
        resposta = RespostaBiblioteca.model_validate_json(strip_json_fences(texto))
        validar_fontes(resposta, trechos)
        return resposta
    except (ValidationError, FonteBibliotecaError):
        return resposta_de_fallback(trechos)


def consultar_biblioteca(
    supabase_client: Client,
    gemini_client: Any,
    pergunta: str,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Responde a pergunta com os livros indexados; devolve resposta e fontes."""

    pergunta_limpa = normalizar_pergunta(pergunta)
    embedding = gerar_embedding_consulta(gemini_client, pergunta_limpa)
    trechos = buscar_trechos(supabase_client, embedding)
    if not trechos:
        return {
            "pergunta": pergunta_limpa,
            "resposta": (
                "Nenhum livro indexado tem trecho parecido com essa pergunta."
            ),
            "fontes": [],
        }
    resposta = gerar_resposta(gemini_client, pergunta_limpa, trechos, logger)
    return {
        "pergunta": pergunta_limpa,
        "resposta": resposta.resposta,
        "fontes": [fonte.model_dump() for fonte in resposta.fontes],
    }


def salvar_consulta(
    client: Client, resultado: dict[str, Any], user_id: str
) -> str | None:
    """Persiste a consulta e devolve o id da linha criada."""

    resposta = (
        client.table("consultas_biblioteca")
        .insert(
            {
                "user_id": user_id,
                "pergunta": resultado["pergunta"],
                "resposta": {
                    "resposta": resultado["resposta"],
                    "fontes": resultado["fontes"],
                },
            }
        )
        .execute()
    )
    linhas = resposta.data or []
    return linhas[0].get("id") if linhas else None
