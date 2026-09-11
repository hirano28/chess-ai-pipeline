"""Ferramenta interativa de feedback imediato para exercícios avulsos de xadrez.

Reaproveita a lógica de backend/agentes/revisar_pensamento.py (Stockfish,
chess_math, classificação de qualidade, prompt/schema do Gemini) para dar
feedback na hora sobre posições avulsas de "Guess the Move" (ex.: ChessTempo).

Ferramenta de uso pontual: sem barra de progresso e sem log em arquivo,
apenas prints diretos na tela.
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import chess
import chess.pgn
import google.genai as genai
from stockfish import Stockfish


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.revisar_pensamento import (  # noqa: E402
    AvaliacaoLance,
    RevisaoRaciocinio,
    Settings,
    build_prompt,
    call_gemini,
    classificar_qualidade_lance,
    gerar_revisao,
    load_settings,
    obter_linha_principal,
    obter_melhor_lance,
    obter_top_candidatos,
    strip_json_fences,
)
from backend.analise_engine.analisar_partidas import evaluate_position  # noqa: E402
from backend.common.chess_math import centipawns_para_win_percent  # noqa: E402
from backend.common.notacao_pt import (  # noqa: E402
    traduzir_lance_pt_para_san,
    traduzir_san_para_lance_pt,
)
from backend.common.progress import configurar_encoding_utf8  # noqa: E402
from backend.ingestao.common_ingestao import create_supabase_client  # noqa: E402

configurar_encoding_utf8()

# Ferramenta de uso pontual (1 posição por vez): pode pagar uma busca bem mais
# profunda que o STOCKFISH_SEARCHTIME_MS usado no processamento em lote.
EXERCICIO_AVULSO_SEARCHTIME_MS = int(
    os.getenv("EXERCICIO_AVULSO_SEARCHTIME_MS", "10000")
)

# Uma única instância do Stockfish é compartilhada entre requisições web
# concorrentes; sem lock, duas requisições simultâneas corrompem o diálogo
# com o subprocesso do motor e travam indefinidamente (sem erro, sem timeout).
ENGINE_LOCK_TIMEOUT_SECONDS = 60


class EngineIndisponivelError(RuntimeError):
    """Erro sinalizando que o lock do engine não foi obtido dentro do timeout."""


@contextlib.contextmanager
def _acquire_engine_lock(
    engine_lock: threading.Lock | None,
    timeout_seconds: float = ENGINE_LOCK_TIMEOUT_SECONDS,
) -> Iterator[None]:
    """Serializa o acesso ao engine; sem lock (uso via CLI), é um no-op."""

    if engine_lock is None:
        yield
        return
    if not engine_lock.acquire(timeout=timeout_seconds):
        raise EngineIndisponivelError(
            "Servidor ocupado, tente novamente em instantes."
        )
    try:
        yield
    finally:
        engine_lock.release()


def configure_console_logger() -> logging.Logger:
    """Logger só em console (sem arquivo), para os avisos de retry do Gemini."""

    logger = logging.getLogger("revisar_exercicio_avulso")
    logger.setLevel(logging.WARNING)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)
    return logger


@dataclass(frozen=True)
class LanceResolvido:
    """Um lance do usuário já resolvido para um move legal na posição.

    'interpretacao' diz sob qual idioma o texto digitado fez sentido ('PT' ou
    'EN'); 'san' é o SAN canônico (inglês) e 'lance_interpretado' é o mesmo
    lance de volta em português, para mostrar ao usuário o que entendemos.
    """

    move: chess.Move
    san: str
    interpretacao: str
    lance_interpretado: str


def resolver_lance_usuario(board: chess.Board, lance_texto: str) -> LanceResolvido:
    """Resolve o lance digitado tentando português primeiro e inglês como fallback.

    A ordem importa nos casos ambíguos: 'R' é Rei em português e Torre em inglês,
    e o usuário escreve em português, então a leitura em PT tem prioridade quando
    as duas são legais na posição. Se a leitura em PT for ilegal, tentamos o texto
    ORIGINAL sem tradução (já estava em inglês). Falhando as duas, propagamos o
    erro referente ao que o usuário realmente digitou, encadeado com a tentativa
    em português.
    """

    traduzido = traduzir_lance_pt_para_san(lance_texto)
    try:
        move = board.parse_san(traduzido)
        interpretacao = "PT"
    except ValueError as erro_pt:
        try:
            move = board.parse_san(lance_texto)
        except ValueError as erro_en:
            raise erro_en from erro_pt
        interpretacao = "EN"

    san = board.san(move)
    return LanceResolvido(
        move=move,
        san=san,
        interpretacao=interpretacao,
        lance_interpretado=traduzir_san_para_lance_pt(san),
    )


def resolver_sequencia_usuario(
    board: chess.Board, lances_texto: list[str]
) -> list[LanceResolvido]:
    """Resolve uma linha inteira de lances sem alterar o tabuleiro recebido.

    Cada lance é resolvido na posição em que ocorre (ver resolver_lance_usuario),
    então o mesmo texto pode ser lido como PT em um ponto e como EN em outro.
    """

    scratch = board.copy()
    resolvidos: list[LanceResolvido] = []
    for indice, lance_texto in enumerate(lances_texto):
        try:
            resolvido = resolver_lance_usuario(scratch, lance_texto)
        except ValueError as error:
            raise ValueError(
                f"Lance inválido na sequência: '{lance_texto}' "
                f"(posição {indice + 1}). {error}"
            ) from error
        scratch.push(resolvido.move)
        resolvidos.append(resolvido)
    return resolvidos


def ler_fen() -> chess.Board:
    """Pede a FEN da posição até que seja válida."""

    while True:
        fen = input("Cole a FEN da posição: ").strip()
        try:
            return chess.Board(fen)
        except ValueError as error:
            print(f"FEN inválida: {error}. Tente novamente.\n")


def ler_lance(board: chess.Board) -> chess.Move:
    """Pede o lance em SAN até que seja legal na posição."""

    while True:
        lance_texto = input("Lance jogado (SAN, ex: Cxe5 ou Txc3+): ").strip()
        try:
            return resolver_lance_usuario(board, lance_texto).move
        except ValueError as error:
            print(f"Lance inválido: {error}. Tente novamente.\n")


def ler_lances(board: chess.Board) -> list[str]:
    """Pede um ou vários lances SAN (separados por espaço/vírgula) e valida a linha.

    O 1º lance é do jogador, o 2º do adversário, o 3º do jogador, e assim por diante.
    """

    while True:
        entrada = input(
            "Seus lances (SAN, um ou vários; alternando com o adversário, "
            "ex: Cd5, Dc6, Bxe6): "
        ).strip()
        try:
            lances = normalizar_lances(None, entrada)
            resolver_sequencia_usuario(board, lances)
            return lances
        except ValueError as error:
            print(f"Sequência inválida: {error}. Tente novamente.\n")


def ler_texto_pensamento() -> str:
    """Lê múltiplas linhas de raciocínio até uma linha só com 'FIM'."""

    print("Descreva seu raciocínio (finalize com uma linha contendo apenas FIM):")
    linhas: list[str] = []
    while True:
        linha = input()
        if linha.strip().upper() == "FIM":
            break
        linhas.append(linha)
    return "\n".join(linhas).strip()


def perguntar_sim_nao(pergunta: str, default_sim: bool = True) -> bool:
    """Pergunta Y/n ao usuário, com valor padrão configurável."""

    sufixo = "[Y/n]" if default_sim else "[y/N]"
    resposta = input(f"{pergunta} {sufixo} ").strip().lower()
    if not resposta:
        return default_sim
    return resposta in {"y", "s", "sim", "yes"}


def avaliar_lance_avulso(
    engine: Stockfish,
    board: chess.Board,
    move: chess.Move,
    engine_lock: threading.Lock | None = None,
) -> AvaliacaoLance:
    """Avalia o lance jogado numa posição avulsa, reaproveitando o mesmo motor.

    Todo o uso do engine (avaliação antes, melhor lance, linha principal e
    avaliação depois) fica dentro de engine_lock, para não corromper o
    subprocesso do Stockfish quando requisições concorrentes o compartilham.
    """

    with _acquire_engine_lock(engine_lock):
        cor_jogada = "BRANCAS" if board.turn == chess.WHITE else "PRETAS"
        before_cp = evaluate_position(
            engine, board, cor_jogada, searchtime_ms=EXERCICIO_AVULSO_SEARCHTIME_MS
        )
        melhor_lance = obter_melhor_lance(
            engine, board, searchtime_ms=EXERCICIO_AVULSO_SEARCHTIME_MS
        )
        linha_principal = obter_linha_principal(engine, board)
        top_candidatos = obter_top_candidatos(engine, board)
        lance_jogado = board.san(move)
        board.push(move)
        after_cp = evaluate_position(
            engine, board, cor_jogada, searchtime_ms=EXERCICIO_AVULSO_SEARCHTIME_MS
        )
    queda_win_percent = round(
        centipawns_para_win_percent(before_cp) - centipawns_para_win_percent(after_cp),
        2,
    )
    return AvaliacaoLance(
        lance_jogado, melhor_lance, queda_win_percent, linha_principal, top_candidatos
    )


def resolver_posicao(posicao: str) -> chess.Board:
    """Resolve uma FEN direta ou um PGN completo para o tabuleiro de avaliação.

    Tenta primeiro como FEN; se falhar, tenta como PGN (com ou sem cabeçalhos)
    e aplica todos os lances, retornando a posição final resultante.
    """

    posicao = posicao.strip()
    try:
        return chess.Board(posicao)
    except ValueError:
        pass

    game = chess.pgn.read_game(io.StringIO(posicao))
    # chess.pgn.read_game nunca retorna None para texto não vazio: para lixo
    # sem estrutura de PGN, ele devolve um jogo com headers padrão e 0 lances.
    if game is None:
        raise ValueError("A posição informada não é uma FEN nem um PGN válido.")

    moves = list(game.mainline_moves())
    if not moves:
        raise ValueError(
            "A posição informada não é uma FEN nem um PGN válido "
            "(nenhum lance foi reconhecido)."
        )

    board = game.board()
    for move in moves:
        board.push(move)
    return board


def processar_revisao_avulsa(
    engine: Stockfish,
    gemini_client: Any,
    settings: Settings,
    logger: logging.Logger,
    fen: str,
    lance_san: str,
    texto_pensamento: str,
    engine_lock: threading.Lock | None = None,
) -> dict[str, Any]:
    """Núcleo reutilizável: avalia o lance, classifica a qualidade e chama o Gemini.

    Usado tanto pelo script interativo quanto pelo servidor web (backend/api).
    engine_lock, quando fornecido, serializa o acesso ao Stockfish compartilhado
    entre requisições concorrentes (ver _acquire_engine_lock).
    """

    board = chess.Board(fen)
    resolvido = resolver_lance_usuario(board, lance_san)

    avaliacao = avaliar_lance_avulso(engine, board, resolvido.move, engine_lock)
    qualidade_lance = classificar_qualidade_lance(
        avaliacao.queda_win_percent, settings.limiar_lance_bom, settings.limiar_lance_ruim
    )
    prompt = build_prompt(texto_pensamento, avaliacao, qualidade_lance)
    revisao = gerar_revisao(
        gemini_client,
        prompt,
        logger,
        avaliacao.linha_principal,
        avaliacao.top_candidatos,
        avaliacao.lance_jogado,
    )

    return {
        "lance_jogado": avaliacao.lance_jogado,
        "lance_interpretado": resolvido.lance_interpretado,
        "melhor_lance": avaliacao.melhor_lance,
        "queda_win_percent": avaliacao.queda_win_percent,
        "qualidade_lance": qualidade_lance,
        "qualidade_raciocinio": revisao.qualidade_raciocinio,
        "feedback_texto": revisao.feedback_texto,
        "analise_mestre": revisao.analise_mestre,
        "top_candidatos": revisao.top_candidatos,
        "checklist_rotina": revisao.checklist_rotina,
    }


def normalizar_lances(lances: list[str] | None, lance: str | None) -> list[str]:
    """Normaliza a entrada para uma lista de lances SAN (compat com 'lance' único).

    Aceita 'lances' (lista) OU 'lance' (string única, tratada como sequência de 1).
    Também divide uma única string com vários lances separados por espaço/vírgula.
    """

    brutos: list[str] = []
    if lances:
        brutos = list(lances)
    elif lance:
        brutos = [lance]

    tokens: list[str] = []
    for item in brutos:
        for parte in item.replace(",", " ").split():
            if parte.strip():
                tokens.append(parte.strip())

    if not tokens:
        raise ValueError("Informe ao menos um lance (campo 'lance' ou 'lances').")
    return tokens


def _descrever_contexto_sequencia(
    lances_sequencia: list[str],
    indice_atual: int,
    numero_lance_jogador: int,
) -> str:
    """Descreve, para o prompt, a posição deste lance do jogador dentro da linha."""

    linha_texto = " ".join(lances_sequencia)
    lance_atual = lances_sequencia[indice_atual]
    if indice_atual == 0:
        return (
            f"A linha completa informada é: {linha_texto}. Este é o 1º lance do "
            f"jogador ({lance_atual}), o ponto de partida do plano."
        )
    lance_adversario = lances_sequencia[indice_atual - 1]
    return (
        f"A linha completa informada é: {linha_texto}. Este é o {numero_lance_jogador}º "
        f"lance do jogador ({lance_atual}), jogado APÓS a resposta do adversário "
        f"'{lance_adversario}'."
    )


def build_prompt_resumo_sequencia(
    texto_pensamento: str, avaliacoes_jogador: list[dict[str, Any]]
) -> str:
    """Monta o prompt do resumo geral que comenta a sequência do jogador como um todo."""

    linhas = []
    for item in avaliacoes_jogador:
        candidatos = ", ".join(
            f"{cand['lance']} ({cand['avaliacao']})"
            for cand in item.get("top_candidatos") or []
        )
        linhas.append(
            f"- lance {item['lance_jogado']}: qualidade {item['qualidade_lance']}, "
            f"melhor do motor {item['melhor_lance']}, candidatos: {candidatos or '—'}"
        )
    resumo_lances = "\n".join(linhas)

    return f"""Você é um treinador de xadrez. Um jogador resolveu um exercício de
