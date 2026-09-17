"""Popula a fila de repetição espaçada (D-48) com os lances críticos já
diagnosticados de cada usuário, aguardando revisão.

Desde o D-66 isso inclui os eventos EROSAO, que até então não tinham formato de
treino e ficavam parados no banco — ver `backend/common/treino_trecho.py`.

Roda no pipeline diário, DEPOIS do agente1_linter.py (depende de
`diagnosticos` já existir). Sem chamada a LLM: a citação de livro é resolvida
uma única vez aqui via `buscar_conceitos()` (ILIKE puro sobre
`indice_conceitual`, `agente3_prescritor.py` — sem embedding, sem Gemini) e
cacheada na linha da fila, para o endpoint `POST /treino/{id}/responder` não
pagar esse custo a cada repetição.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from supabase import Client, create_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.agente2_analista import HEXAGON_CATEGORIES  # noqa: E402
from backend.agentes.agente3_prescritor import buscar_conceitos  # noqa: E402
from backend.common.progress import configurar_encoding_utf8, log_and_print  # noqa: E402
from backend.common.settings import carregar_variaveis_obrigatorias  # noqa: E402

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "popular_fila_treino_espacado.log"
PAGE_SIZE = 1000

# Quantos cards NOVOS entram "hoje" na fila de um usuário, por execução. Evita
# que o primeiro run despeje o backlog histórico inteiro de uma vez - o
# restante é escalonado nos dias seguintes (ver montar_linhas_novas). Mesmo
# padrão de configuração por env var de LIMITE_DIARIO_* em D-32.
TREINO_NOVOS_POR_DIA = int(os.getenv("TREINO_NOVOS_POR_DIA", "10"))

# Até quantos dias à frente a fila pode agendar material NOVO (D-64).
#
# A válvula que faltava. Até aqui todo card novo entrava a partir de `hoje`,
# então cada execução empilhava mais 10 vencidos sobre os que já estavam
# vencidos — a fila crescia no ritmo da INGESTÃO, não no do consumo. Medido em
# 17/09/2026: 657 cards, 655 nunca respondidos, 61 dias de horizonte, 2
# respondidos na vida.
#
# Duas regras substituem isso: material novo vai para o FIM da fila (nunca
# disputa o dia com o que já está atrasado), e nada é agendado além deste
# horizonte. Material além do teto não se perde — o script reconsulta os
# diagnósticos elegíveis a cada execução e o pega quando a fila drenar.
#
# Por que um teto, e não "agenda tudo, só que longe": prometer trabalho para
# daqui a seis meses é ficção. Até lá o diagnóstico envelheceu, o jogador mudou
# e a fila vira um número que só serve para intimidar.
TREINO_HORIZONTE_DIAS = int(os.getenv("TREINO_HORIZONTE_DIAS", "60"))

# Quantos cards de EROSAO ("Refazer o trecho", D-66) cabem num mesmo dia.
#
# Um card de PICO é uma decisão: uma posição, um lance, um veredito. Um card de
# erosão são 8 lances do jogador, cada um com a resposta do motor — umas oito
# vezes o trabalho. Enfileirar 10 deles num dia seria repetir, em outra escala,
# o erro que o D-64 corrigiu: medir a fila em número de linhas em vez de em
# esforço real.
#
# Por isso eles entram com cota própria e o resto do dia é completado com
# picos, em vez de disputarem as mesmas 10 vagas por ordem de chegada. Em 0, os
# eventos de erosão simplesmente não são enfileirados (o desligador do recurso
# sem precisar de deploy); eles continuam no banco e voltam a ser candidatos
# quando a configuração mudar.
TREINO_TRECHOS_POR_DIA = int(os.getenv("TREINO_TRECHOS_POR_DIA", "2"))

# tag_falha -> categoria do hexágono, invertendo HEXAGON_CATEGORIES.
TAG_PARA_CATEGORIA: dict[str, str] = {
    tag: categoria
    for categoria, tags in HEXAGON_CATEGORIES.items()
    for tag in tags
}

# Cache em memória (uma execução do script cobre vários usuários, e a mesma
# categoria tende a se repetir entre eles) - buscar_conceitos já é barato
# (ILIKE), mas não há motivo pra repetir a mesma busca várias vezes.
_CACHE_CITACAO: dict[str, dict[str, Any] | None] = {}


def configure_logging() -> logging.Logger:
    """Configura o arquivo de log do script."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("popular_fila_treino_espacado")
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


