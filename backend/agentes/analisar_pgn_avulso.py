"""Orquestrador de análise de PGN avulso — pipeline completo para UMA partida.

Aceita um PGN via --pgn-file ou stdin, roda Stockfish → Diagnóstico → Resumo,
e imprime a narrativa completa no terminal.

Uso:
    python -m backend.agentes.analisar_pgn_avulso --pgn-file minha_partida.pgn
    cat partida.pgn | python -m backend.agentes.analisar_pgn_avulso
    python -m backend.agentes.analisar_pgn_avulso   # cola o PGN e Ctrl+Z/D
"""

from __future__ import annotations

import argparse
import hashlib
import io
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import chess.pgn
import google.genai as genai
from dotenv import load_dotenv
from stockfish import Stockfish
from supabase import Client, create_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# --- Imports reutilizados dos módulos existentes (sem duplicar lógica) ---
from backend.agentes.agente1_linter import (  # noqa: E402
    AgentSettings as LinterSettings,
    fetch_critical_moves,
    fetch_diagnosed_move_ids,
    insert_diagnosis,
    load_settings as load_linter_settings,
    processar_lance,
)
from backend.agentes.gerar_resumo_partida import (  # noqa: E402
    build_prompt_resumo,
    coletar_dados_partida,
    enriquecer_com_dados_motor,
    gerar_resumo_gemini,
    inserir_resumo,
)
from backend.analise_engine.analisar_partidas import (  # noqa: E402
    AnalysisSettings,
    insert_critical_moves,
    load_settings as load_analysis_settings,
    load_timeout_setting,
    processar_partida_com_timeout,
    update_status,
    PARTIDA_TIMEOUT_SECONDS,
    STOCKFISH_INIT_TIMEOUT_SECONDS,
)
from backend.common.progress import (  # noqa: E402
    configurar_encoding_utf8,
    format_duration,
    format_progress,
    log_and_print,
)

configurar_encoding_utf8()

LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "analisar_pgn_avulso.log"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def configure_logging() -> logging.Logger:
    """Configura o logger do orquestrador de PGN avulso."""

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("analisar_pgn_avulso")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


# ---------------------------------------------------------------------------
# Leitura do PGN
# ---------------------------------------------------------------------------

def ler_pgn_de_arquivo(caminho: str) -> str:
    """Lê o conteúdo PGN de um arquivo."""

    path = Path(caminho)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")
    return path.read_text(encoding="utf-8")


def ler_pgn_de_stdin() -> str:
    """Lê o conteúdo PGN do stdin (permite colar no terminal)."""

    print("Cole o PGN abaixo e pressione Ctrl+Z (Windows) ou Ctrl+D (Unix) ao final:\n")
    return sys.stdin.read()


# ---------------------------------------------------------------------------
# Parse e determinação de cor
# ---------------------------------------------------------------------------

def parse_pgn(pgn_text: str) -> chess.pgn.Game:
    """Faz parse do PGN e valida que é uma partida jogável."""

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Não foi possível fazer parse do PGN fornecido.")
    if game.end() is game:
        raise ValueError("O PGN não contém lances para analisar.")
    return game


def inferir_cor_jogador(game: chess.pgn.Game) -> str | None:
    """Tenta inferir a cor do jogador comparando headers com .env usernames."""

    load_dotenv(PROJECT_ROOT / ".env")
    usernames: list[str] = []
    for var in ("LICHESS_USERNAME", "CHESSCOM_USERNAME"):
        val = os.getenv(var)
        if val:
            usernames.append(val.strip().lower())

    if not usernames:
        return None

    white = (game.headers.get("White") or "").strip().lower()
    black = (game.headers.get("Black") or "").strip().lower()

    for username in usernames:
        if white == username:
            return "BRANCAS"
        if black == username:
            return "PRETAS"

    return None


def perguntar_cor_interativamente() -> str:
    """Pergunta ao usuário qual cor ele jogou."""

    while True:
        resposta = input(
            "\nVocê jogou de Brancas ou Pretas nesta partida? (B/P): "
        ).strip().upper()
        if resposta in ("B", "BRANCAS"):
            return "BRANCAS"
        if resposta in ("P", "PRETAS"):
            return "PRETAS"
        print("  Resposta inválida. Digite B (Brancas) ou P (Pretas).")