"adivinhe o lance" que envolvia uma SEQUÊNCIA de lances dele (alternados com as
respostas do adversário).

O pensamento declarado pelo jogador para a sequência inteira foi:
\"\"\"{texto_pensamento}\"\"\"

Avaliação objetiva de cada lance DO JOGADOR na sequência (do motor):
{resumo_lances}

Escreva um RESUMO GERAL curto (2 a 4 frases) comentando a sequência como um todo.
Foque especialmente em: o raciocínio inicial declarado se manteve válido ao longo
da sequência? A necessidade de reposicionar peças (ex.: mover a mesma peça de novo)
realmente invalidou a ideia original, ou fazia parte do plano? Seja construtivo e
objetivo. Responda apenas com o texto do resumo, sem markdown e sem JSON."""


def gerar_resumo_sequencia(
    gemini_client: Any,
    logger: logging.Logger,
    texto_pensamento: str,
    avaliacoes_jogador: list[dict[str, Any]],
) -> str | None:
    """Gera o resumo geral da sequência; retorna None em caso de falha (é opcional)."""

    if len(avaliacoes_jogador) < 2:
        return None
    prompt = build_prompt_resumo_sequencia(texto_pensamento, avaliacoes_jogador)
    try:
        return strip_json_fences(call_gemini(gemini_client, prompt, logger))
    except Exception:
        logger.warning("Falha ao gerar resumo geral da sequência; seguindo sem ele.")
        return None


def processar_revisao_sequencia(
    engine: Stockfish,
    gemini_client: Any,
    settings: Settings,
    logger: logging.Logger,
    fen: str,
    lances_san: list[str],
    texto_pensamento: str,
    engine_lock: threading.Lock | None = None,
) -> dict[str, Any]:
    """Avalia uma SEQUÊNCIA de lances a partir de uma posição.

    Convenção: o 1º lance é do jogador, o 2º é resposta do adversário, o 3º é do
    jogador de novo, e assim por diante (alternância). Apenas os lances DO JOGADOR
    (índices pares) são avaliados quanto à qualidade; os do adversário só avançam a
    posição. Retorna uma lista de avaliações (uma por lance do jogador) + resumo.
    """

    board = chess.Board(fen)
    # Resolve a linha inteira antes de gastar motor/Gemini: assim uma sequência
    # com lance inválido no meio falha de imediato e o contexto passado ao prompt
    # já usa o SAN canônico (inglês), e não o texto cru digitado em português.
    resolvidos = resolver_sequencia_usuario(board, lances_san)
    lances_reais = [item.san for item in resolvidos]

    avaliacoes: list[dict[str, Any]] = []
    numero_lance_jogador = 0

    for indice, resolvido in enumerate(resolvidos):
        move = board.parse_san(resolvido.san)
        eh_do_jogador = indice % 2 == 0

        if eh_do_jogador:
            numero_lance_jogador += 1
            avaliacao = avaliar_lance_avulso(engine, board, move, engine_lock)
            qualidade_lance = classificar_qualidade_lance(
                avaliacao.queda_win_percent,
                settings.limiar_lance_bom,
                settings.limiar_lance_ruim,
            )
            contexto = _descrever_contexto_sequencia(
                lances_reais, indice, numero_lance_jogador
            )
            prompt = build_prompt(
                texto_pensamento, avaliacao, qualidade_lance, contexto
            )
            revisao = gerar_revisao(
                gemini_client,
                prompt,
                logger,
                avaliacao.linha_principal,
                avaliacao.top_candidatos,
                avaliacao.lance_jogado,
            )
            avaliacoes.append(
                {
                    "indice_na_sequencia": indice + 1,
                    "lance_jogado": avaliacao.lance_jogado,
                    "lance_interpretado": resolvido.lance_interpretado,
                    "melhor_lance": avaliacao.melhor_lance,
                    "queda_win_percent": avaliacao.queda_win_percent,
                    "qualidade_lance": qualidade_lance,
                    "qualidade_raciocinio": revisao.qualidade_raciocinio,
                    "feedback_texto": revisao.feedback_texto,
                    "analise_mestre": revisao.analise_mestre,
                    "top_candidatos": revisao.top_candidatos,
                    "checklist_rotina": revisao.checklist_rotina,
                }
            )
        else:
            # Lance do adversário: apenas avança a posição, não é avaliado
            # (operação de tabuleiro pura, sem acesso ao engine).
            board.push(move)

    resumo_geral = gerar_resumo_sequencia(
        gemini_client, logger, texto_pensamento, avaliacoes
    )

    return {
        "fen": fen,
        "lances": lances_reais,
        # O lance principal do exercício (1º lance do jogador), em português,
        # exatamente como foi entendido — é o que o dashboard destaca.
        "lance_interpretado": resolvidos[0].lance_interpretado,
        "avaliacoes": avaliacoes,
        "resumo_geral": resumo_geral,
    }


def imprimir_resultado(resultado: dict[str, Any]) -> None:
    """Imprime o feedback formatado na tela."""

    print("\n" + "=" * 60)
    print(f"Lance jogado:            {resultado['lance_jogado']}")
    lance_interpretado = resultado.get("lance_interpretado")
    if lance_interpretado:
        print(f"Lance interpretado (PT): {lance_interpretado}")
    print(f"Melhor lance (motor):    {resultado['melhor_lance']}")
    top_candidatos = resultado.get("top_candidatos") or []
    if top_candidatos:
        candidatos_texto = ", ".join(
            f"{cand['lance']} ({cand['avaliacao']})" for cand in top_candidatos
        )
        print(f"Top candidatos (motor):  {candidatos_texto}")
    print(f"Queda de win%:           {resultado['queda_win_percent']}")
    print(f"Qualidade do lance:      {resultado['qualidade_lance']}")
    print(f"Qualidade do raciocínio: {resultado['qualidade_raciocinio']}")
    print(f"Feedback: {resultado['feedback_texto']}")
    print(f"Análise do mestre: {resultado['analise_mestre']}")
    checklist = resultado.get("checklist_rotina") or {}
    if checklist:
        print("Checklist da rotina:")
        for chave, valor in checklist.items():
            print(f"  - {chave}: {valor}")
    print("=" * 60 + "\n")


def imprimir_resultado_sequencia(resultado: dict[str, Any]) -> None:
    """Imprime, um bloco por lance do jogador, o resultado de uma sequência."""

    avaliacoes = resultado.get("avaliacoes") or []
    print(f"\nLinha avaliada: {' '.join(resultado.get('lances') or [])}")
    print(f"Lances do jogador avaliados: {len(avaliacoes)}")
    for ordem, item in enumerate(avaliacoes, start=1):
        print(f"\n----- Lance {ordem} do jogador "
              f"(posição {item['indice_na_sequencia']} na linha) -----")
        imprimir_resultado(item)
    resumo = resultado.get("resumo_geral")
    if resumo:
        print("===== RESUMO GERAL DA SEQUÊNCIA =====")
        print(resumo)
        print("=" * 60 + "\n")


def salvar_exercicio(
    client: Any,
    fen: str,
    texto_pensamento: str,
    resultado: dict[str, Any],
) -> str | None:
    """Insere o exercício avulso revisado em revisao_exercicio_avulso.

    Retorna o id da linha criada (usado pelo frontend para marcar o exercício
    salvo como o "item ativo" no histórico, sobrevivendo a um F5), ou None se
    a resposta do Supabase não trouxer o id por algum motivo inesperado.
    """

    resposta = (
        client.table("revisao_exercicio_avulso")
        .insert(
            {
                "fen": fen,
                "lance_jogado": resultado["lance_jogado"],
                "melhor_lance": resultado["melhor_lance"],
                "queda_win_percent": resultado["queda_win_percent"],
                "texto_pensamento": texto_pensamento,
                "qualidade_lance": resultado["qualidade_lance"],
                "qualidade_raciocinio": resultado["qualidade_raciocinio"],
                "feedback_texto": resultado["feedback_texto"],
                "origem": "GUESS_THE_MOVE",
            }
        )
        .execute()
    )
    linhas = resposta.data or []
    return linhas[0]["id"] if linhas else None


def executar_um_exercicio(
    engine: Stockfish,
    gemini_client: Any,
    supabase_client: Any,
    settings: Settings,
    logger: logging.Logger,
) -> None:
    """Executa o ciclo completo de um único exercício avulso."""

    board = ler_fen()
    fen = board.fen()
    lances_san = ler_lances(board)
    texto_pensamento = ler_texto_pensamento()

    print("\nAvaliando com o Stockfish e consultando o Gemini...")
    resultado = processar_revisao_sequencia(
        engine, gemini_client, settings, logger, fen, lances_san, texto_pensamento
    )

    imprimir_resultado_sequencia(resultado)

    avaliacoes = resultado.get("avaliacoes") or []
    if avaliacoes and perguntar_sim_nao(
        "Salvar este exercício (o 1º lance do jogador)?"
    ):
        salvar_exercicio(supabase_client, fen, texto_pensamento, avaliacoes[0])
        print("Exercício salvo.\n")
    else:
        print("Exercício não salvo.\n")


def run() -> None:
    """Loop interativo principal: pede exercícios até o usuário encerrar."""

    logger = configure_console_logger()
    settings = load_settings()
    supabase_client = create_supabase_client(
        settings.supabase_url, settings.supabase_service_role_key
    )
    gemini_client = genai.Client(api_key=settings.gemini_api_key)

    print("Inicializando o Stockfish...")
    engine = Stockfish(
        path=settings.stockfish_path,
        depth=settings.stockfish_depth,
        turn_perspective=False,
    )
    print("Pronto. Vamos revisar seus exercícios avulsos.\n")

    try:
        while True:
            try:
                executar_um_exercicio(
                    engine, gemini_client, supabase_client, settings, logger
                )
            except Exception as error:
                print(f"\nOcorreu um erro neste exercício: {error}\nVamos tentar de novo.\n")

            if not perguntar_sim_nao("Fazer outro exercício?"):
                break
    finally:
        try:
            engine.send_quit_command()
        except Exception:
            pass
        print("Encerrado.")


if __name__ == "__main__":
    run()
