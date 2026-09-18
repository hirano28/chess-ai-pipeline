"""Mostra quantos conceitos citáveis cada categoria do Hexágono tem hoje.

Reaproveita a mesma lógica de `buscar_conceitos()` do Agente 3
(`agente3_prescritor.py`) — não uma reimplementação em SQL à parte — para
que este relatório nunca fique fora de sincronia com o que a prescrição de
treino realmente enxerga. Motivação: entre D-72 e D-79, a mesma contagem
por categoria foi refeita à mão, por query solta, várias vezes na mesma
sessão de trabalho.

Uso:
  python -m backend.rag.cobertura_categorias
  python -m backend.rag.cobertura_categorias --livros
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from supabase import create_client  # noqa: E402

from backend.agentes.agente2_analista import HEXAGON_CATEGORIES  # noqa: E402
from backend.agentes.agente3_prescritor import (  # noqa: E402
    CATEGORY_SEARCH_TERMS,
    buscar_conceitos,
)
from backend.common.settings import carregar_variaveis_obrigatorias  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cobertura de indice_conceitual por categoria do Hexágono."
    )
    parser.add_argument(
        "--livros",
        action="store_true",
        help="Também lista os livros distintos citados em cada categoria.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = carregar_variaveis_obrigatorias(
        PROJECT_ROOT, "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"
    )
    client = create_client(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])

    linhas: list[tuple[str, int, list[str]]] = []
    for categoria in HEXAGON_CATEGORIES:
        conceitos = buscar_conceitos(client, categoria)
        livros = sorted({c["livro"] for c in conceitos if c.get("livro")})
        linhas.append((categoria, len(conceitos), livros))

    largura = max(len(categoria) for categoria, _, _ in linhas)
    linhas.sort(key=lambda item: item[1])
    print(f"{'Categoria':<{largura}}  Conceitos  Livros distintos")
    for categoria, total, livros in linhas:
        print(f"{categoria:<{largura}}  {total:>9}  {len(livros)}")
        if args.livros:
            for livro in livros:
                print(f"  - {livro}")

    sem_termo = [c for c in HEXAGON_CATEGORIES if c not in CATEGORY_SEARCH_TERMS]
    if sem_termo:
        print(f"\nAviso: sem termo de busca definido para {sem_termo}.")


if __name__ == "__main__":
    main()
