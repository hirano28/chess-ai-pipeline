"""Módulo analítico e explicador didático de posições de xadrez.

Recebe uma posição (FEN ou PGN) e opcionalmente o lado/jogador. Combina:
1. Avaliação objetiva do Stockfish (centipawns/mate, Win%, melhores linhas PV e
   refutação da melhor defesa).
2. Inspeção posicional via python-chess (desequilíbrio de material, peças
   indefesas/atacadas, peças cravadas, segurança do rei e ameaças imediatas).
3. Modelo Gemini com prompt estruturado e validação anti-alucinação para
   produzir uma explicação humana, didática e conceitual em 4 seções:
   - Veredito claro
   - Ameaça concreta
   - O que parece bom mas falha (refutação da defesa)
   - Plano de conversão
   - Resumo didático sintetizado.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

import chess
import chess.pgn
from pydantic import BaseModel, Field, ValidationError

from backend.agentes.revisar_exercicio_avulso import (
    _acquire_engine_lock,
    resolver_posicao,
)
from backend.agentes.revisar_pensamento import (
    Settings,
    _formatar_avaliacao,
    call_gemini,
    strip_json_fences,
)
from backend.analise_engine.analisar_partidas import (
    STOCKFISH_SEARCHTIME_MS,
    evaluation_to_cp,
)
from backend.common.chess_math import centipawns_para_win_percent
from backend.common.tenant import obter_default_user_id

NOME_PECA_PT: dict[chess.PieceType, str] = {
    chess.PAWN: "Peão",
    chess.KNIGHT: "Cavalo",
    chess.BISHOP: "Bispo",
    chess.ROOK: "Torre",
    chess.QUEEN: "Dama",
    chess.KING: "Rei",
}

VALOR_PECA: dict[chess.PieceType, int] = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}


class ExplicacaoPosicao(BaseModel):
    """Schema estruturado da explicação didática gerada pelo agente."""

    veredito: str = Field(
        description="Veredito claro: quem está ganhando e a magnitude da vantagem."
    )
    ameaca_concreta: str = Field(
        description="Ameaça concreta mais perigosa que torna a defesa insustentável."
    )
    o_que_parece_bom_mas_falha: str = Field(
        description="Defesas que parecem intuitivas para o lado perdedor mas falham, com refutação."
    )
    plano_conversao: str = Field(
        description="O plano didático para converter a posição em vitória."
    )
    resumo_didatico: str = Field(
        description="Síntese didática e conceitual em 2 a 3 frases memoráveis."
    )


def normalizar_lado(lado: str | None) -> str | None:
    """Normaliza o lado do jogador informado pelo usuário.

    Retorna "BRANCAS", "PRETAS", ou None se não informado/vazio/automático.
    Lança ValueError se for uma string inválida.
    """
    if lado is None:
        return None
    limpo = lado.strip().upper()
    if not limpo:
        return None
    if limpo in {"TODOS", "AMBOS", "AUTO", "AUTOMATICO", "AUTOMÁTICO", "ALL"}:
        return None
    if limpo in {"BRANCAS", "BRANCA", "WHITE", "W"}:
        return "BRANCAS"
    if limpo in {"PRETAS", "PRETA", "BLACK", "NEGRAS", "NEGRA", "P"}:
        return "PRETAS"
    raise ValueError(f"Lado inválido: '{lado}'. Escolha 'BRANCAS' ou 'PRETAS'.")


def inspecionar_elementos_tabuleiro(board: chess.Board) -> dict[str, Any]:
    """Inspeciona o tabuleiro usando python-chess para extrair a realidade posicional objetiva.

    Retorna:
    - material: contagens, saldo e par de bispos
    - pecas_indefesas: peças sem defesa ou sub-defendidas
    - pecas_cravadas: peças cravadas ao rei
    - seguranca_rei: xeque, casas atacadas ao redor do rei, roque
    - ameacas_imediatas: cheques e capturas legais disponíveis para o lado a jogar
    """
    # 1. Material
    pontos_brancas = sum(
        len(board.pieces(pt, chess.WHITE)) * val for pt, val in VALOR_PECA.items()
    )
    pontos_pretas = sum(
        len(board.pieces(pt, chess.BLACK)) * val for pt, val in VALOR_PECA.items()
    )
    saldo_brancas = pontos_brancas - pontos_pretas
    par_bispos_brancas = len(board.pieces(chess.BISHOP, chess.WHITE)) >= 2
    par_bispos_pretas = len(board.pieces(chess.BISHOP, chess.BLACK)) >= 2

    if saldo_brancas > 0:
        desc_material = (
            f"Brancas têm vantagem de material (+{saldo_brancas} pontos: "
            f"{pontos_brancas} vs {pontos_pretas})"
        )
    elif saldo_brancas < 0:
        desc_material = (
            f"Pretas têm vantagem de material (+{abs(saldo_brancas)} pontos: "
            f"{pontos_pretas} vs {pontos_brancas})"
        )
    else:
        desc_material = f"Material rigorosamente igual ({pontos_brancas} pontos para cada lado)"

    material_info = {
        "pontos_brancas": pontos_brancas,
        "pontos_pretas": pontos_pretas,
        "saldo_brancas": saldo_brancas,
        "descricao": desc_material,
        "par_bispos_brancas": par_bispos_brancas,
        "par_bispos_pretas": par_bispos_pretas,
    }

    # 2. Peças indefesas e cravadas
    pecas_indefesas: dict[str, list[str]] = {"BRANCAS": [], "PRETAS": []}
    pecas_cravadas: dict[str, list[str]] = {"BRANCAS": [], "PRETAS": []}

    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None or piece.piece_type == chess.KING:
            continue

        cor = piece.color
        cor_str = "BRANCAS" if cor == chess.WHITE else "PRETAS"
        sq_name = chess.square_name(sq)
        nome_peca = NOME_PECA_PT[piece.piece_type]

        # Cravadas ao rei
        if board.is_pinned(cor, sq):
            king_sq = board.king(cor)
            king_name = chess.square_name(king_sq) if king_sq is not None else "?"
            pecas_cravadas[cor_str].append(
                f"{nome_peca} em {sq_name} cravado ao Rei em {king_name}"
            )

        # Defensores vs atacantes
        defensores = board.attackers(cor, sq)
        atacantes = board.attackers(not cor, sq)
        qtd_def = len(defensores)
        qtd_atk = len(atacantes)

        if qtd_def == 0 and qtd_atk > 0:
            pecas_indefesas[cor_str].append(
                f"{nome_peca} em {sq_name} (indefeso e atacado por {qtd_atk} peça(s))"
            )
        elif qtd_atk > qtd_def:
            pecas_indefesas[cor_str].append(
                f"{nome_peca} em {sq_name} (sub-defendido: {qtd_atk} atacante(s) vs {qtd_def} defensor(es))"
            )
        elif qtd_def == 0 and qtd_atk == 0 and piece.piece_type != chess.PAWN:
            # Peça solta (LPDO - apenas peças menores e maiores)
            pecas_indefesas[cor_str].append(f"{nome_peca} em {sq_name} (sem defensores)")

    # 3. Segurança do rei
    seguranca_rei: dict[str, Any] = {}
    for cor, cor_str in ((chess.WHITE, "BRANCAS"), (chess.BLACK, "PRETAS")):
        king_sq = board.king(cor)
        if king_sq is None:
            continue
        king_name = chess.square_name(king_sq)
        em_xeque = board.is_check() if board.turn == cor else False
        surrounding = board.attacks(king_sq)
        opponent = not cor
        casas_atacadas = [
            chess.square_name(s)
            for s in surrounding
            if board.is_attacked_by(opponent, s)
        ]
        roque = board.has_kingside_castling_rights(
            cor
        ) or board.has_queenside_castling_rights(cor)

        if em_xeque:
            resumo = f"Rei em {king_name} sob xeque!"
        elif len(casas_atacadas) >= 3:
            resumo = f"Rei em {king_name} muito exposto ({len(casas_atacadas)} casas ao redor atacadas)"
        elif not roque and king_name in ("e1", "e8", "d1", "d8"):
            resumo = f"Rei em {king_name} no centro sem roque"
        else:
            resumo = f"Rei em {king_name} com segurança razoável"

        seguranca_rei[cor_str] = {
            "casa": king_name,
            "em_xeque": em_xeque,
            "casas_vizinhas_atacadas": len(casas_atacadas),
            "roque_disponivel": roque,
            "resumo": resumo,
        }

    # 4. Ameaças imediatas para o lado que está a jogar
    cheques = [board.san(m) for m in board.legal_moves if board.gives_check(m)]
    capturas = [board.san(m) for m in board.legal_moves if board.is_capture(m)]

    return {
        "material": material_info,
        "pecas_indefesas": pecas_indefesas,
        "pecas_cravadas": pecas_cravadas,
        "seguranca_rei": seguranca_rei,
        "ameacas_imediatas": {
            "cheques": cheques,
            "capturas": capturas,
        },
    }


def analisar_posicao_com_engine(
    engine: Any,
    board: chess.Board,
    searchtime_ms: int = STOCKFISH_SEARCHTIME_MS,
    engine_lock: threading.Lock | None = None,
) -> dict[str, Any]:
    """Consulta Stockfish de forma concorrente-segura para avaliação e linhas táticas."""
    # 1. Trata posições já terminais no tabuleiro sem consultar o motor
    if board.is_checkmate():
        vencedor = "PRETAS" if board.turn == chess.WHITE else "BRANCAS"
        score_cp = -10000 if vencedor == "PRETAS" else 10000
        desc = f"Xeque-mate! As {'Brancas' if vencedor == 'BRANCAS' else 'Pretas'} venceram a partida."
        return {
            "score_cp": score_cp,
            "mate": 0,
            "win_percent": 100.0,
            "win_percent_brancas": 100.0 if vencedor == "BRANCAS" else 0.0,
            "win_percent_pretas": 100.0 if vencedor == "PRETAS" else 0.0,
            "lado_vencedor": vencedor,
            "descricao": desc,
            "linhas_taticas": [],
            "refutacao_defesa": {
                "defesa": "Sem defesa viável",
                "refutacao_linha": [],
                "detalhes": f"A posição é xeque-mate. As {vencedor.lower()} já venceram.",
            },
        }

    if board.is_stalemate():
        return {
            "score_cp": 0,
            "mate": None,
            "win_percent": 50.0,
            "win_percent_brancas": 50.0,
            "win_percent_pretas": 50.0,
            "lado_vencedor": "EQUILIBRADO",
            "descricao": "Empate por afogamento (stalemate).",
            "linhas_taticas": [],
            "refutacao_defesa": None,
        }

    with _acquire_engine_lock(engine_lock):
        engine.set_fen_position(board.fen())
        try:
            eval_dict = engine.get_evaluation(searchtime=searchtime_ms)
        except TypeError:
            eval_dict = engine.get_evaluation()

        try:
            top_moves_raw = engine.get_top_moves(3, verbose=True)
        except TypeError:
            top_moves_raw = engine.get_top_moves(3)
        except Exception:
            top_moves_raw = []

    score_cp = evaluation_to_cp(eval_dict)
    mate_val: int | None = (
        int(eval_dict["value"]) if eval_dict.get("type") == "mate" else None
    )

    if mate_val is not None:
        if mate_val > 0:
            lado_vencedor = "BRANCAS"
            win_percent = 100.0
            win_percent_brancas = 100.0
            win_percent_pretas = 0.0
        elif mate_val < 0:
            lado_vencedor = "PRETAS"
            win_percent = 100.0
            win_percent_brancas = 0.0
            win_percent_pretas = 100.0
        else:
            lado_vencedor = "BRANCAS" if board.turn == chess.BLACK else "PRETAS"
            win_percent = 100.0
            win_percent_brancas = 100.0 if lado_vencedor == "BRANCAS" else 0.0
            win_percent_pretas = 100.0 if lado_vencedor == "PRETAS" else 0.0

        if mate_val == 0:
            descricao = f"Xeque-mate! As {'Brancas' if lado_vencedor == 'BRANCAS' else 'Pretas'} venceram a partida."
        else:
            m_int = mate_val
            descricao = (
                f"Mate forçado em {abs(m_int)} lance(s) para as "
                f"{'Brancas' if m_int > 0 else 'Pretas'}"
            )
    else:
        win_percent_brancas = round(centipawns_para_win_percent(score_cp), 2)
        win_percent_pretas = round(100.0 - win_percent_brancas, 2)
        if score_cp >= 120:
            lado_vencedor = "BRANCAS"
            win_percent = win_percent_brancas
        elif score_cp <= -120:
            lado_vencedor = "PRETAS"
            win_percent = win_percent_pretas
        else:
            lado_vencedor = "EQUILIBRADO"
            win_percent = 50.0

        cp_abs = abs(score_cp)
        sinal = "+" if score_cp > 0 else ("-" if score_cp < 0 else "=")
        if cp_abs >= 400:
            grau = "vantagem decisiva"
        elif cp_abs >= 200:
            grau = "vantagem substancial"
        elif cp_abs >= 100:
            grau = "vantagem clara"
        else:
            grau = "posição equilibrada"
        quem = "Brancas" if score_cp > 0 else ("Pretas" if score_cp < 0 else "ambos")
        descricao = f"{sinal}{cp_abs / 100:.2f} centipawns ({grau} para {quem})"

    # Converte PVs para SAN
    linhas_taticas: list[dict[str, Any]] = []
    perspectiva_brancas = board.turn == chess.WHITE

    for item in top_moves_raw:
        pv_raw = item.get("PVMoves") or item.get("Move") or ""
        if isinstance(pv_raw, list):
            pv_uci_list = [str(x) for x in pv_raw]
        elif isinstance(pv_raw, str):
            pv_uci_list = pv_raw.split()
        else:
            pv_uci_list = []

        if not pv_uci_list and item.get("Move"):
            pv_uci_list = [str(item["Move"])]

        pv_san: list[str] = []
        scratch = board.copy()
        for uci_str in pv_uci_list:
            try:
                m = chess.Move.from_uci(uci_str)
                if not scratch.is_legal(m):
                    break
                pv_san.append(scratch.san(m))
                scratch.push(m)
            except (ValueError, AssertionError):
                break

        lance_primeiro = pv_san[0] if pv_san else (item.get("Move") or "")
        avaliacao_fmt = _formatar_avaliacao(
            item.get("Centipawn"), item.get("Mate"), perspectiva_brancas
        )
        linhas_taticas.append(
            {
                "lance": lance_primeiro,
                "avaliacao": avaliacao_fmt,
                "pv_san": pv_san,
            }
        )

    # Identifica a melhor defesa do lado perdedor e a respectiva refutação
    refutacao_defesa: dict[str, Any] | None = None
    if linhas_taticas and lado_vencedor != "EQUILIBRADO":
        melhor_pv = linhas_taticas[0]["pv_san"]
        lado_a_jogar = "BRANCAS" if board.turn == chess.WHITE else "PRETAS"

        if melhor_pv:
            if lado_a_jogar == lado_vencedor:
                if len(melhor_pv) >= 2:
                    lance_vencedor = melhor_pv[0]
                    defesa = melhor_pv[1]
                    refutacao = melhor_pv[2:]
                    refut_str = (
                        " ".join(refutacao[:3]) if refutacao else "vantagem consolidada"
                    )
                    detalhes = (
                        f"Após o lance vencedor {lance_vencedor}, a melhor defesa adversária é {defesa}. "
                        f"No entanto, ela é refutada pela sequência direta {refut_str}."
                    )
                    refutacao_defesa = {
                        "defesa": defesa,
                        "refutacao_linha": melhor_pv[:5],
                        "detalhes": detalhes,
                    }
                elif len(melhor_pv) == 1:
                    refutacao_defesa = {
                        "defesa": "Sem defesa viável",
                        "refutacao_linha": melhor_pv,
                        "detalhes": f"O lance {melhor_pv[0]} arremata a posição imediatamente.",
                    }
            else:
                defesa = melhor_pv[0]
                refutacao = melhor_pv[1:] if len(melhor_pv) > 1 else []
                refut_str = (
                    " ".join(refutacao[:3]) if refutacao else "vantagem vencedora"
                )
                detalhes = (
                    f"A defesa mais resistente é {defesa}. "
                    f"Ainda assim, o adversário refuta com {refut_str}, convertendo a vitória."
                )
                refutacao_defesa = {
                    "defesa": defesa,
                    "refutacao_linha": melhor_pv[:5],
                    "detalhes": detalhes,
                }

    return {
        "score_cp": score_cp,
        "mate": mate_val,
        "win_percent": win_percent,
        "win_percent_brancas": win_percent_brancas,
        "win_percent_pretas": win_percent_pretas,
        "lado_vencedor": lado_vencedor,
        "descricao": descricao,
        "linhas_taticas": linhas_taticas,
        "refutacao_defesa": refutacao_defesa,
    }


def build_prompt_explicador(
    fen: str,
    lado_a_jogar: str,
    lado_analisado: str,
    avaliacao: dict[str, Any],
    linhas_taticas: list[dict[str, Any]],
    refutacao_defesa: dict[str, Any] | None,
    elementos: dict[str, Any],
) -> str:
    """Monta o prompt para o Gemini gerar a explicação humana da posição."""
    linhas_str = ""
    for idx, l in enumerate(linhas_taticas, 1):
        seq = " ".join(l["pv_san"]) if l["pv_san"] else l["lance"]
        linhas_str += f"  Linha {idx}: {l['lance']} ({l['avaliacao']}) -> Sequência: {seq}\n"

    refut_str = (
        f"Melhor defesa: {refutacao_defesa['defesa']}\n"
        f"Linha de refutação: {' '.join(refutacao_defesa['refutacao_linha'])}\n"
        f"Explicação da refutação: {refutacao_defesa['detalhes']}"
        if refutacao_defesa
        else "Posição equilibrada ou sem refutação tática direta."
    )

    mat = elementos["material"]
    indef_b = ", ".join(elementos["pecas_indefesas"]["BRANCAS"]) or "Nenhuma"
    indef_p = ", ".join(elementos["pecas_indefesas"]["PRETAS"]) or "Nenhuma"
    crav_b = ", ".join(elementos["pecas_cravadas"]["BRANCAS"]) or "Nenhuma"
    crav_p = ", ".join(elementos["pecas_cravadas"]["PRETAS"]) or "Nenhuma"
    rei_b = elementos["seguranca_rei"].get("BRANCAS", {}).get("resumo", "Normal")
    rei_p = elementos["seguranca_rei"].get("PRETAS", {}).get("resumo", "Normal")
    cheques = ", ".join(elementos["ameacas_imediatas"]["cheques"]) or "Nenhum"
    capturas = ", ".join(elementos["ameacas_imediatas"]["capturas"]) or "Nenhuma"

    if avaliacao.get("lado_vencedor") == "EQUILIBRADO":
        missao = (
            "Sua missão é explicar de forma didática, humana, conceitual e precisa "
            "por que essa posição está equilibrada (nenhum dos lados possui vantagem decisiva), "
            "quais são os recursos defensivos e ofensivos em jogo e como conduzir a posição."
        )
        estrutura = f"""ESTRUTURA DA RESPOSTA (Obrigatório preencher todas as 5 seções):
