"""Consulta ao vivo: ajuda para pensar numa posição da partida em andamento (D-67).

O jogador espelha no aplicativo, lance a lance, uma partida que está jogando
contra um bot no Lichess ou no Chess.com. Quando trava ("não tenho plano", "não
sei como seguir"), pede uma consulta, podendo ou não dizer o que está pensando.

A resposta vem em três camadas, e a ordem é o ponto da feature:

1. **Pensar** — o que a posição pede, o que o raciocínio do jogador deixou de
   fora, perguntas para se fazer e planos descritos em palavras. **Nenhum lance
   concreto.** Um lance aqui transformaria a consulta num oráculo, e o que se
   quer treinar é justamente decidir sozinho.
2. **Ideias** — os lances candidatos do motor, cada um com a ideia por trás, em
   ordem alfabética: a ordem do Stockfish revelaria qual é o melhor.
3. **Motor** — o melhor lance, a avaliação e as linhas. Só com clique explícito.

As três vêm de uma única chamada ao Gemini (a terceira nem usa Gemini: é o
Stockfish). A ocultação das camadas 2 e 3 é pedagógica, feita na tela, e não uma
barreira de segurança — a feature é de um usuário só, e ele sabe o que tem ali.

Nada aqui fala com a API do Lichess ou do Chess.com: o espelhamento é manual.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any

import chess
from pydantic import BaseModel, Field, ValidationError

from backend.agentes.explicador_posicao import (
    analisar_posicao_com_engine,
    detectar_lances_inventados,
    inspecionar_elementos_tabuleiro,
    obter_lances_permitidos,
)
from backend.agentes.revisar_pensamento import call_gemini, strip_json_fences
from backend.analise_engine.analisar_partidas import STOCKFISH_SEARCHTIME_MS

PLATAFORMAS = ("LICHESS", "CHESSCOM", "OUTRA")
# Lance em notação portuguesa: C(avalo), B(ispo), T(orre), D(ama), R(ei).
PADRAO_LANCE_PT = re.compile(r"\b[CBTDR][a-h]?[1-8]?x?[a-h][1-8](?:=[CBTD])?[+#]?(?!\w)")
CORES = ("BRANCAS", "PRETAS")
PENSAMENTO_MAX_CARACTERES = 1500


def usuarios_com_acesso() -> frozenset[str]:
    """IDs (auth.users) liberados para a consulta ao vivo.

    Lido de `CONSULTA_AO_VIVO_USUARIOS`, separado por vírgula. **Fecha por
    padrão**: variável ausente ou vazia significa ninguém. A feature é exclusiva
    do dono do projeto por decisão dele, e um esquecimento de configuração não
    pode abri-la para todos.

    Lido a cada chamada, e não uma vez no import, para os testes poderem trocar
    a variável sem recarregar o módulo.
    """

    bruto = os.getenv("CONSULTA_AO_VIVO_USUARIOS", "")
    return frozenset(parte.strip() for parte in bruto.split(",") if parte.strip())


def limite_por_partida() -> int:
    """Quantas consultas cabem numa mesma partida espelhada.

    Um teto por partida, além do diário, é o que obriga a escolher os momentos
    de dúvida de verdade — que é o hábito que se quer criar — e segura o gasto
    de Gemini. Consultar a cada lance seria jogar com o motor do lado.
    """

    try:
        return max(1, int(os.getenv("CONSULTA_MAX_POR_PARTIDA", "3")))
    except ValueError:
        return 3


class PlanoConsulta(BaseModel):
    titulo: str = Field(description="Nome curto do plano, sem lances concretos.")
    explicacao: str = Field(description="Por que esse plano faz sentido nesta posição.")


class IdeiaCandidata(BaseModel):
    lance: str = Field(description="Um dos lances candidatos fornecidos, em SAN.")
    ideia: str = Field(description="A ideia por trás do lance, sem dizer se é o melhor.")


class RespostaConsulta(BaseModel):
    """O que o Gemini devolve. A camada do motor é montada à parte, do Stockfish."""

    leitura_da_posicao: str
    sobre_o_seu_raciocinio: str | None = None
    perguntas_guia: list[str] = Field(default_factory=list)
    planos: list[PlanoConsulta] = Field(default_factory=list)
    ideias_candidatas: list[IdeiaCandidata] = Field(default_factory=list)


def normalizar_escolha(valor: str | None, opcoes: tuple[str, ...], campo: str) -> str:
    limpo = (valor or "").strip().upper()
    if limpo not in opcoes:
        raise ValueError(f"{campo} inválido: '{valor}'. Use um de: {', '.join(opcoes)}.")
    return limpo


def reconstruir_partida(fen_inicial: str | None, lances: list[str]) -> chess.Board:
    """Reaplica os lances espelhados sobre a posição inicial.

    A posição de consulta nunca é aceita pronta do cliente: é o resultado dos
    lances. Assim a consulta sabe o número do lance, guarda a partida inteira e
    pode ser casada depois com a partida real que a coleta trouxer.

    Aceita SAN (o que o tabuleiro da tela produz) e, como segunda chance, UCI.
    """

    try:
        board = chess.Board(fen_inicial) if fen_inicial else chess.Board()
    except ValueError as error:
        raise ValueError(f"Posição inicial inválida: {error}") from error
    if board.status() != chess.STATUS_VALID:
        raise ValueError("Posição inicial inválida: a FEN não descreve uma posição legal.")

    for indice, texto in enumerate(lances):
        lance = (texto or "").strip()
        try:
            move = board.parse_san(lance)
        except ValueError:
            try:
                move = chess.Move.from_uci(lance)
            except ValueError:
                move = None
            if move is None or move not in board.legal_moves:
                raise ValueError(
                    f"Lance {indice + 1} ('{lance}') não é legal na posição espelhada."
                ) from None
        board.push(move)
    return board


def _linhas_para_camadas(linhas_taticas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "lance": linha["lance"],
            "avaliacao": linha["avaliacao"],
            "sequencia": linha.get("pv_san") or [],
        }
        for linha in linhas_taticas
        if linha.get("lance")
    ]


def build_prompt_consulta(
    board: chess.Board,
    cor_jogador: str,
    lances_san: list[str],
    analise: dict[str, Any],
    elementos: dict[str, Any],
    pensamento: dict[str, str | None],
    adversario: str | None,
) -> str:
    """Prompt da consulta. As regras que protegem as camadas vêm explícitas."""

    candidatos = _linhas_para_camadas(analise["linhas_taticas"])
    candidatos_str = "\n".join(
        f"  - {c['lance']} (avaliação {c['avaliacao']}; sequência: {' '.join(c['sequencia']) or c['lance']})"
        for c in candidatos
    ) or "  (o motor não devolveu candidatos)"

    mat = elementos["material"]
    indefesas_jogador = ", ".join(elementos["pecas_indefesas"][cor_jogador]) or "nenhuma"
    adversaria = "PRETAS" if cor_jogador == "BRANCAS" else "BRANCAS"
    indefesas_adversario = ", ".join(elementos["pecas_indefesas"][adversaria]) or "nenhuma"
    rei_jogador = elementos["seguranca_rei"].get(cor_jogador, {}).get("resumo", "?")
    rei_adversario = elementos["seguranca_rei"].get(adversaria, {}).get("resumo", "?")

    partes_pensamento = [
        ("O que acho que está acontecendo", pensamento.get("situacao")),
        ("Lances que considerei", pensamento.get("candidatos")),
        ("O que me trava", pensamento.get("trava")),
    ]
    tem_pensamento = any((texto or "").strip() for _, texto in partes_pensamento)
    if tem_pensamento:
        pensamento_str = "\n".join(
            f"- {rotulo}: {texto.strip()}"
            for rotulo, texto in partes_pensamento
            if (texto or "").strip()
        )
        instrucao_raciocinio = (
            '"sobre_o_seu_raciocinio": comente o raciocínio do jogador com franqueza: o que '
            "está certo, o que falta e que fator da posição ele não levou em conta. Pode citar "
            "casas e peças, mas NÃO cite lances."
        )
    else:
        pensamento_str = "(o jogador não descreveu o que está pensando)"
        instrucao_raciocinio = '"sobre_o_seu_raciocinio": null.'

    return f"""Você é um treinador de xadrez experiente sentado ao lado do seu aluno.