def listar_usuarios_com_diagnostico(client: Client) -> list[str]:
    """Lista, sem repetir, os donos que têm ao menos um diagnóstico gerado.

    Times a `partidas` via o embed (mesmo raciocínio de D-28 em
    `agente2_analista.listar_usuarios_com_partidas`): um usuário sem nenhum
    diagnóstico ainda não tem nada pra enfileirar.
    """

    response = (
        client.table("diagnosticos")
        .select("lances_criticos!inner(partidas!inner(user_id))")
        .execute()
    )
    usuarios: set[str] = set()
    for row in response.data or []:
        lance = row.get("lances_criticos") or {}
        if isinstance(lance, list):
            lance = lance[0] if lance else {}
        partida = lance.get("partidas") or {}
        if isinstance(partida, list):
            partida = partida[0] if partida else {}
        user_id = partida.get("user_id")
        if user_id:
            usuarios.add(user_id)
    return sorted(usuarios)


def buscar_diagnosticos_elegiveis(
    client: Client, logger: logging.Logger, user_id: str
) -> list[dict[str, Any]]:
    """Busca diagnósticos de lances críticos com posição registrada, de 1 usuário.

    Exige `fen_antes_lance` não nulo - a coluna existe desde D-27, linhas mais
    antigas podem não ter sido reprocessadas e ficam sem posição pra mostrar.

    Até o D-65 filtrava também `tipo_evento='PICO'`, porque EROSAO é uma janela
    de vários lances e não tem um único "lance certo" pra pedir. O D-66 deu a
    ela o formato que lhe cabe (refazer o trecho inteiro contra o motor), então
    os dois tipos entram - o que os separa agora é a cota diária de
    `montar_linhas_novas`, não a elegibilidade.
    """

    rows: list[dict[str, Any]] = []
    offset = 0
    select = (
        "id, tags_falha, "
        "lances_criticos!inner(id, tipo_evento, fen_antes_lance, "
        "partidas!inner(user_id))"
    )
    while True:
        response = (
            client.table("diagnosticos")
            .select(select)
            .eq("lances_criticos.partidas.user_id", user_id)
            .not_.is_("lances_criticos.fen_antes_lance", "null")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    logger.info(
        "Usuário %s: %d diagnóstico(s) elegível(is) (com posição registrada).",
        user_id,
        len(rows),
    )
    return rows


def lances_ja_na_fila(client: Client, user_id: str) -> set[str]:
    """IDs de lances_criticos que este usuário já tem na fila (evita duplicar)."""

    response = (
        client.table("fila_treino_espacado")
        .select("lance_id")
        .eq("user_id", user_id)
        .execute()
    )
    return {row["lance_id"] for row in response.data or [] if row.get("lance_id")}


def resolver_citacao(client: Client, categoria: str | None) -> dict[str, Any] | None:
    """Resolve a 1ª citação de livro pra uma categoria, com cache em memória.

    Sem citação disponível (categoria sem conceito indexado) não é erro -
    devolve None e a linha da fila fica com os 3 campos de citação nulos.
    """

    if not categoria:
        return None
    if categoria in _CACHE_CITACAO:
        return _CACHE_CITACAO[categoria]

    conceitos = buscar_conceitos(client, categoria)
    citacao = conceitos[0] if conceitos else None
    _CACHE_CITACAO[categoria] = citacao
    return citacao


def primeiro_dia_livre(client: Client, user_id: str, hoje: date) -> date:
    """Primeiro dia em que cabe material novo, para ele entrar no FIM da fila.

    É o dia seguinte ao último já agendado para um card que o usuário ainda
    não respondeu (`total_revisoes = 0`), ou hoje, se não houver nenhum.

    Só contam os nunca respondidos: um card que já foi revisado e voltou para
    daqui a 30 dias pelo SM-2 é trabalho previsto, não backlog — deixá-lo
    empurrar o material novo adiaria a fila para sempre.
    """

    resposta = (
        client.table("fila_treino_espacado")
        .select("proxima_revisao_data")
        .eq("user_id", user_id)
        .eq("total_revisoes", 0)
        .order("proxima_revisao_data", desc=True)
        .limit(1)
        .execute()
    )
    linhas = resposta.data or []
    if not linhas or not linhas[0].get("proxima_revisao_data"):
        return hoje
    try:
        ultima = date.fromisoformat(str(linhas[0]["proxima_revisao_data"]))
    except ValueError:
        # Data ilegível não pode derrubar a população da fila: cair em `hoje` é
        # o comportamento anterior ao D-64, conservador e conhecido.
        return hoje
    return max(hoje, ultima + timedelta(days=1))


def _lance_do_diagnostico(diagnostico: dict[str, Any]) -> dict[str, Any]:
    """Desembrulha o embed `lances_criticos`, que vem objeto ou lista de um."""

    lance = diagnostico.get("lances_criticos") or {}
    if isinstance(lance, list):
        lance = lance[0] if lance else {}
    return lance if isinstance(lance, dict) else {}


def distribuir_por_dia(
    candidatos: list[tuple[str, dict[str, Any], bool]],
    por_dia: int,
    trechos_por_dia: int,
) -> list[tuple[int, str, dict[str, Any]]]:
    """Reparte os candidatos em dias, com cota separada para os trechos (D-66).

    Devolve `(deslocamento_em_dias, lance_id, diagnostico)`. Cada dia leva até
    `trechos_por_dia` cards de erosão e completa o resto com picos, até
    `por_dia` no total - assim um dia nunca vira oito vezes o trabalho de outro
    só porque a ordem de chegada calhou de trazer erosões em sequência.

    Com `trechos_por_dia = 0` os trechos não são distribuídos: o laço para
    quando só sobram eles, e eles continuam no banco como candidatos da próxima
    execução (mesma mecânica do que estoura o horizonte).
    """

    trechos = [item for item in candidatos if item[2]]
    picos = [item for item in candidatos if not item[2]]

    distribuicao: list[tuple[int, str, dict[str, Any]]] = []
    dia = 0
    while trechos or picos:
        do_dia: list[tuple[str, dict[str, Any], bool]] = []
        cota_trechos = min(max(0, trechos_por_dia), por_dia)
        while trechos and len(do_dia) < cota_trechos:
            do_dia.append(trechos.pop(0))
        while picos and len(do_dia) < por_dia:
            do_dia.append(picos.pop(0))
        if not do_dia:
            # Só restam trechos e a cota deles é zero: sair é o certo, insistir
            # seria laço infinito.
            break
        for lance_id, diagnostico, _ in do_dia:
            distribuicao.append((dia, lance_id, diagnostico))
        dia += 1
    return distribuicao


def montar_linhas_novas(
    diagnosticos: list[dict[str, Any]],
    ja_na_fila: set[str],
    client: Client,
    user_id: str,
    hoje: date,
    primeiro_dia: date | None = None,
    horizonte_dias: int = TREINO_HORIZONTE_DIAS,
) -> list[dict[str, Any]]:
    """Monta as linhas a inserir, escalonando no máximo TREINO_NOVOS_POR_DIA/dia.

    O escalonamento começa em `primeiro_dia` (o fim da fila, ver
    `primeiro_dia_livre`) e não passa de `hoje + horizonte_dias` — as duas
    metades da válvula do D-64. Antes dela o início era sempre `hoje`, e cada
    execução jogava mais 10 cards vencidos por cima dos que já estavam
    atrasados.

    O que passa do horizonte é deixado de fora **de propósito**: os
    diagnósticos continuam no banco e voltam a ser candidatos na próxima
    execução, quando a fila tiver drenado.

    Dentro de cada dia, os cards de erosão (D-66) têm cota própria e o resto é
    completado com picos - ver `distribuir_por_dia`.
    """

    candidatos: list[tuple[str, dict[str, Any], bool]] = []
    for diagnostico in diagnosticos:
        lance = _lance_do_diagnostico(diagnostico)
        lance_id = lance.get("id")
        if not lance_id or lance_id in ja_na_fila:
            continue
        eh_trecho = str(lance.get("tipo_evento") or "PICO").upper() == "EROSAO"
        candidatos.append((lance_id, diagnostico, eh_trecho))

    inicio = primeiro_dia or hoje
    ultimo_dia_permitido = hoje + timedelta(days=horizonte_dias)
    por_dia = max(1, TREINO_NOVOS_POR_DIA)

    linhas: list[dict[str, Any]] = []
    for deslocamento, lance_id, diagnostico in distribuir_por_dia(
        candidatos, por_dia, TREINO_TRECHOS_POR_DIA
    ):
        dia = inicio + timedelta(days=deslocamento)
        if dia > ultimo_dia_permitido:
            break
        tags = diagnostico.get("tags_falha") or []
        categoria = TAG_PARA_CATEGORIA.get(tags[0]) if tags else None
        citacao = resolver_citacao(client, categoria)
        linhas.append(
            {
                "user_id": user_id,
                "lance_id": lance_id,
                "proxima_revisao_data": dia.isoformat(),
                "livro_citado": citacao.get("livro") if citacao else None,
                "capitulo_citado": citacao.get("capitulo") if citacao else None,
                "pagina_citada": citacao.get("pagina_aprox") if citacao else None,
            }
        )
    return linhas


def popular_para_usuario(
    client: Client, logger: logging.Logger, user_id: str, hoje: date
) -> int:
    """Popula a fila de um usuário; devolve quantas linhas novas foram inseridas."""

    diagnosticos = buscar_diagnosticos_elegiveis(client, logger, user_id)
    if not diagnosticos:
        return 0

    ja_na_fila = lances_ja_na_fila(client, user_id)
    inicio = primeiro_dia_livre(client, user_id, hoje)
    linhas = montar_linhas_novas(
        diagnosticos, ja_na_fila, client, user_id, hoje, primeiro_dia=inicio
    )
    if not linhas:
        # Duas causas possíveis, e vale distinguir no log: ou não há material
        # novo, ou há e a fila está cheia até o horizonte (D-64).
        if inicio > hoje + timedelta(days=TREINO_HORIZONTE_DIAS):
            log_and_print(
                logger,
                f"Usuário {user_id}: fila cheia até {inicio.isoformat()}; "
                f"material novo aguarda a fila drenar (horizonte de "
                f"{TREINO_HORIZONTE_DIAS} dias).",
            )
        else:
            log_and_print(logger, f"Usuário {user_id}: fila já em dia, nada novo.")
        return 0

    client.table("fila_treino_espacado").upsert(
        linhas, on_conflict="user_id,lance_id"
    ).execute()
    log_and_print(
        logger, f"Usuário {user_id}: {len(linhas)} card(s) novo(s) enfileirado(s)."
    )
    return len(linhas)


def main() -> None:
    """Popula a fila de todos os usuários com diagnóstico disponível."""

    logger = configure_logging()
    hoje = date.today()
    total_inseridos = 0
    total_falhas = 0
    try:
        settings = load_settings()
        client = create_client(
            settings["SUPABASE_URL"], settings["SUPABASE_SERVICE_ROLE_KEY"]
        )
        usuarios = listar_usuarios_com_diagnostico(client)
        log_and_print(logger, f"{len(usuarios)} usuário(s) com diagnóstico disponível.")
        for user_id in usuarios:
            try:
                total_inseridos += popular_para_usuario(client, logger, user_id, hoje)
            except Exception:
                total_falhas += 1
                logger.error(
                    "Falha ao popular a fila do usuário %s:\n%s",
                    user_id,
                    traceback.format_exc(),
                )
    except Exception:
        total_falhas += 1
        logger.error(
            "Falha geral ao popular a fila de treino:\n%s", traceback.format_exc()
        )

    print(f"Cards novos enfileirados: {total_inseridos}")
    print(f"Falhas: {total_falhas}")


if __name__ == "__main__":
    main()