1. "veredito": Veredito claro e direto em 2 a 3 frases explicando o equilíbrio dinâmico ou estático ({avaliacao['descricao']}).
2. "ameaca_concreta": A ideia, tensão ou plano principal a considerar para o lado a jogar.
3. "o_que_parece_bom_mas_falha": Erros conceituais ou lances tentadores que desequilibrariam a posição se jogados de forma descuidada.
4. "plano_conversao": O plano estratégico correto para manter a igualdade, coordenar as peças e disputar o controle central.
5. "resumo_didatico": Uma síntese didática memorável em 2 a 3 frases sobre o conceito-chave do equilíbrio nesta posição."""
    else:
        missao = (
            f"Sua missão é explicar de forma didática, humana, conceitual e precisa o porquê "
            f"essa posição é vencida para as {avaliacao['lado_vencedor']}."
        )
        estrutura = f"""ESTRUTURA DA RESPOSTA (Obrigatório preencher todas as 5 seções):
1. "veredito": O veredito claro e direto em 2 a 3 frases. Deixe explícito quem está ganho e a gravidade (se é mate inevitável, ganho decisivo de material ou ataque fulminante de mate), contextualizando a avaliação ({avaliacao['descricao']}).
2. "ameaca_concreta": A ameaça concreta e imediata mais perigosa que torna a posição insustentável. O que o lado vencedor está ameaçando a seguir e por que isso não pode ser impedido.
3. "o_que_parece_bom_mas_falha": O que parece bom mas falha para o lado perdedor. Explique por que defesas intuitivas ou lances que o jogador perdedor poderia tentar não funcionam, citando a refutação concreta demonstrada pelo motor.
4. "plano_conversao": O plano de conversão em vitória. Explique em linguagem conceitual como o lado vencedor deve conduzir a posição (ex: simplificação favorável para o final, abertura de linhas contra o rei, peão passado, etc.).
5. "resumo_didatico": Uma síntese didática e memorável em 2 a 3 frases que fixe o conceito-chave da posição na mente do aluno."""

    return f"""Você é um Grande Mestre e treinador de elite de xadrez.