Ele está jogando uma partida {'contra ' + adversario if adversario else 'contra um bot'}, joga de {cor_jogador}, é a vez dele e ele travou: não sabe como prosseguir.
Seu trabalho NÃO é dar o lance. É ensinar a pensar nesta posição para que ELE decida.

POSIÇÃO:
- FEN: {board.fen()}
- Lance número: {board.fullmove_number}
- Partida até aqui (SAN): {' '.join(lances_san) or '(histórico não disponível; use só a posição)'}

DADOS OBJETIVOS (use para não errar; não repita números ao aluno):
- Avaliação do motor: {analise['descricao']}
- Material: {mat['descricao']}
- Peças soltas/atacadas do aluno: {indefesas_jogador}
- Peças soltas/atacadas do adversário: {indefesas_adversario}
- Rei do aluno: {rei_jogador}
- Rei do adversário: {rei_adversario}
- Lances candidatos do motor, do melhor para o pior:
{candidatos_str}

O QUE O ALUNO ESTÁ PENSANDO:
{pensamento_str}

RESPONDA preenchendo:
- "leitura_da_posicao": 2 a 4 frases sobre o que a posição pede (estrutura de peões, peças ativas e inativas, segurança dos reis, desequilíbrios). SEM lances e SEM números de avaliação.
- {instrucao_raciocinio}
- "perguntas_guia": 2 a 4 perguntas curtas que o aluno deve se fazer antes de jogar. SEM lances.
- "planos": 1 a 3 planos, cada um com "titulo" e "explicacao", descritos em palavras (casas e peças podem aparecer; lances não).
- "ideias_candidatas": para CADA lance candidato do motor listado acima, um objeto com "lance" (exatamente como listado) e "ideia" (a ideia por trás dele, em 1 a 2 frases). NÃO diga qual é o melhor, NÃO compare, NÃO cite avaliações.

