"""Consulta ao vivo: ajuda para pensar numa posição da partida em andamento (D-67, D-70).

O jogador espelha no aplicativo (ou sincroniza, D-69) uma partida que está
jogando. Quando trava ("não tenho plano", "não sei como seguir"), pede uma
consulta, podendo ou não dizer o que está pensando.

A resposta ensina a AVALIAR a posição, e nada além disso (D-70):

- **Tipo de posição** — o que caracteriza esta posição e o que isso exige do
  raciocínio (calcular? manobrar? defender?).
- **Sobre o seu raciocínio** — o que o jogador acertou e o que deixou de fora.
- **Roteiro** — os passos da avaliação, em ordem, cada um com o PORQUÊ de
  olhar aquilo nesta posição.
- **Princípio** — a regra geral que vale levar para outras partidas.

**Nenhum lance, nem candidatos, nem o lance do motor.** Até o D-69 a consulta
tinha mais duas camadas (ideias candidatas e o lance do motor) escondidas atrás
de cliques; o dono da feature pediu para tirá-las: o que ele quer é aprender a
pensar, não receber a resposta. O Stockfish continua rodando, mas só para o
Gemini não errar a leitura (uma posição tática pede outro roteiro que uma
calma) e para o desfecho do D-68 — o que ele diz fica gravado e nunca sai pela
API.
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
)
from backend.agentes.revisar_pensamento import call_gemini, strip_json_fences
from backend.analise_engine.analisar_partidas import STOCKFISH_SEARCHTIME_MS

PLATAFORMAS = ("LICHESS", "CHESSCOM", "OUTRA")
# Lance em notação portuguesa: C(avalo), B(ispo), T(orre), D(ama), R(ei).
PADRAO_LANCE_PT = re.compile(r"\b[CBTDR][a-h]?[1-8]?x?[a-h][1-8](?:=[CBTD])?[+#]?(?!\w)")
# Lance descrito em palavras: "leve o cavalo para f5", "avance o peão até h5".
# É o jeito de dar o lance sem escrever notação, e o roteiro promete não dar.
PADRAO_LANCE_POR_EXTENSO = re.compile(
    # Só formas de comando ("leve", "levar", "levando"): "jogador" ou
    # "movimento" seguidos de "para f7" não são lance nenhum.
    r"\b(?:lev(?:ar|e|ando)|jog(?:ar|ue|ando)|mov(?:er|a|endo)|coloc(?:ar|ando)|coloque"
    r"|avan(?:çar|ce|çando)|recu(?:ar|e|ando)|(?:re)?posicion(?:ar|e|ando)|traz(?:er|endo)|traga"
    r"|desloc(?:ar|ando)|desloque|transf(?:erir|ira|erindo)|pul(?:ar|e|ando))\b"
    r"[^.;:?!]{0,40}?\b(?:para|até|em direção a)\s+(?:a\s+casa\s+)?[a-h][1-8]\b",
    re.IGNORECASE,
)
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
    de Gemini.
    """

    try:
        return max(1, int(os.getenv("CONSULTA_MAX_POR_PARTIDA", "3")))
    except ValueError:
        return 3


class PassoDoRoteiro(BaseModel):
    o_que_avaliar: str = Field(description="O que olhar neste passo, sem lances.")
    por_que: str = Field(description="Por que olhar isso NESTA posição.")


class RespostaConsulta(BaseModel):
    """O que o Gemini devolve (e o fallback imita)."""

    tipo_de_posicao: str
    sobre_o_seu_raciocinio: str | None = None
    roteiro: list[PassoDoRoteiro] = Field(default_factory=list)
    principio: str


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