Um jogador estava revisando sua partida e não entendeu por que a engine indica que essa posição é vencedora/perdida ou de equilíbrio.
{missao}

DADOS OBJETIVOS DA POSIÇÃO:
- FEN: {fen}
- Vez de jogar: {lado_a_jogar}
- Lado analisado/perspectiva: {lado_analisado}
- Avaliação objetiva da Engine: {avaliacao['descricao']}
- Win%: {avaliacao['win_percent']:.1f}%
- Lado vencedor: {avaliacao['lado_vencedor']}

MELHORES LINHAS TÁTICAS DO MOTOR (Stockfish):
{linhas_str}

REFUTAÇÃO DA DEFESA:
{refut_str}

ELEMENTOS POSICIONAIS E TÁTICOS IMEDIATOS:
- Material: {mat['descricao']} (Par de bispos Brancas: {mat['par_bispos_brancas']}, Pretas: {mat['par_bispos_pretas']})
- Peças indefesas / atacadas Brancas: {indef_b}
- Peças indefesas / atacadas Pretas: {indef_p}
- Peças cravadas Brancas: {crav_b}
- Peças cravadas Pretas: {crav_p}
- Segurança do Rei Branco: {rei_b}
- Segurança do Rei Preto: {rei_p}
- Lances forçados imediatos ({lado_a_jogar}): Cheques: {cheques} | Capturas: {capturas}

