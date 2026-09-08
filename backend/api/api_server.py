"""Servidor HTTP local (FastAPI) que expõe a revisão de exercícios avulsos.

Reaproveita processar_revisao_avulsa, resolver_posicao e salvar_exercicio de
backend/agentes/revisar_exercicio_avulso.py - a mesma lógica usada pelo
script interativo de linha de comando. Nenhum comportamento do script
interativo foi alterado; ele continua funcionando standalone.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

import chess
import google.genai as genai
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from stockfish import Stockfish


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.revisar_exercicio_avulso import (  # noqa: E402
    EngineIndisponivelError,
    configure_console_logger,
    normalizar_lances,
    processar_revisao_sequencia,
    resolver_posicao,
    salvar_exercicio,
)
from backend.agentes.revisar_pensamento import load_settings  # noqa: E402
from backend.ingestao.common_ingestao import create_supabase_client  # noqa: E402

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:4200",
    "https://chess-ai-pipeline.vercel.app",
)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS)).split(",")
    if origin.strip()
]

app = FastAPI(title="Chess AI Pipeline - API de revisão avulsa")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Recursos inicializados uma única vez na subida do servidor (ver startup/shutdown).
_state: dict[str, Any] = {}


class RevisarAvulsoRequest(BaseModel):
    """Payload de entrada: posição (FEN ou PGN), lance(s) e pensamento do jogador.

    Aceita 'lance' (string única, compat) OU 'lances' (lista SAN na ordem em que
    ocorrem a partir da posição). Quando ambos vêm, 'lances' tem prioridade.
    """

    posicao: str
    lance: str | None = None
    lances: list[str] | None = None
    pensamento: str


class AvaliacaoSequenciaItem(BaseModel):
    """Avaliação de um único lance DO JOGADOR dentro da sequência."""

    indice_na_sequencia: int
    lance_jogado: str
    melhor_lance: str | None
    queda_win_percent: float
    qualidade_lance: str
    qualidade_raciocinio: str
    feedback_texto: str
    analise_mestre: str
    top_candidatos: list[dict] = Field(default_factory=list)


class RevisarAvulsoResponse(BaseModel):
    """Resultado da revisão de uma sequência, pronto para exibição no dashboard.

    'avaliacoes' tem um item por lance DO JOGADOR (para um lance único, 1 item).
    'lances' lista todos os lances aplicados (jogador + adversário), em SAN.
    """

    fen: str
    lances: list[str]
    avaliacoes: list[AvaliacaoSequenciaItem]
    resumo_geral: str | None = None


class SalvarAvulsoRequest(BaseModel):
    """Payload de um exercício (um lance do jogador) a persistir, mais fen/pensamento."""

    lance_jogado: str
    melhor_lance: str | None
    queda_win_percent: float
    qualidade_lance: str
    qualidade_raciocinio: str
    feedback_texto: str
    analise_mestre: str
    top_candidatos: list[dict] = Field(default_factory=list)
    fen: str
    texto_pensamento: str


@app.on_event("startup")
def iniciar_recursos() -> None:
    """Inicializa Stockfish, Gemini e Supabase uma única vez para todo o servidor."""

    settings = load_settings()
    _state["settings"] = settings
    _state["logger"] = configure_console_logger()
    _state["gemini_client"] = genai.Client(api_key=settings.gemini_api_key)
    _state["supabase_client"] = create_supabase_client(
        settings.supabase_url, settings.supabase_service_role_key
    )
    _state["engine"] = Stockfish(
        path=settings.stockfish_path,
        depth=settings.stockfish_depth,
        turn_perspective=False,
    )
    # Serializa o acesso ao engine compartilhado entre requisições concorrentes.
    _state["engine_lock"] = threading.Lock()

    api_secret_key = os.getenv("API_SECRET_KEY")
    if not api_secret_key:
        raise RuntimeError(
            "Variável de ambiente API_SECRET_KEY é obrigatória para subir o servidor."
        )
    _state["api_secret_key"] = api_secret_key


@app.on_event("shutdown")
def encerrar_recursos() -> None:
    """Fecha o Stockfish corretamente ao desligar o servidor."""

    engine = _state.get("engine")
    if engine is not None:
        try:
            engine.send_quit_command()
        except Exception:
            pass


def verificar_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Valida X-API-Key ANTES de qualquer rota executar (Stockfish/Gemini/Supabase).

    Como dependency do FastAPI, roda antes do corpo da função da rota, garantindo
    que requisições não autorizadas não consomem tempo de engine nem cota de API.
    """

    api_secret_key = _state.get("api_secret_key")
    if not api_secret_key or x_api_key != api_secret_key:
        raise HTTPException(status_code=401, detail="Chave de API ausente ou inválida.")


@app.post(
    "/revisar-avulso",
    response_model=RevisarAvulsoResponse,
    dependencies=[Depends(verificar_api_key)],
)
def revisar_avulso(payload: RevisarAvulsoRequest) -> RevisarAvulsoResponse:
    """Avalia um exercício avulso (lance único ou sequência) e retorna o feedback."""

    try:
        lances_san = normalizar_lances(payload.lances, payload.lance)
        board = resolver_posicao(payload.posicao)
        fen = board.fen()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        resultado = processar_revisao_sequencia(
            _state["engine"],
            _state["gemini_client"],
            _state["settings"],
            _state["logger"],
            fen,
            lances_san,
            payload.pensamento,
            _state["engine_lock"],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except EngineIndisponivelError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao processar a revisão: {error}"
        ) from error

    return RevisarAvulsoResponse(**resultado)


@app.post("/revisar-avulso/salvar", dependencies=[Depends(verificar_api_key)])
def revisar_avulso_salvar(payload: SalvarAvulsoRequest) -> dict[str, str]:
    """Persiste um exercício já revisado em revisao_exercicio_avulso."""

    resultado = {
        "lance_jogado": payload.lance_jogado,
        "melhor_lance": payload.melhor_lance,
        "queda_win_percent": payload.queda_win_percent,
        "qualidade_lance": payload.qualidade_lance,
        "qualidade_raciocinio": payload.qualidade_raciocinio,
        "feedback_texto": payload.feedback_texto,
    }
    try:
        salvar_exercicio(
            _state["supabase_client"], payload.fen, payload.texto_pensamento, resultado
        )
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao salvar o exercício: {error}"
        ) from error

    return {"status": "salvo"}