def _linhas_do_motor(linhas_taticas: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    """Prompt da consulta. As regras que impedem dar o lance vêm explícitas."""

    candidatos = _linhas_do_motor(analise["linhas_taticas"])
    candidatos_str = "\n".join(
        f"  - {c['lance']} (avaliação {c['avaliacao']}; sequência: {' '.join(c['sequencia']) or c['lance']})"
        for c in candidatos
    ) or "  (o motor não devolveu linhas)"

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
            '"sobre_o_seu_raciocinio": comente o PROCESSO de raciocínio do aluno com franqueza: '
            "o que ele avaliou bem, que fator da posição deixou de fora e em que ordem deveria ter "
            "olhado as coisas. Se ele listou lances, NÃO diga qual é bom ou ruim: diga o que ele "
            "precisaria ter verificado para decidir sozinho."
        )
    else:
        pensamento_str = "(o aluno não descreveu o que está pensando)"
        instrucao_raciocinio = '"sobre_o_seu_raciocinio": null.'

    return f"""Você é um treinador de xadrez experiente sentado ao lado do seu aluno.
Ele está jogando uma partida {'contra ' + adversario if adversario else 'online'}, joga de {cor_jogador}, é a vez dele e ele travou.
Ele NÃO quer saber qual é o melhor lance nem quais lances considerar. Ele quer aprender COMO AVALIAR esta posição e POR QUE avaliar desse jeito, para decidir sozinho.

POSIÇÃO:
- FEN: {board.fen()}
- Lance número: {board.fullmove_number}
- Partida até aqui (SAN): {' '.join(lances_san) or '(histórico não disponível; use só a posição)'}

DADOS OBJETIVOS (só para você não errar a leitura; NUNCA os repasse ao aluno):
- Avaliação do motor: {analise['descricao']}
- Material: {mat['descricao']}
- Peças soltas/atacadas do aluno: {indefesas_jogador}
- Peças soltas/atacadas do adversário: {indefesas_adversario}
- Rei do aluno: {rei_jogador}
- Rei do adversário: {rei_adversario}
- Linhas do motor (SEGREDO: servem só para você saber se a posição é tática ou calma, se pede ataque ou defesa):
{candidatos_str}

O QUE O ALUNO ESTÁ PENSANDO:
{pensamento_str}

RESPONDA preenchendo:
- "tipo_de_posicao": 2 a 4 frases dizendo que tipo de posição é esta (tática ou calma; aberta ou fechada; quem tem a iniciativa; quais desequilíbrios existem) e o que isso exige do raciocínio agora (calcular lances forçantes, melhorar peças, defender, simplificar...).
- {instrucao_raciocinio}
- "roteiro": 3 a 5 passos, NA ORDEM em que o aluno deve avaliar esta posição. Cada passo tem "o_que_avaliar" (o que olhar, em uma frase, podendo citar peças e casas que JÁ existem no tabuleiro) e "por_que" (por que isso importa NESTA posição e por que vem nesta ordem, em 1 a 2 frases). O roteiro ensina a procurar, não entrega o que vai ser achado.
- "principio": 1 a 2 frases com a regra geral de pensamento que esta posição ensina e que vale em outras partidas.

REGRAS OBRIGATÓRIAS:
- É PROIBIDO escrever lances em notação (ex.: Nf3, exd5, O-O, Cf3, "lance e4").
- É PROIBIDO descrever lances em palavras ("leve o cavalo para f5", "avance o peão de h", "troque as damas", "sacrifique o bispo em h7"). Diga o que avaliar, nunca o que jogar.
- NÃO diga qual lance é o melhor, NÃO sugira candidatos e NÃO revele números de avaliação nem quem está melhor em porcentagem.
- Nunca invente peças ou casas.
- Escreva em português do Brasil, falando diretamente com o aluno ("você").
- Responda ESTRITAMENTE com um único JSON válido, sem texto antes ou depois e sem fences markdown.

{{
  "tipo_de_posicao": "string",
  "sobre_o_seu_raciocinio": "string ou null",
  "roteiro": [{{"o_que_avaliar": "string", "por_que": "string"}}],
  "principio": "string"
}}"""


def problemas_da_resposta(resposta: RespostaConsulta) -> list[str]:
    """O que a resposta fez de errado, em frases que servem de correção ao modelo.

    A resposta inteira não pode ter lance NENHUM — por isso a verificação usa um
    conjunto de permitidos vazio: qualquer lance escrito é problema, mesmo que
    legal. Lance descrito em palavras também conta.
    """

    problemas: list[str] = []
    texto = " ".join(
        [
            resposta.tipo_de_posicao,
            resposta.sobre_o_seu_raciocinio or "",
            *(f"{passo.o_que_avaliar} {passo.por_que}" for passo in resposta.roteiro),
            resposta.principio,
        ]
    )
    lances = detectar_lances_inventados(texto, set())
    # O detector herdado do explicador só conhece a notação inglesa. Em
    # português "Cf3" e "Dxd5" passariam direto.
    for achado in PADRAO_LANCE_PT.findall(texto):
        if achado not in lances:
            lances.append(achado)
    if lances:
        problemas.append("A resposta citou lances, o que é proibido: " + ", ".join(lances))

    por_extenso = [achado.group(0) for achado in PADRAO_LANCE_POR_EXTENSO.finditer(texto)]
    if por_extenso:
        problemas.append(
            "A resposta descreveu lances em palavras, o que é proibido: "
            + "; ".join(f'"{trecho}"' for trecho in por_extenso)
        )

    if not resposta.tipo_de_posicao.strip():
        problemas.append("'tipo_de_posicao' veio vazio")
    if len(resposta.roteiro) < 3:
        problemas.append("'roteiro' precisa de pelo menos 3 passos")
    if not resposta.principio.strip():
        problemas.append("'principio' veio vazio")
    return problemas


