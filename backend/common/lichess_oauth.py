"""Leitura de tokens OAuth do Lichess salvos por usuário (D-33).

Movido de `backend/api/api_server.py` no Estágio 2 (D-34): tanto a API quanto
os scripts de ingestão (`importar_puzzle_activity.py`) precisam ler
`lichess_oauth_tokens`, e um script de ingestão não deve importar o módulo da
API (que carrega FastAPI, Gemini, Stockfish) só para reaproveitar uma função.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from supabase import Client

# Margem de segurança ao checar validade: um token que expira "daqui a 30s" não
# deve ser entregue a quem vai usá-lo numa chamada que pode demorar mais que isso.
MARGEM_EXPIRACAO_SEG = 60


def obter_access_token_lichess(client: Client, user_id: str) -> str | None:
    """Devolve o access_token do Lichess de `user_id`, ou None se não servir mais.

    É o ponto único por onde qualquer consumidor deve pegar o token, justamente
    para a checagem de validade nunca ser esquecida.

    Não existe renovação automática: a doc oficial do Lichess diz que refresh
    tokens **não são suportados** (o access_token já nasce com validade de ~1
    ano). Então não há o que renovar — token expirado, revogado ou inexistente
    devolve None, e a única saída é a pessoa reconectar a conta pelo fluxo
    OAuth de novo. Ver D-33 em `DECISOES.md`.
    """

    resposta = (
        client.table("lichess_oauth_tokens")
        .select("access_token, expires_at")
        .eq("user_id", user_id)
        .execute()
    )
    linhas = resposta.data or []
    if not linhas:
        return None

    linha = linhas[0]
    expires_at = linha.get("expires_at")
    if expires_at:
        limite = datetime.fromisoformat(expires_at)
        agora = datetime.now(timezone.utc) + timedelta(seconds=MARGEM_EXPIRACAO_SEG)
        if limite <= agora:
            return None
    return linha.get("access_token")


def listar_usuarios_com_token_lichess_valido(client: Client) -> list[dict[str, Any]]:
    """Lista `user_id` com uma linha não expirada em `lichess_oauth_tokens`.

    Filtro no banco (`expires_at > agora`) é só uma pré-seleção para não
    percorrer contas já mortas há tempo — quem consome o resultado ainda deve
    chamar `obter_access_token_lichess` antes de usar o token (ela aplica a
    margem de segurança de `MARGEM_EXPIRACAO_SEG` e é a autoridade final sobre
    "esse token serve").
    """

    agora = datetime.now(timezone.utc).isoformat()
    resposta = (
        client.table("lichess_oauth_tokens")
        .select("user_id, expires_at")
        .gt("expires_at", agora)
        .execute()
    )
    return resposta.data or []