def resolver_cor(game: chess.pgn.Game, cor_fornecida: str | None = None) -> str:
    """Resolve a cor do jogador a partir do argumento fornecido ou inferência do PGN.

    Se cor_fornecida for informada, normaliza e valida ('BRANCAS' ou 'PRETAS').
    Se não for informada, tenta inferir via inferir_cor_jogador.
    Se não for possível inferir, levanta ValueError solicitando a cor explicitamente.
    """
    if cor_fornecida is not None:
        cor_limpa = cor_fornecida.strip().upper()
        if cor_limpa in ("BRANCAS", "B"):
            return "BRANCAS"
        if cor_limpa in ("PRETAS", "P"):
            return "PRETAS"
        raise ValueError(
            f"Cor inválida: '{cor_fornecida}'. A cor deve ser 'BRANCAS' ou 'PRETAS'."
        )

    cor_inferida = inferir_cor_jogador(game)
    if cor_inferida:
        return cor_inferida

    raise ValueError(
        "Não foi possível inferir a cor do jogador a partir do PGN. "
        "Por favor, informe a cor explicitamente ('BRANCAS' ou 'PRETAS')."
    )


def determinar_cor(game: chess.pgn.Game) -> str:
    """Determina a cor do jogador para o CLI: inferência automática ou pergunta interativa."""

    cor = inferir_cor_jogador(game)
    if cor:
        print(f"  Cor detectada automaticamente: {cor}")
        return cor
    return perguntar_cor_interativamente()


# ---------------------------------------------------------------------------
# Extração de metadados do PGN
# ---------------------------------------------------------------------------

def extrair_resultado(game: chess.pgn.Game, cor: str) -> str | None:
    """Extrai e normaliza o resultado a partir dos headers do PGN."""

    result = game.headers.get("Result")
    if not result or result == "*":
        return None
    if result == "1/2-1/2":
        return "EMPATE"
    if (result == "1-0" and cor == "BRANCAS") or (result == "0-1" and cor == "PRETAS"):
        return "VITORIA"
    if (result == "0-1" and cor == "BRANCAS") or (result == "1-0" and cor == "PRETAS"):
        return "DERROTA"
    return None


def extrair_rating(game: chess.pgn.Game, cor: str) -> tuple[int | None, int | None]:
    """Extrai ratings do PGN headers (WhiteElo/BlackElo)."""

    try:
        proprio = int(game.headers.get("WhiteElo" if cor == "BRANCAS" else "BlackElo", ""))
    except (ValueError, TypeError):
        proprio = None
    try:
        oponente = int(game.headers.get("BlackElo" if cor == "BRANCAS" else "WhiteElo", ""))
    except (ValueError, TypeError):
        oponente = None
    return proprio, oponente


def extrair_data(game: chess.pgn.Game) -> str | None:
    """Extrai a data da partida dos headers (formato ISO)."""

    date_str = game.headers.get("Date") or game.headers.get("UTCDate")
    if not date_str or "?" in date_str:
        return None
    # Converte de "2024.01.15" para "2024-01-15"
    return date_str.replace(".", "-")