REGRAS OBRIGATÓRIAS:
- Em "leitura_da_posicao", "sobre_o_seu_raciocinio", "perguntas_guia" e "planos" é PROIBIDO escrever lances em notação (ex.: Nf3, exd5, O-O, Cf3, "lance e4"). Descreva ideias, não jogadas.
- Nunca invente lances, peças ou casas.
- Escreva em português do Brasil.
- Responda ESTRITAMENTE com um único JSON válido, sem texto antes ou depois e sem fences markdown.

{{
  "leitura_da_posicao": "string",
  "sobre_o_seu_raciocinio": "string ou null",
  "perguntas_guia": ["string"],
  "planos": [{{"titulo": "string", "explicacao": "string"}}],
  "ideias_candidatas": [{{"lance": "string", "ideia": "string"}}]
}}"""


def problemas_da_resposta(
    resposta: RespostaConsulta,
    candidatos_san: list[str],
    permitidos: set[str],
) -> list[str]:
    """O que a resposta fez de errado, em frases que servem de correção ao modelo.

    A camada "pensar" não pode ter lance NENHUM — por isso a verificação usa um
    conjunto de permitidos vazio: qualquer lance escrito ali é problema, mesmo
    que legal. Na camada de ideias vale o contrário: só lances reais.
    """

    problemas: list[str] = []
    textos_pensar = [
        resposta.leitura_da_posicao,
        resposta.sobre_o_seu_raciocinio or "",
        *resposta.perguntas_guia,
        *(f"{plano.titulo} {plano.explicacao}" for plano in resposta.planos),
    ]
    texto_pensar = " ".join(textos_pensar)
    lances_na_camada_pensar = detectar_lances_inventados(texto_pensar, set())
    # O detector herdado do explicador só conhece a notação inglesa. Em
    # português "Cf3" e "Dxd5" passariam direto pela camada que promete não
    # ter lance nenhum.
    for achado in PADRAO_LANCE_PT.findall(texto_pensar):
        if achado not in lances_na_camada_pensar:
            lances_na_camada_pensar.append(achado)
    if lances_na_camada_pensar:
        problemas.append(
            "A parte de pensar citou lances, o que é proibido: "
            + ", ".join(lances_na_camada_pensar)
        )

    for ideia in resposta.ideias_candidatas:
        if ideia.lance not in candidatos_san:
            problemas.append(f"'{ideia.lance}' não é um dos lances candidatos fornecidos")
        inventados = detectar_lances_inventados(ideia.ideia, permitidos)
        if inventados:
            problemas.append(
                f"A ideia de {ideia.lance} citou lances inexistentes: {', '.join(inventados)}"
            )

    if not resposta.leitura_da_posicao.strip():
        problemas.append("'leitura_da_posicao' veio vazia")
    return problemas


def resposta_deterministica(
    elementos: dict[str, Any], cor_jogador: str, candidatos_san: list[str]
) -> RespostaConsulta:
    """Resposta sem Gemini, quando ele falha ou insiste em violar as regras.

    É pobre de propósito: só afirma o que o tabuleiro prova. Melhor uma consulta
    modesta e verdadeira do que uma eloquente com um lance escondido na camada
    que prometeu não ter nenhum.
    """

    adversaria = "PRETAS" if cor_jogador == "BRANCAS" else "BRANCAS"
    leitura = [elementos["material"]["descricao"] + "."]
    rei = elementos["seguranca_rei"].get(cor_jogador, {}).get("resumo")
    if rei:
        leitura.append(f"Seu rei: {rei.lower()}.")
    soltas = elementos["pecas_indefesas"][cor_jogador]
    if soltas:
        leitura.append("Atenção às suas peças sem defesa suficiente: " + "; ".join(soltas) + ".")
    alvos = elementos["pecas_indefesas"][adversaria]
    if alvos:
        leitura.append("Do outro lado há alvos: " + "; ".join(alvos) + ".")

    return RespostaConsulta(
        leitura_da_posicao=" ".join(leitura),
        sobre_o_seu_raciocinio=None,
        perguntas_guia=[
            "O que o adversário ameaça com o último lance dele?",
            "Qual é a sua peça menos ativa, e onde ela trabalharia melhor?",
            "Algum xeque, captura ou ameaça direta muda a posição agora?",
        ],
        planos=[],
        ideias_candidatas=[
            IdeiaCandidata(lance=lance, ideia="O motor considera este lance; pense no que ele muda.")
            for lance in candidatos_san
        ],
    )


def gerar_resposta(
    client: Any,
    prompt: str,
    elementos: dict[str, Any],
    cor_jogador: str,
    candidatos_san: list[str],
    permitidos: set[str],
    logger: logging.Logger,
) -> tuple[RespostaConsulta, str]:
    """Uma chamada ao Gemini, no máximo uma correção, e o fallback se preciso.

    Devolve a resposta e a origem ("gemini" ou "fallback"). Uma só correção de
    propósito: o usuário está com o relógio correndo e pediu economia de cota.
    """

    if client is None:
        return resposta_deterministica(elementos, cor_jogador, candidatos_san), "fallback"

    tentativa_prompt = prompt
    for tentativa in range(2):
        try:
            bruto = call_gemini(client, tentativa_prompt, logger)
            resposta = RespostaConsulta.model_validate_json(strip_json_fences(bruto))
        except ValidationError as error:
            problemas = [f"JSON inválido: {error}"]
        except Exception as error:
            logger.warning("Consulta ao vivo: falha ao chamar o Gemini (%s).", error)
            break
        else:
            problemas = problemas_da_resposta(resposta, candidatos_san, permitidos)
            if not problemas:
                return resposta, "gemini"

        logger.warning("Consulta ao vivo: resposta rejeitada (tentativa %d): %s", tentativa + 1, problemas)
        tentativa_prompt = (
            f"{prompt}\n\nA resposta anterior foi rejeitada por estes motivos:\n- "
            + "\n- ".join(problemas)
            + "\nCorrija e responda apenas com o JSON válido."
        )

    return resposta_deterministica(elementos, cor_jogador, candidatos_san), "fallback"


def win_percent_do_jogador(analise: dict[str, Any], cor_jogador: str) -> float:
    chave = "win_percent_brancas" if cor_jogador == "BRANCAS" else "win_percent_pretas"
    return float(analise[chave])


def consultar_posicao(
    engine: Any,
    gemini_client: Any,
    logger: logging.Logger,
    lances: list[str],
    cor_jogador: str,
    fen_inicial: str | None = None,
    pensamento: dict[str, str | None] | None = None,
    adversario: str | None = None,
    engine_lock: threading.Lock | None = None,
) -> dict[str, Any]:
    """Monta a consulta completa para a posição depois de `lances`.

    ValueError para entrada inválida (lance ilegal, cor errada, partida já
    terminada, vez do adversário) — o servidor devolve 400 com a mensagem.
    """

    cor = normalizar_escolha(cor_jogador, CORES, "Cor do jogador")
    board = reconstruir_partida(fen_inicial, lances)
    if board.is_game_over():
        raise ValueError("A partida espelhada já terminou; não há decisão a tomar.")
    vez = "BRANCAS" if board.turn == chess.WHITE else "PRETAS"
    if vez != cor:
        raise ValueError(
            "A vez é do adversário. A consulta serve para a SUA decisão: espelhe o "
            "lance dele primeiro."
        )

    pensamento_limpo = {
        chave: (valor or "").strip()[:PENSAMENTO_MAX_CARACTERES] or None
        for chave, valor in (pensamento or {}).items()
        if chave in ("situacao", "candidatos", "trava")
    }

    # SAN canônico reconstruído (o cliente pode ter mandado UCI).
    replay = chess.Board(fen_inicial) if fen_inicial else chess.Board()
    lances_san: list[str] = []
    for move in board.move_stack:
        lances_san.append(replay.san(move))
        replay.push(move)

    elementos = inspecionar_elementos_tabuleiro(board)
    analise = analisar_posicao_com_engine(
        engine, board, searchtime_ms=STOCKFISH_SEARCHTIME_MS, engine_lock=engine_lock
    )
    linhas = _linhas_para_camadas(analise["linhas_taticas"])
    candidatos_san = [linha["lance"] for linha in linhas]
    permitidos = obter_lances_permitidos(board, analise["linhas_taticas"])

    prompt = build_prompt_consulta(
        board, cor, lances_san, analise, elementos, pensamento_limpo, adversario
    )
    resposta, origem = gerar_resposta(
        gemini_client, prompt, elementos, cor, candidatos_san, permitidos, logger
    )

    # A ordem alfabética esconde o ranking do motor na camada de ideias; uma
    # ideia por candidato, e só candidato real.
    ideia_por_lance = {ideia.lance: ideia.ideia for ideia in resposta.ideias_candidatas}
    ideias = [
        {"lance": lance, "ideia": ideia_por_lance.get(lance)}
        for lance in sorted(candidatos_san, key=str.lower)
    ]

    return {
        "fen": board.fen(),
        "fen_inicial": fen_inicial or chess.STARTING_FEN,
        "lances_san": lances_san,
        "numero_lance": board.fullmove_number,
        "cor_jogador": cor,
        "pensamento": pensamento_limpo,
        "camada_pensar": {
            "leitura_da_posicao": resposta.leitura_da_posicao,
            "sobre_o_seu_raciocinio": resposta.sobre_o_seu_raciocinio,
            "perguntas_guia": resposta.perguntas_guia,
            "planos": [plano.model_dump() for plano in resposta.planos],
        },
        "camada_ideias": {"ideias": ideias},
        "camada_motor": {
            "melhor_lance": candidatos_san[0] if candidatos_san else None,
            "avaliacao": analise["descricao"],
            "win_percent_jogador": round(win_percent_do_jogador(analise, cor), 1),
            "linhas": linhas,
        },
        "gerado_por": origem,
    }
