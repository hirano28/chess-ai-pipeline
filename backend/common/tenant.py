"""Dono dos dados: o `user_id` que toda tabela raiz carrega.

Fase A do multi-tenant (ver D-14 em `docs/DECISOES.md`): as 6 tabelas sem pai
natural gravam `user_id`; as tabelas filhas herdam o dono pela cadeia de FK que
já existe. Enquanto o Supabase Auth não entra (Fase B), o dono é sempre o mesmo
e vem de `DEFAULT_USER_ID`.
"""

from __future__ import annotations

import os

DEFAULT_USER_ID_ENV = "DEFAULT_USER_ID"


def obter_default_user_id() -> str:
    """Devolve o `DEFAULT_USER_ID` do ambiente; erro explícito se faltar.

    Resolvido na hora da escrita, não no import: todo ponto de entrada chama
    `load_dotenv()` dentro do seu `load_settings()` antes de tocar o banco, e
    ler no import capturaria um valor vazio.
    """

    valor = os.getenv(DEFAULT_USER_ID_ENV)
    if not valor:
        raise ValueError(
            f"Variável de ambiente ausente: {DEFAULT_USER_ID_ENV}. "
            "As tabelas raiz exigem user_id (ver D-14 em docs/DECISOES.md)."
        )
    return valor