def gerar_external_id(pgn_text: str) -> str:
    """Gera um external_id determinístico a partir do hash do PGN."""

    return "manual_" + hashlib.sha256(pgn_text.strip().encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Inserção da partida
# ---------------------------------------------------------------------------

def inserir_partida(
    client: Client, pgn_text: str, game: chess.pgn.Game, cor: str
) -> str:
    """Insere a partida na tabela partidas com upsert por external_id.

    Retorna o ID interno da partida (gerado pelo Supabase).
    """

    external_id = gerar_external_id(pgn_text)
    resultado = extrair_resultado(game, cor)
    rating_proprio, rating_oponente = extrair_rating(game, cor)
    data_partida = extrair_data(game)
    eco = game.headers.get("ECO")

    payload: dict[str, Any] = {
        "plataforma": "MANUAL",
        "external_id": external_id,
        "pgn": pgn_text.strip(),
        "cor_jogada": cor,
        "status_processamento": "pendente",
    }
    # Campos opcionais — só inclui se extraiu algo
    if resultado:
        payload["resultado"] = resultado
    if data_partida:
        payload["data_partida"] = data_partida
    if rating_proprio is not None:
        payload["rating_proprio"] = rating_proprio
    if rating_oponente is not None:
        payload["rating_oponente"] = rating_oponente
    if eco:
        payload["eco_abertura"] = eco

    response = (
        client.table("partidas")
        .upsert(payload, on_conflict="external_id")
        .execute()
    )
    row = response.data[0] if response.data else {}
    partida_id = row.get("id")
    if not partida_id:
        raise RuntimeError(
            f"Falha ao inserir/atualizar partida (external_id={external_id})"
        )
    return str(partida_id)


# ---------------------------------------------------------------------------
# Etapa 1: Análise Stockfish
# ---------------------------------------------------------------------------

def etapa_stockfish(
    client: Client,
    partida_id: str,
    settings: AnalysisSettings,
    logger: logging.Logger,
) -> int:
    """Roda o Stockfish e insere lances críticos. Retorna quantidade inserida."""

    log_and_print(logger, "\n⏳ Etapa 1/3: Analisando com Stockfish...")

    # Busca a partida recém-inserida
    response = (
        client.table("partidas")
        .select("*")
        .eq("id", partida_id)
        .execute()
    )
    partida = response.data[0] if response.data else None
    if not partida:
        raise RuntimeError(f"Partida {partida_id} não encontrada no banco.")

    update_status(client, partida_id, "processando")

    init_timeout = load_timeout_setting(
        "STOCKFISH_INIT_TIMEOUT_SECONDS", STOCKFISH_INIT_TIMEOUT_SECONDS
    )
    partida_timeout = load_timeout_setting(
        "PARTIDA_TIMEOUT_SECONDS", PARTIDA_TIMEOUT_SECONDS
    )

    result = processar_partida_com_timeout(
        partida, settings, init_timeout, partida_timeout
    )
    inserted = insert_critical_moves(client, result)
    update_status(client, partida_id, "concluido")

    log_and_print(
        logger,
        f"  ✅ Stockfish concluído: {inserted} lance(s) crítico(s) detectados "
        f"({sum(1 for m in result.critical_moves if m.tipo_evento == 'PICO')} pico(s), "
        f"{sum(1 for m in result.critical_moves if m.tipo_evento == 'EROSAO')} erosão(ões))",
    )
    return inserted


# ---------------------------------------------------------------------------
# Etapa 2: Diagnóstico via Gemini (agente1_linter)
# ---------------------------------------------------------------------------

def etapa_diagnostico(
    client: Client,
    partida_id: str,
    gemini_client: Any,
    linter_settings: LinterSettings,
    logger: logging.Logger,
) -> int:
    """Diagnostica os lances críticos desta partida. Retorna quantidade diagnosticada."""

    log_and_print(logger, "\n⏳ Etapa 2/3: Diagnosticando lances críticos com Gemini...")

    # Busca lances críticos SOMENTE desta partida
    all_moves = fetch_critical_moves(client, logger)
    moves_desta_partida = [
        lance for lance in all_moves
        if lance.get("partida_id") == partida_id
    ]

    if not moves_desta_partida:
        log_and_print(logger, "  ⚠️  Nenhum lance crítico encontrado para diagnosticar.")
        return 0

    # Remove diagnósticos existentes desta partida (para reprocessamento limpo)
    diagnosed_ids = fetch_diagnosed_move_ids(client, logger)

    total = len(moves_desta_partida)
    processed = 0
    failed = 0
    start_time = time.time()

    for i, lance in enumerate(moves_desta_partida, 1):
        lance_id = lance.get("id")
        if lance_id in diagnosed_ids:
            log_and_print(logger, f"  ⏭️  Lance {lance_id} já diagnosticado — pulando.")
            continue
        try:
            result = processar_lance(
                lance, gemini_client, settings=linter_settings, logger=logger
            )
            insert_diagnosis(client, result)
            processed += 1
        except Exception:
            failed += 1
            logger.error(
                "Falha ao diagnosticar lance %s:\n%s",
                lance_id, traceback.format_exc(),
            )

        if i % 3 == 0 or i == total:
            log_and_print(
                logger,
                "  " + format_progress(
                    "Diagnóstico", "lances", i, total,
                    time.time() - start_time,
                ),
            )

    log_and_print(
        logger,
        f"  ✅ Diagnóstico concluído: {processed} lance(s) diagnosticados"
        + (f", {failed} falha(s)" if failed else ""),
    )
    return processed


# ---------------------------------------------------------------------------
# Etapa 3: Resumo narrativo (gerar_resumo_partida)
# ---------------------------------------------------------------------------

def etapa_resumo(
    client: Client,
    partida_id: str,
    gemini_client: Any,
    stockfish_settings: AnalysisSettings,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Gera o resumo narrativo da partida. Retorna os dados do resumo."""

    log_and_print(logger, "\n⏳ Etapa 3/3: Gerando resumo narrativo...")

    dados = coletar_dados_partida(client, partida_id, logger)
    if not dados.lances_criticos:
        log_and_print(
            logger,
            "  ⚠️  Nenhum lance crítico com diagnóstico — gerando resumo mínimo.",
        )

    engine = Stockfish(
        path=stockfish_settings.stockfish_path,
        depth=stockfish_settings.stockfish_depth,
        turn_perspective=False,
    )
    try:
        enriquecer_com_dados_motor(dados, engine, logger)
    finally:
        try:
            engine.send_quit_command()
        except Exception:
            pass

    prompt = build_prompt_resumo(dados)
    resumo = gerar_resumo_gemini(gemini_client, prompt, dados, logger)
    inserir_resumo(client, partida_id, resumo)

    log_and_print(logger, "  ✅ Resumo gerado e salvo no banco.")

    return {
        "narrativa": resumo.narrativa,
        "pontos_criticos": [pc.model_dump() for pc in resumo.pontos_criticos],
        "momento_chave_estrategico": resumo.momento_chave_estrategico,
    }


def executar_pipeline_partida(
    client: Client,
    partida_id: str,
    gemini_client: Any,
    analysis_settings: AnalysisSettings,
    linter_settings: LinterSettings,
    logger: logging.Logger | None = None,
    engine_lock: Any | None = None,
) -> dict[str, Any] | None:
    """Executa as 3 etapas de análise (Stockfish -> Diagnóstico -> Resumo) para uma partida.

    Garante que:
    1. Se engine_lock for fornecido, adquire o lock para as etapas que utilizam o Stockfish.
    2. Se ocorrer qualquer falha durante a execução, marca status_processamento='falhou'
       na tabela partidas para que a partida não fique indefinidamente presa em 'processando'.
    3. Retorna o resultado do resumo, ou None se a partida não teve lances críticos detectados.
    """

    logger = logger or configure_logging()

    try:
        # --- Etapa 1: Stockfish ---
        if engine_lock is not None:
            with engine_lock:
                lances_inseridos = etapa_stockfish(
                    client, partida_id, analysis_settings, logger
                )
        else:
            lances_inseridos = etapa_stockfish(
                client, partida_id, analysis_settings, logger
            )

        if lances_inseridos == 0:
            log_and_print(
                logger,
                "\n✅ Partida sem lances críticos detectados — jogo limpo!",
            )
            update_status(client, partida_id, "concluido")
            return None

        # --- Etapa 2: Diagnóstico Gemini ---
        etapa_diagnostico(
            client, partida_id, gemini_client, linter_settings, logger
        )

        # --- Etapa 3: Resumo Narrativo ---
        if engine_lock is not None:
            with engine_lock:
                resultado = etapa_resumo(
                    client, partida_id, gemini_client, analysis_settings, logger
                )
        else:
            resultado = etapa_resumo(
                client, partida_id, gemini_client, analysis_settings, logger
            )

        update_status(client, partida_id, "concluido")
        return resultado

    except Exception as error:
        try:
            update_status(client, partida_id, "falhou")
        except Exception:
            pass
        logger.error(
            "Falha ao executar pipeline da partida %s: %s\n%s",
            partida_id,
            error,
            traceback.format_exc(),
        )
        raise


# ---------------------------------------------------------------------------
# Exibição final no terminal
# ---------------------------------------------------------------------------

def exibir_resultado(resultado: dict[str, Any]) -> None:
    """Imprime a narrativa completa formatada no terminal."""

    separador = "═" * 70
    print(f"\n{separador}")
    print("  📋 RESUMO NARRATIVO DA PARTIDA")
    print(separador)
    print()
    print(resultado["narrativa"])
    print()

    if resultado["pontos_criticos"]:
        print(f"{'─' * 70}")
        print("  🎯 PONTOS CRÍTICOS")
        print(f"{'─' * 70}")
        for pc in resultado["pontos_criticos"]:
            tipo = pc.get("tipo_evento", "?")
            lance = pc.get("numero_lance", "?")
            tags = ", ".join(pc.get("tags_falha", []))
            emoji = "💥" if tipo == "PICO" else "📉"
            print(f"  {emoji} Lance {lance} ({tipo}): {tags}")
        print()

    if resultado.get("momento_chave_estrategico"):
        print(f"{'─' * 70}")
        print("  🔑 MOMENTO-CHAVE ESTRATÉGICO")
        print(f"{'─' * 70}")
        print(f"  {resultado['momento_chave_estrategico']}")
        print()

    print(separador)


# ---------------------------------------------------------------------------
# Orquestrador principal
# ---------------------------------------------------------------------------

def main() -> None:
    """Orquestra o pipeline completo para um PGN avulso."""

    parser = argparse.ArgumentParser(
        description="Analisa uma partida PGN avulsa com o pipeline completo."
    )
    parser.add_argument(
        "--pgn-file",
        type=str,
        default=None,
        help="Caminho para o arquivo .pgn (se omitido, lê do stdin).",
    )
    args = parser.parse_args()

    logger = configure_logging()
    start_time = time.time()

    try:
        # --- Leitura do PGN ---
        if args.pgn_file:
            log_and_print(logger, f"📂 Lendo PGN de: {args.pgn_file}")
            pgn_text = ler_pgn_de_arquivo(args.pgn_file)
        else:
            pgn_text = ler_pgn_de_stdin()

        if not pgn_text.strip():
            print("❌ PGN vazio. Encerrando.")
            return

        # --- Parse e validação ---
        game = parse_pgn(pgn_text)
        white = game.headers.get("White", "?")
        black = game.headers.get("Black", "?")
        result_header = game.headers.get("Result", "?")
        print(f"\n♟️  Partida: {white} vs {black} ({result_header})")

        # --- Determinação da cor ---
        cor = determinar_cor(game)

        # --- Configurações ---
        load_dotenv(PROJECT_ROOT / ".env")
        analysis_settings = load_analysis_settings()
        linter_settings = load_linter_settings()
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY não encontrada no .env")

        supabase_client = create_client(
            analysis_settings.supabase_url,
            analysis_settings.supabase_service_role_key,
        )
        gemini_client = genai.Client(api_key=gemini_api_key)

        # --- Inserção da partida ---
        external_id = gerar_external_id(pgn_text)
        log_and_print(
            logger,
            f"💾 Inserindo partida no banco (external_id={external_id[:20]}...)...",
        )
        partida_id = inserir_partida(supabase_client, pgn_text, game, cor)
        log_and_print(logger, f"  ✅ Partida inserida (id={partida_id})")

        # --- Executar pipeline das 3 etapas ---
        resultado = executar_pipeline_partida(
            supabase_client,
            partida_id,
            gemini_client,
            analysis_settings,
            linter_settings,
            logger=logger,
        )

        if resultado is None:
            print("\n  🎉 Nenhum erro significativo detectado nesta partida.")
            return

        # --- Exibição ---
        elapsed = format_duration(time.time() - start_time)
        log_and_print(logger, f"\n⏱️  Tempo total: {elapsed}")
        exibir_resultado(resultado)

    except KeyboardInterrupt:
        print("\n\n⛔ Análise interrompida pelo usuário.")
    except Exception as error:
        logger.error("Falha no pipeline:\n%s", traceback.format_exc())
        print(f"\n❌ Erro: {error}")
        print("   Veja o log completo em:", LOG_PATH)
        sys.exit(1)


if __name__ == "__main__":
    main()
