"""Gera uma sessão real do Supabase Auth para testar a aplicação localmente (D-53).

Desde o D-25 a API não tem mais chave estática: toda rota exige
`Authorization: Bearer <token>` de uma sessão real. Isso deixou o teste manual
(curl no endpoint, screenshot da tela logada) dependente de um token que
ninguém tinha à mão — e cada sessão de trabalho reescrevia o mesmo script
descartável. Este arquivo encerra isso.

Usa a Admin API para emitir um magic link e trocá-lo por uma sessão, sem
precisar da senha de ninguém. Requer `SUPABASE_URL` e
`SUPABASE_SERVICE_ROLE_KEY` no `.env` — as mesmas credenciais que todo script
de `backend/` já usa.

Uso:
    python backend/common/gerar_sessao_local.py <email>              # imprime o access_token
    python backend/common/gerar_sessao_local.py <email> sessao.json  # grava a sessão completa

O JSON gravado tem o formato que o supabase-js guarda em `localStorage`, para
`frontend/tools/capturar-telas.mjs` injetar e abrir a aplicação já logada.

ATENÇÃO: o token impresso é uma credencial válida. Não cole em log, issue,
commit ou conversa — gere um novo quando precisar.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from supabase import create_client  # noqa: E402

from backend.common.settings import carregar_variaveis_obrigatorias  # noqa: E402

ARQUIVO_ENVIRONMENT = (
    PROJECT_ROOT / "frontend" / "src" / "environments" / "environment.ts"
)


def ler_chave_anon() -> str:
    """Lê a chave `anon` do environment do frontend.

    Ela é pública (vai no bundle) e não está no `.env`, então a fonte de
    verdade é o próprio environment — evita uma segunda cópia para
    dessincronizar.
    """
    texto = ARQUIVO_ENVIRONMENT.read_text(encoding="utf-8")
    achado = re.search(r"supabaseAnonKey:\s*'([^']+)'", texto)
    if not achado:
        raise ValueError(f"supabaseAnonKey não encontrada em {ARQUIVO_ENVIRONMENT}")
    return achado.group(1)


def gerar_sessao(email: str) -> dict:
    """Emite um magic link pela Admin API e o troca por uma sessão real."""
    config = carregar_variaveis_obrigatorias(
        PROJECT_ROOT, "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"
    )

    admin = create_client(config["SUPABASE_URL"], config["SUPABASE_SERVICE_ROLE_KEY"])
    link = admin.auth.admin.generate_link({"type": "magiclink", "email": email})

    # A troca precisa ser feita com a chave anon: é o cliente do navegador que
    # o frontend usa, e é o formato de sessão que ele sabe restaurar.
    anon = create_client(config["SUPABASE_URL"], ler_chave_anon())
    resposta = anon.auth.verify_otp(
        {"token_hash": link.properties.hashed_token, "type": "magiclink"}
    )

    sessao = resposta.session
    if sessao is None:
        raise ValueError(f"O Supabase não devolveu sessão para {email}.")

    return {
        "access_token": sessao.access_token,
        "refresh_token": sessao.refresh_token,
        "token_type": sessao.token_type,
        "expires_in": sessao.expires_in,
        "expires_at": sessao.expires_at,
        "user": json.loads(resposta.user.model_dump_json()),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "uso: python backend/common/gerar_sessao_local.py <email> [saida.json]",
            file=sys.stderr,
        )
        return 2

    email = sys.argv[1]
    sessao = gerar_sessao(email)

    if len(sys.argv) > 2:
        destino = Path(sys.argv[2])
        destino.write_text(json.dumps(sessao), encoding="utf-8")
        # Nunca imprime o token neste caminho: quem pediu arquivo quer o
        # arquivo, e o terminal costuma acabar colado em algum lugar.
        print(f"sessão de {email} gravada em {destino}")
    else:
        print(sessao["access_token"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