def resposta_deterministica(elementos: dict[str, Any], cor_jogador: str) -> RespostaConsulta:
    """Resposta sem Gemini, quando ele falha ou insiste em violar as regras.

    É modesta de propósito: só afirma o que o tabuleiro prova, e o roteiro é o
    método geral (ameaças, peças soltas, lances forçantes, reis, pior peça)
    ordenado pelo que esta posição tem de concreto. Nunca cita a lista de
    xeques e capturas do inspetor: ela é feita de lances.
    """

    adversaria = "PRETAS" if cor_jogador == "BRANCAS" else "BRANCAS"
    soltas = elementos["pecas_indefesas"][cor_jogador]
    alvos = elementos["pecas_indefesas"][adversaria]
    ameacas = elementos.get("ameacas_imediatas") or {}
    ha_forcantes = bool(ameacas.get("cheques") or ameacas.get("capturas"))
    tatica = bool(soltas or alvos)

    tipo = [elementos["material"]["descricao"] + "."]
    if tatica:
        tipo.append(
            "Há peças sem defesa suficiente no tabuleiro, então a posição é tática: "
            "antes de qualquer plano, ela pede cálculo."
        )
    else:
        tipo.append(
            "Nenhuma peça está solta, então a posição tende a ser de manobra: "
            "o que decide é melhorar peças e escolher um plano."
        )

    roteiro = [
        PassoDoRoteiro(
            o_que_avaliar="O que o último lance do adversário mudou: o que ele passou a atacar e que casa deixou de defender.",
            por_que="A maioria dos erros de quem está em dúvida vem de não ver a ameaça; nenhum plano vale se a posição não estiver segura.",
        )
    ]
    if soltas:
        roteiro.append(
            PassoDoRoteiro(
                o_que_avaliar="Suas peças sem defesa suficiente: " + "; ".join(soltas) + ".",
                por_que="Peça solta é o primeiro alvo de qualquer tática do adversário, e resolver isso vem antes de atacar.",
            )
        )
    if alvos or ha_forcantes:
        roteiro.append(
            PassoDoRoteiro(
                o_que_avaliar="Seus xeques, capturas e ameaças"
                + (": do outro lado há alvos (" + "; ".join(alvos) + ")." if alvos else "."),
                por_que="Lances forçantes vêm antes dos calmos porque limitam as respostas do adversário, e por isso dá para calculá-los até o fim.",
            )
        )
    rei = elementos["seguranca_rei"].get(cor_jogador, {}).get("resumo")
    rei_adversario = elementos["seguranca_rei"].get(adversaria, {}).get("resumo")
    resumos_reis = "; ".join(texto for texto in (rei, rei_adversario) if texto)
    roteiro.append(
        PassoDoRoteiro(
            o_que_avaliar="A segurança dos dois reis" + (f": {resumos_reis}." if resumos_reis else "."),
            por_que="É ela que diz se é hora de atacar ou de consolidar antes.",
        )
    )
    roteiro.append(
        PassoDoRoteiro(
            o_que_avaliar="Qual é a sua peça menos ativa, e onde ela trabalharia melhor.",
            por_que="Quando nada forçante funciona, melhorar a pior peça é o plano que quase nunca piora a posição.",
        )
    )

    principio = (
        "Em posição com peças soltas, a ordem é segurança, depois lances forçantes, e só então planos."
        if tatica
        else "Em posição sem nada forçante, não procure um lance brilhante: procure a peça que está pior e dê a ela uma função."
    )
    return RespostaConsulta(
        tipo_de_posicao=" ".join(tipo),
        sobre_o_seu_raciocinio=None,
        roteiro=roteiro,
        principio=principio,
    )


def gerar_resposta(
    client: Any,
    prompt: str,
    elementos: dict[str, Any],
    cor_jogador: str,
    logger: logging.Logger,
) -> tuple[RespostaConsulta, str]:
    """Uma chamada ao Gemini, no máximo uma correção, e o fallback se preciso.

    Devolve a resposta e a origem ("gemini" ou "fallback"). Uma só correção de
    propósito: o usuário está com o relógio correndo e pediu economia de cota.
    """

    if client is None:
        return resposta_deterministica(elementos, cor_jogador), "fallback"

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
            problemas = problemas_da_resposta(resposta)
            if not problemas:
                return resposta, "gemini"

        logger.warning("Consulta ao vivo: resposta rejeitada (tentativa %d): %s", tentativa + 1, problemas)
        tentativa_prompt = (
            f"{prompt}\n\nA resposta anterior foi rejeitada por estes motivos:\n- "
            + "\n- ".join(problemas)
            + "\nCorrija e responda apenas com o JSON válido."
        )

    return resposta_deterministica(elementos, cor_jogador), "fallback"


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

    `como_pensar` é o que o jogador vê. `motor` é interno: vai para o banco
    (o desfecho do D-68 compara o lance jogado com ele) e o servidor não o
    devolve.

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
    linhas = _linhas_do_motor(analise["linhas_taticas"])

    prompt = build_prompt_consulta(
        board, cor, lances_san, analise, elementos, pensamento_limpo, adversario
    )
    resposta, origem = gerar_resposta(gemini_client, prompt, elementos, cor, logger)

    return {
        "fen": board.fen(),
        "fen_inicial": fen_inicial or chess.STARTING_FEN,
        "lances_san": lances_san,
        "numero_lance": board.fullmove_number,
        "cor_jogador": cor,
        "pensamento": pensamento_limpo,
        "como_pensar": resposta.model_dump(),
        "motor": {
            "candidatos": [linha["lance"] for linha in linhas],
            "melhor_lance": linhas[0]["lance"] if linhas else None,
            "avaliacao": analise["descricao"],
            "win_percent_jogador": round(win_percent_do_jogador(analise, cor), 1),
            "linhas": linhas,
        },
        "gerado_por": origem,
    }
