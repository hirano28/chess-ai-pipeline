"""Rebusca no Lichess o PGN oficial das partidas já ingeridas e regrava
`partidas.pgn` junto das três colunas de cadência (D-62).

Por que este script existe, e por que `backfill_cadencia.py` não resolve: aquele
lê o `TimeControl` do PGN **já guardado**, e aqui o PGN guardado é justamente o
problema. Até o D-62 a coleta do Lichess não pedia `pgnInJson`, então
`build_pgn()` reconstruía um PGN de 6 cabeçalhos a partir da lista de lances —
sem `TimeControl`, sem Elo, sem ECO e sem relógio. Resultado medido em
17/09/2026: 87 de 87 partidas do Lichess com `cadencia = DESCONHECIDA`, contra
161 de 161 classificadas no Chess.com. Rodar o backfill de cadência sobre esses
PGNs devolveria DESCONHECIDA de novo, corretamente — o dado não está lá.

A correção é reingerir o PGN da fonte. O endpoint de exportação por IDs aceita
até 300 de uma vez, o que resolve o acervo inteiro em pouquíssimas chamadas.

**Os lances não mudam.** O PGN oficial traz a mesma partida com mais
cabeçalhos e comentários de relógio, então a numeração continua valendo e
`lances_criticos.numero_lance` segue apontando para o mesmo lance. É por isso
que dá para regravar o PGN de partidas já analisadas sem reprocessar nada — e
o script confere isso partida a partida antes de gravar, em vez de confiar.

Uso:
  python backend/ingestao/backfill_pgn_lichess.py           # só as sem cadência
  python backend/ingestao/backfill_pgn_lichess.py --todas   # todas do Lichess
  python backend/ingestao/backfill_pgn_lichess.py --simular # não grava nada
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Iterator

import chess.pgn
import requests
from supabase import Client, create_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.common.cadencia import campos_de_cadencia, time_control_do_pgn  # noqa: E402
from backend.common.progress import configurar_encoding_utf8, log_and_print  # noqa: E402
from backend.common.settings import carregar_variaveis_obrigatorias  # noqa: E402

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "backfill_pgn_lichess.log"
LICHESS_EXPORT_IDS_URL = "https://lichess.org/api/games/export/_ids"

# Teto do próprio endpoint. Não aumentar sem conferir a documentação: acima
# disso o Lichess responde 400 em vez de truncar, e a leva inteira se perde.
IDS_POR_REQUISICAO = 300

PARAMETROS_EXPORT: dict[str, str] = {
    "pgnInJson": "true",
    "tags": "true",
    "clocks": "true",
    "opening": "true",
}


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do script."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("backfill_pgn_lichess")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def load_settings() -> dict[str, str]:
    """Carrega e valida as configurações do ambiente."""

    return carregar_variaveis_obrigatorias(
        PROJECT_ROOT, "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "LICHESS_TOKEN"
    )


def lances_do_pgn(pgn: str | None) -> list[str] | None:
    """Lista de lances (UCI) de um PGN, ou None se não der para ler.

    Comparar a sequência, e não só a contagem, é o que sustenta a decisão de
    regravar: garante que estamos falando da MESMA partida antes de trocar um
    PGN que `lances_criticos` referencia por número de lance.
    """

    if not pgn or not pgn.strip():
        return None
    try:
        jogo = chess.pgn.read_game(io.StringIO(pgn))
    except Exception:
        return None
    if jogo is None:
        return None
    return [lance.uci() for lance in jogo.mainline_moves()]


def contar_lances(pgn: str | None) -> int | None:
    """Quantidade de meios-lances de um PGN, ou None se ilegível."""

    lances = lances_do_pgn(pgn)
    return None if lances is None else len(lances)


def comeca_de_posicao_customizada(pgn: str | None) -> bool:
    """Diz se o PGN declara uma posição inicial própria (`SetUp`/`FEN`)."""

    if not pgn:
        return False
    for linha in pgn.splitlines():
        despida = linha.strip()
        if not despida.startswith("["):
            if despida:
                break
            continue
        if despida.startswith('[SetUp "1"]') or despida.startswith('[FEN "'):
            return True
    return False


def classificar_troca(
    antigos: list[str] | None,
    novos: list[str],
    novo_de_posicao_customizada: bool = False,
) -> str:
    """Diz se trocar o PGN antigo pelo novo é seguro, e por quê.

    Quatro respostas:

    - `"igual"` — mesma sequência de lances. É o caso dos 85 PGNs que a
      reconstrução antiga acertou: a troca só acrescenta cabeçalhos e relógio.
    - `"truncado"` — o antigo é PREFIXO do novo. O `build_pgn()` anterior tinha
      um `break` ao topar com um SAN que não parseava, e gravava a partida pela
      metade sem avisar ninguém. Trocar aqui não é só seguro, é o conserto — e a
      numeração dos lances já existentes continua válida, porque é prefixo.
    - `"posicao_errada"` — o PGN oficial parte de uma posição customizada
      (`variant: fromPosition`) e o antigo não. A reconstrução antiga sempre
      começava da posição inicial padrão, então ela interpretou os mesmos SAN
      em outro tabuleiro: o `d4` que ela gravou é um lance DIFERENTE do `d4`
      jogado. O PGN guardado não descreve a partida que aconteceu, e trocá-lo
      é corrigir, não arriscar.
    - `"divergente"` — discordam em ponto comum sem explicação conhecida. Aí
      regravar desalinharia `lances_criticos.numero_lance`, e a recusa vale.
    """

    if antigos is None:
        return "truncado"  # sem base de comparação; o oficial só pode ser melhor
    if antigos == novos:
        return "igual"
    if len(antigos) < len(novos) and novos[: len(antigos)] == antigos:
        return "truncado"
    if novo_de_posicao_customizada:
        return "posicao_errada"
    return "divergente"


# Os dois vereditos em que o PGN guardado não descreve a partida real, e por
# isso tudo que foi derivado dele precisa ser refeito.
VEREDITOS_QUE_EXIGEM_REANALISE = ("truncado", "posicao_errada")


def lotes(itens: list[Any], tamanho: int) -> Iterator[list[Any]]:
    """Fatia uma lista em blocos de no máximo `tamanho`."""

    for inicio in range(0, len(itens), tamanho):
        yield itens[inicio : inicio + tamanho]


def buscar_pgns(
    ids: list[str], token: str, logger: logging.Logger
) -> dict[str, dict[str, Any]]:
    """Exporta as partidas informadas e devolve {external_id: jogo}."""

    resposta = requests.post(
        LICHESS_EXPORT_IDS_URL,
        headers={
            "Accept": "application/x-ndjson",
            "Authorization": f"Bearer {token}",
        },
        params=PARAMETROS_EXPORT,
        data=",".join(ids),
        timeout=60,
    )
    resposta.raise_for_status()

    encontrados: dict[str, dict[str, Any]] = {}
    for linha in resposta.text.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            jogo = json.loads(linha)
        except json.JSONDecodeError as erro:
            logger.error("Linha NDJSON inválida na exportação: %s", erro)
            continue
        if isinstance(jogo, dict) and jogo.get("id"):
            encontrados[str(jogo["id"])] = jogo
    return encontrados


def atualizacao_da_partida(
    partida: dict[str, Any], jogo: dict[str, Any]
) -> tuple[dict[str, Any] | None, str, str]:
    """Monta o update de uma partida.

    Devolve `(campos, motivo_da_recusa, veredito)`. Função pura, para ser
    testável sem rede nem banco: `campos` é None sempre que a troca não for
    segura, e o veredito ("igual"/"truncado") diz ao chamador se há trabalho
    derivado a limpar antes de gravar.
    """

    novo_pgn = jogo.get("pgn")
    if not isinstance(novo_pgn, str) or not novo_pgn.strip():
        return None, "resposta sem PGN", ""

    novos = lances_do_pgn(novo_pgn)
    if novos is None:
        return None, "PGN novo ilegível", ""

    antigos = lances_do_pgn(partida.get("pgn"))
    veredito = classificar_troca(
        antigos, novos, comeca_de_posicao_customizada(novo_pgn)
    )
    if veredito == "divergente":
        return None, f"lances divergem ({len(antigos or [])} -> {len(novos)})", veredito

    campos: dict[str, Any] = {"pgn": novo_pgn}
    campos.update(campos_de_cadencia(time_control_do_pgn(novo_pgn)))

    if veredito in VEREDITOS_QUE_EXIGEM_REANALISE:
        # A partida guardada estava pela metade, então tudo que foi derivado
        # dela saiu de uma partida que não aconteceu. Voltar para `pendente`
        # faz o pipeline diário reanalisá-la inteira. Quem grava é o chamador,
        # que antes apaga os derivados — R7 em AGENTS.md.
        campos["status_processamento"] = "pendente"

    return campos, "", veredito


def carregar_partidas(client: Client, todas: bool) -> list[dict[str, Any]]:
    """Busca as partidas do Lichess candidatas ao backfill."""

    consulta = (
        client.table("partidas")
        .select("id, external_id, pgn, cadencia")
        .eq("plataforma", "LICHESS")
    )
    if not todas:
        # `or_` cobre os dois estados de "sem cadência utilizável": nunca
        # classificada (null) e classificada como desconhecida.
        consulta = consulta.or_("cadencia.is.null,cadencia.eq.DESCONHECIDA")
    return consulta.execute().data or []


def main() -> None:
    """Rebusca os PGNs e regrava PGN + cadência, informando o resumo."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--todas",
        action="store_true",
        help="reprocessa todas as partidas do Lichess, não só as sem cadência",
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="mostra o que mudaria sem gravar nada",
    )
    args = parser.parse_args()

    logger = configure_logging()
    settings = load_settings()
    client = create_client(
        settings["SUPABASE_URL"], settings["SUPABASE_SERVICE_ROLE_KEY"]
    )

    partidas = carregar_partidas(client, args.todas)
    if not partidas:
        print("Nenhuma partida do Lichess pendente de PGN oficial.")
        return

    por_external_id = {str(p["external_id"]): p for p in partidas}
    ids = list(por_external_id)
    log_and_print(logger, f"{len(ids)} partida(s) do Lichess para rebuscar.")

    atualizadas = puladas = ausentes = recuperadas = 0
    distribuicao: dict[str, int] = {}

    for bloco in lotes(ids, IDS_POR_REQUISICAO):
        jogos = buscar_pgns(bloco, settings["LICHESS_TOKEN"], logger)
        for external_id in bloco:
            partida = por_external_id[external_id]
            jogo = jogos.get(external_id)
            if jogo is None:
                ausentes += 1
                logger.warning("Partida %s não voltou na exportação.", external_id)
                continue

            campos, recusa, veredito = atualizacao_da_partida(partida, jogo)
            if campos is None:
                puladas += 1
                logger.warning("Partida %s pulada: %s", external_id, recusa)
                continue

            cadencia = str(campos["cadencia"])
            distribuicao[cadencia] = distribuicao.get(cadencia, 0) + 1
            if veredito in VEREDITOS_QUE_EXIGEM_REANALISE:
                recuperadas += 1
                log_and_print(
                    logger,
                    f"Partida {external_id} estava incorreta no banco "
                    f"({veredito}) e vai ser reanalisada do zero.",
                )
            if not args.simular:
                if veredito in VEREDITOS_QUE_EXIGEM_REANALISE:
                    # R7: apagar o derivado ANTES de remarcar como pendente,
                    # senão o diagnóstico da partida pela metade se mistura com
                    # o da partida inteira.
                    client.table("lances_criticos").delete().eq(
                        "partida_id", partida["id"]
                    ).execute()
                client.table("partidas").update(campos).eq("id", partida["id"]).execute()
            atualizadas += 1

        log_and_print(
            logger, f"Progresso: {atualizadas + puladas + ausentes}/{len(ids)}"
        )

    if args.simular:
        print("\n[SIMULACAO] nada foi gravado.")
    print(f"\nPartidas atualizadas: {atualizadas}")
    print(f"  destas, truncadas no banco e remarcadas para reanalise: {recuperadas}")
    print(f"Partidas puladas (troca insegura): {puladas}")
    print(f"Partidas nao encontradas no Lichess: {ausentes}")
    print("Cadencia resultante:")
    for nome in sorted(distribuicao, key=lambda n: -distribuicao[n]):
        print(f"  {nome}: {distribuicao[nome]}")


if __name__ == "__main__":
    main()