{estrutura}

REGRAS ANTI-ALUCINAÇÃO OBRIGATÓRIAS:
- NUNCA invente lances. Cite EXCLUSIVAMENTE lances que constam nas linhas táticas fornecidas acima ou lances legais reais da posição.
- NÃO invente peças ou casas inexistentes.
- Responda ESTRITAMENTE com um único JSON válido, sem texto antes ou depois e sem fences markdown (```json).

{{
  "veredito": "string",
  "ameaca_concreta": "string",
  "o_que_parece_bom_mas_falha": "string",
  "plano_conversao": "string",
  "resumo_didatico": "string"
}}"""


def fallback_explicacao_posicao(
    board: chess.Board,
    lado_analisado: str,
    avaliacao: dict[str, Any],
    linhas_taticas: list[dict[str, Any]],
    refutacao_defesa: dict[str, Any] | None,
    elementos: dict[str, Any],
) -> ExplicacaoPosicao:
    """Gera uma explicação didática determinística caso o Gemini esteja indisponível."""
    vencedor = avaliacao["lado_vencedor"]
    vencedor_nome = (
        "Brancas"
        if vencedor == "BRANCAS"
        else ("Pretas" if vencedor == "PRETAS" else vencedor)
    )
    melhor_lance = linhas_taticas[0]["lance"] if linhas_taticas else None
    mat_desc = elementos["material"]["descricao"]

    if board.is_checkmate():
        veredito = (
            f"A partida terminou em xeque-mate: as {vencedor_nome} venceram a partida."
        )
        ameaca = "A posição é terminal; o rei adversário está em xeque-mate sem lances legais para escapar."
        defesa_falha = "Não há defesas viáveis ou lances legais disponíveis para o lado derrotado."
        plano = f"A partida já está concluída com vitória decisiva das {vencedor_nome}."
        resumo = f"Vitória consumada das {vencedor_nome} por xeque-mate no tabuleiro."
    elif board.is_stalemate():
        veredito = "A partida terminou empatada por afogamento (stalemate)."
        ameaca = "A posição é terminal; nenhum lance legal pode ser feito e o rei não está em xeque."
        defesa_falha = "Não há lances válidos disponíveis na posição final de afogamento."
        plano = "A partida está encerrada em empate pelas regras oficiais do xadrez."
        resumo = "Empate confirmado por afogamento (stalemate)."
    elif vencedor == "EQUILIBRADO":
        lance_txt = melhor_lance if melhor_lance else "a melhor jogada posicional"
        veredito = (
            f"A posição está equilibrada segundo o motor ({avaliacao['descricao']}). "
            "Nenhum dos lados possui vantagem decisiva no momento."
        )
        ameaca = f"O lance principal recomendado é {lance_txt}, mantendo a solidez da posição."
        defesa_falha = "Não há refutação tática imediata, pois a posição permanece sólida para ambos os lados."
        plano = "O plano ideal consiste em desenvolver peças ativas, coordenar torres e manter o controle do centro."
        resumo = "Posição equilibrada com chances iguais para ambos os lados; a precisão posicional ditará o resultado."
    else:
        lance_txt = melhor_lance if melhor_lance else "a iniciativa das peças ativas"
        veredito = (
            f"As {vencedor_nome} possuem uma vantagem expressiva ({avaliacao['descricao']}), "
            f"com {avaliacao['win_percent']:.1f}% de probabilidade de vitória calculada pela engine."
        )
        ameaca = (
            f"A ameaça mais direta parte de {lance_txt}, explorando as vulnerabilidades táticas "
            f"e impondo pressão decisiva."
        )
        if refutacao_defesa:
            defesa_falha = refutacao_defesa["detalhes"]
        else:
            defesa_falha = "As tentativas defensivas do adversário são neutralizadas pelo cálculo preciso das linhas principais."

        plano = (
            f"O plano de conversão apoia-se no equilíbrio posicional ({mat_desc}): "
            "manter a pressão, simplificar nas horas corretas e explorar as debilidades do oponente."
        )
        resumo = (
            f"Vantagem clara para as {vencedor_nome}. A combinação de melhor atividade e fraquezas adversárias "
            "garante o caminho para a conversão."
        )

    return ExplicacaoPosicao(
        veredito=veredito,
        ameaca_concreta=ameaca,
        o_que_parece_bom_mas_falha=defesa_falha,
        plano_conversao=plano,
        resumo_didatico=resumo,
    )


PADRAO_LANCE_EXPLICITO = re.compile(
    r"\b(?:(?:O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8]=[QRBN])[+#]?|[a-h][1-8][+#])(?!\w)"
)
PADRAO_LANCE_PEAO_PREFIXADO = re.compile(
    r"(?:\b(?:lance|jogar|joga|jogada|resposta|mover|movimento)\s+)([a-h][1-8])\b",
    re.IGNORECASE,
)


def obter_lances_permitidos(
    board: chess.Board, linhas_taticas: list[dict[str, Any]]
) -> set[str]:
    """Coleta o conjunto de lances SAN válidos (legais na posição e nas linhas PV)."""
    permitidos: set[str] = {board.san(m) for m in board.legal_moves}
    for item in linhas_taticas:
        scratch = board.copy()
        for san_move in item.get("pv_san", []):
            permitidos.add(san_move)
            try:
                m = scratch.parse_san(san_move)
                scratch.push(m)
                for next_m in scratch.legal_moves:
                    permitidos.add(scratch.san(next_m))
            except Exception:
                break
    # Inclui versões limpas sem marcadores de xeque/mate (+ e #)
    norm = set(permitidos)
    for p in permitidos:
        norm.add(p.rstrip("+#"))
    return norm


def detectar_lances_inventados(
    texto: str, permitidos: set[str]
) -> list[str]:
    """Identifica lances SAN citados no texto que não existem entre os permitidos.

    Diferencia com precisão:
    1. Lances explícitos (com peça, captura, promoção, roque ou xeque/mate).
    2. Lances de peão bare (ex: "lance a4") que não constam nas opções permitidas.
    3. Referências puramente posicionais/casas (ex: "rei em g8", "casa f7",
       "par de bispos em c4 e e3"), que NÃO são tratadas falsamente como lances.
    """
    permitidos_norm = {p.rstrip("+#") for p in permitidos} | set(permitidos)
    inventados: list[str] = []

    # 1. Lances com sintaxe inequívoca de lance de xadrez
    for match in PADRAO_LANCE_EXPLICITO.finditer(texto):
        lance = match.group(0)
        lance_limpo = lance.rstrip("+#")
        if lance not in permitidos_norm and lance_limpo not in permitidos_norm:
            if lance not in inventados:
                inventados.append(lance)

    # 2. Lances de peão explícitos ("lance d4", "jogada e5")
    for match in PADRAO_LANCE_PEAO_PREFIXADO.finditer(texto):
        sq = match.group(1)
        if sq not in permitidos_norm:
            if sq not in inventados:
                inventados.append(sq)

    return inventados


def gerar_explicacao_gemini(
    client: Any,
    board: chess.Board,
    lado_a_jogar: str,
    lado_analisado: str,
    avaliacao: dict[str, Any],
    linhas_taticas: list[dict[str, Any]],
    refutacao_defesa: dict[str, Any] | None,
    elementos: dict[str, Any],
    logger: logging.Logger,
) -> ExplicacaoPosicao:
    if board.is_checkmate() or board.is_stalemate():
        return fallback_explicacao_posicao(
            board,
            lado_analisado,
            avaliacao,
            linhas_taticas,
            refutacao_defesa,
            elementos,
        )

    prompt = build_prompt_explicador(
        board.fen(),
        lado_a_jogar,
        lado_analisado,
        avaliacao,
        linhas_taticas,
        refutacao_defesa,
        elementos,
    )

    if client is None:
        logger.warning("Cliente Gemini não fornecido; usando fallback determinístico.")
        return fallback_explicacao_posicao(
            board,
            lado_analisado,
            avaliacao,
            linhas_taticas,
            refutacao_defesa,
            elementos,
        )

    try:
        raw_response = call_gemini(client, prompt, logger)
    except Exception as error:
        logger.warning("Falha ao chamar Gemini (%s); usando fallback.", error)
        return fallback_explicacao_posicao(
            board,
            lado_analisado,
            avaliacao,
            linhas_taticas,
            refutacao_defesa,
            elementos,
        )

    # 1. Parse estruturado do JSON com Pydantic
    try:
        explicacao = ExplicacaoPosicao.model_validate_json(
            strip_json_fences(raw_response)
        )
    except ValidationError as error:
        logger.warning("JSON inválido do Gemini (%s); disparando retry de correção.", error)
        prompt_correcao = (
            f"{prompt}\n\nA resposta anterior falhou com erro de validação: {error}. "
            "Responda ESTRITAMENTE com o JSON válido corrigido."
        )
        try:
            raw_retry = call_gemini(client, prompt_correcao, logger)
            explicacao = ExplicacaoPosicao.model_validate_json(
                strip_json_fences(raw_retry)
            )
        except Exception as retry_err:
            logger.warning(
                "Retry do Gemini falhou (%s); usando fallback determinístico.",
                retry_err,
            )
            return fallback_explicacao_posicao(
                board,
                lado_analisado,
                avaliacao,
                linhas_taticas,
                refutacao_defesa,
                elementos,
            )

    # 2. Validação anti-alucinação de lances SAN citados
    permitidos = obter_lances_permitidos(board, linhas_taticas)
    texto_total = (
        f"{explicacao.veredito} {explicacao.ameaca_concreta} "
        f"{explicacao.o_que_parece_bom_mas_falha} {explicacao.plano_conversao}"
    )
    lances_inventados = detectar_lances_inventados(texto_total, permitidos)

    if lances_inventados:
        logger.warning(
            "Lances inventados detectados pelo filtro anti-alucinação: %s. Disparando correção.",
            lances_inventados,
        )
        prompt_anti_alucinacao = (
            f"{prompt}\n\n"
            f"ATENÇÃO: A resposta anterior citou lances inválidos/inventados que NÃO existem "
            f"na posição nem nas linhas do motor: {', '.join(lances_inventados)}. "
            "Reescreva a explicação citando EXCLUSIVAMENTE os lances reais fornecidos nas linhas táticas. "
            "Responda apenas com o JSON válido."
        )
        try:
            raw_anti = call_gemini(client, prompt_anti_alucinacao, logger)
            explicacao_corrigida = ExplicacaoPosicao.model_validate_json(
                strip_json_fences(raw_anti)
            )
            # Verifica novamente se ainda há lances inventados
            texto_corrigido = (
                f"{explicacao_corrigida.veredito} {explicacao_corrigida.ameaca_concreta} "
                f"{explicacao_corrigida.o_que_parece_bom_mas_falha} {explicacao_corrigida.plano_conversao}"
            )
            ainda_inventados = detectar_lances_inventados(texto_corrigido, permitidos)
            if not ainda_inventados:
                return explicacao_corrigida
            logger.warning(
                "Resposta após retry ainda continha lances inventados (%s); revertendo para fallback determinístico.",
                ainda_inventados,
            )
            return fallback_explicacao_posicao(
                board,
                lado_analisado,
                avaliacao,
                linhas_taticas,
                refutacao_defesa,
                elementos,
            )
        except Exception as retry_err:
            logger.warning(
                "Falha no retry anti-alucinação (%s); usando fallback.",
                retry_err,
            )
            return fallback_explicacao_posicao(
                board,
                lado_analisado,
                avaliacao,
                linhas_taticas,
                refutacao_defesa,
                elementos,
            )

    return explicacao


def explicar_posicao(
    engine: Any,
    gemini_client: Any,
    settings: Settings,
    logger: logging.Logger,
    posicao: str,
    lado: str | None = None,
    engine_lock: threading.Lock | None = None,
) -> dict[str, Any]:
    """Função principal: recebe posição (FEN ou PGN) e lado opcional, retornando a análise completa."""
    board = resolver_posicao(posicao)
    lado_norm = normalizar_lado(lado)
    lado_a_jogar = "BRANCAS" if board.turn == chess.WHITE else "PRETAS"
    lado_analisado = lado_norm if lado_norm is not None else lado_a_jogar

    # 1. Inspeção posicional via python-chess
    elementos = inspecionar_elementos_tabuleiro(board)

    # 2. Avaliação objetiva com Stockfish
    analise_engine = analisar_posicao_com_engine(
        engine,
        board,
        searchtime_ms=STOCKFISH_SEARCHTIME_MS,
        engine_lock=engine_lock,
    )

    # 3. Explicação didática gerada pelo Gemini com anti-alucinação
    explicacao = gerar_explicacao_gemini(
        gemini_client,
        board,
        lado_a_jogar,
        lado_analisado,
        analise_engine,
        analise_engine["linhas_taticas"],
        analise_engine["refutacao_defesa"],
        elementos,
        logger,
    )

    return {
        "fen": board.fen(),
        "lado_a_jogar": lado_a_jogar,
        "lado_analisado": lado_analisado,
        "avaliacao": {
            "score_cp": analise_engine["score_cp"],
            "mate": analise_engine["mate"],
            "win_percent": analise_engine["win_percent"],
            "lado_vencedor": analise_engine["lado_vencedor"],
            "descricao": analise_engine["descricao"],
        },
        "linhas_taticas": analise_engine["linhas_taticas"],
        "refutacao_defesa": analise_engine["refutacao_defesa"],
        "elementos_posicionais": elementos,
        "explicacao": explicacao.model_dump(),
    }


def salvar_explicacao_posicao(
    client: Any, resultado: dict[str, Any], user_id: str | None = None
) -> str | None:
    """Persiste o resultado completo de explicar_posicao() em explicacoes_posicao.

    Fecha a pendência P-10 (ESTADO.md): antes desta função, nenhuma explicação
    gerada era salva. 'resultado' é o dict inteiro devolvido por
    explicar_posicao() e é gravado por completo em jsonb - fen e lado_analisado
    também viram colunas próprias só para filtrar/exibir sem desempacotar o
    jsonb. Retorna o id da linha criada, ou None se a resposta não trouxer id.

    `user_id`: dono real da escrita (sessão Supabase Auth, Fase B.2 — D-17);
    `None` usa o `DEFAULT_USER_ID` de sempre.
    """

    resposta = (
        client.table("explicacoes_posicao")
        .insert(
            {
                "fen": resultado["fen"],
                "lado_analisado": resultado["lado_analisado"],
                "resultado": resultado,
                "user_id": user_id or obter_default_user_id(),
            }
        )
        .execute()
    )
    linhas = resposta.data or []
    return linhas[0]["id"] if linhas else None
