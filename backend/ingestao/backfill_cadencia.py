"""Preenche `partidas.cadencia`/`tempo_base_segundos`/`incremento_segundos`
no acervo anterior ao D-57, lendo o header `TimeControl` do PGN já guardado.

Execução única (ou sempre que sobrar partida sem cadência). O PGN nunca muda
depois de gravado, então reprocessar é idempotente e barato — não há chamada
de rede nem de motor aqui, só leitura de texto.

Uso:
  python backend/ingestao/backfill_cadencia.py           # só as pendentes
  python backend/ingestao/backfill_cadencia.py --todas   # recalcula tudo
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from supabase import Client, create_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.cadencia import campos_de_cadencia, time_control_do_pgn  # noqa: E402
from backend.common.progress import configurar_encoding_utf8, log_and_print  # noqa: E402
from backend.common.settings import carregar_variaveis_obrigatorias  # noqa: E402

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "backfill_cadencia.log"
PAGE_SIZE = 200


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do script."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("backfill_cadencia")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def load_settings() -> dict[str, str]:
    """Carrega e valida as configurações do ambiente."""

    return carregar_variaveis_obrigatorias(
        PROJECT_ROOT, "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"
    )


def cadencia_da_partida(partida: dict[str, Any]) -> dict[str, Any]:
    """Campos de cadência de uma linha de `partidas` (função pura)."""

    return campos_de_cadencia(time_control_do_pgn(partida.get("pgn")))


def buscar_partidas(client: Client, todas: bool, offset: int) -> list[dict[str, Any]]:
    """Uma página de partidas a preencher."""

    consulta = client.table("partidas").select("id, pgn")
    if not todas:
        consulta = consulta.is_("cadencia", "null")
    return (
        consulta.order("id").range(offset, offset + PAGE_SIZE - 1).execute().data or []
    )


def executar(client: Client, logger: logging.Logger, todas: bool = False) -> dict[str, int]:
    """Percorre as partidas e grava a cadência de cada uma."""

    resumo: dict[str, int] = {}
    total = 0
    offset = 0

    while True:
        pagina = buscar_partidas(client, todas, offset)
        if not pagina:
            break

        for partida in pagina:
            campos = cadencia_da_partida(partida)
            client.table("partidas").update(campos).eq("id", partida["id"]).execute()
            cadencia = str(campos["cadencia"])
            resumo[cadencia] = resumo.get(cadencia, 0) + 1
            total += 1

        log_and_print(logger, f"{total} partidas atualizadas ({resumo}).")
        if len(pagina) < PAGE_SIZE:
            break
        # Sem `--todas` a própria consulta encolhe a cada página (as já
        # preenchidas somem do filtro), então o offset tem que ficar parado.
        offset = offset + PAGE_SIZE if todas else 0

    return {"partidas_atualizadas": total, **resumo}


def main() -> None:
    """Ponto de entrada do backfill de cadência."""

    todas = "--todas" in sys.argv
    logger = configure_logging()
    settings = load_settings()
    client = create_client(settings["SUPABASE_URL"], settings["SUPABASE_SERVICE_ROLE_KEY"])

    resumo = executar(client, logger, todas=todas)

    print(f"Partidas atualizadas: {resumo['partidas_atualizadas']}")
    for chave, valor in sorted(resumo.items()):
        if chave != "partidas_atualizadas":
            print(f"  {chave}: {valor}")


if __name__ == "__main__":
    main()
