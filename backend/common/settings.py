"""Carregamento e validação de variáveis de ambiente obrigatórias,
compartilhado por todo `load_settings()` do pipeline.

Antes de uma auditoria de qualidade pós-D-49, ~18 scripts (backend/agentes/,
backend/ingestao/, backend/rag/, backend/analise_engine/) reimplementavam a
mesma sequência (load_dotenv + validar presença + ValueError com a lista de
nomes ausentes) de forma independente - um typo de nome de variável ou uma
regra de validação corrigida num script não se propagava pros outros.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def carregar_variaveis_obrigatorias(project_root: Path, *nomes: str) -> dict[str, str]:
    """Carrega o `.env` de `project_root` e valida que `nomes` estão presentes.

    Levanta `ValueError` (mesmo formato de mensagem que todo `load_settings()`
    já usava manualmente) com a lista ordenada de nomes ausentes/vazios, num
    erro só. Devolve o dict {nome: valor} pronto para os módulos montarem seu
    próprio objeto de configuração (dataclass, dict, ou tupla) em cima.
    """

    load_dotenv(project_root / ".env")
    valores = {nome: os.getenv(nome) for nome in nomes}
    faltantes = [nome for nome, valor in valores.items() if not valor]
    if faltantes:
        raise ValueError(
            "Variáveis de ambiente ausentes: " + ", ".join(sorted(faltantes))
        )
    return valores  # type: ignore[return-value]
