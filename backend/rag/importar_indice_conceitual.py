"""Importa sugestões de índice conceitual geradas pelo Gemini para a tabela indice_conceitual.

Uso:
  python backend/rag/importar_indice_conceitual.py --json backend/rag/sugestoes/How_to_Reassess_Your_Chess.json [--substituir]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.rag.processar_livro import load_settings  # noqa: E402
from supabase import Client, create_client  # noqa: E402

BATCH_SIZE = 50


def carregar_sugestoes(json_path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Lê o arquivo JSON de sugestões e extrai os registros prontos para inserção."""
    if not json_path.exists():
        raise FileNotFoundError(f"Arquivo de sugestões não encontrado: {json_path}")

    conteudo = json.loads(json_path.read_text(encoding="utf-8"))
    livro = conteudo.get("livro")
    if not livro:
        raise ValueError("JSON de sugestões não contém a chave 'livro'.")

    registros: list[dict[str, Any]] = []
    for cap in conteudo.get("capitulos", []):
        capitulo = cap.get("capitulo")
        pagina = cap.get("pagina_min", 1)
        for conc in cap.get("conceitos_sugeridos", []):
            conceito = conc.get("conceito", "").strip()
            resumo = conc.get("resumo_curto", "").strip()
            if conceito:
                registros.append(
                    {
                        "livro": livro,
                        "capitulo": capitulo,
                        "pagina_aprox": pagina,
                        "conceito": conceito,
                        "resumo_curto": resumo,
                    }
                )

    return livro, registros


def importar_indice(
    client: Client,
    livro: str,
    registros: list[dict[str, Any]],
    substituir: bool = False,
) -> int:
    """Insere os registros na tabela indice_conceitual."""
    # Se substituir for solicitado, limpa registros anteriores deste livro
    if substituir:
        client.table("indice_conceitual").delete().eq("livro", livro).execute()

    inseridos = 0
    for i in range(0, len(registros), BATCH_SIZE):
        lote = registros[i : i + BATCH_SIZE]
        client.table("indice_conceitual").insert(lote).execute()
        inseridos += len(lote)

    return inseridos


def parse_args() -> argparse.Namespace:
    """Interpreta os argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="Importa registros de sugestões conceituais para o Supabase."
    )
    parser.add_argument(
        "--json",
        required=True,
        help="Caminho do arquivo JSON de sugestões.",
    )
    parser.add_argument(
        "--substituir",
        action="store_true",
        help="Remove entradas prévias do mesmo livro antes de inserir.",
    )
    return parser.parse_args()


def main() -> None:
    """Executa a importação a partir da linha de comando."""
    args = parse_args()
    json_path = Path(args.json)

    livro, registros = carregar_sugestoes(json_path)
    print(f"Carregados {len(registros)} conceitos do livro '{livro}'.")

    if not registros:
        print("Nenhum conceito válido para importar.")
        return

    settings = load_settings()
    client = create_client(
        settings["SUPABASE_URL"], settings["SUPABASE_SERVICE_ROLE_KEY"]
    )

    inseridos = importar_indice(client, livro, registros, substituir=args.substituir)
    print(f"Sucesso: {inseridos} conceitos inseridos em 'indice_conceitual' no Supabase!")


if __name__ == "__main__":
    main()

