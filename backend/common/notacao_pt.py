"""Conversão entre notação algébrica em português e o SAN padrão (inglês).

O python-chess só entende as iniciais em inglês (N, R, Q, K, B). Aqui ficam as
duas traduções de letra de peça: PT -> EN (para conseguir dar parse no que o
usuário digitou) e EN -> PT (para devolver ao usuário o lance como ele escreve).

Só a inicial da peça e a letra de promoção mudam; casas, capturas, xeques,
desambiguações e roque passam intactos.
"""

from __future__ import annotations

# Bispo é 'B' nos dois idiomas; fica explícito no mapa para deixar claro que a
# letra foi considerada (e não esquecida).
PT_PARA_EN: dict[str, str] = {
    "C": "N",  # Cavalo -> kNight
    "T": "R",  # Torre -> Rook
    "D": "Q",  # Dama -> Queen
    "R": "K",  # Rei -> King
    "B": "B",  # Bispo -> Bishop
}

EN_PARA_PT: dict[str, str] = {
    "N": "C",
    "R": "T",
    "Q": "D",
    "K": "R",
    "B": "B",
}


def _traduzir(lance: str, mapa: dict[str, str]) -> str:
    """Traduz a inicial da peça e a letra de promoção usando o mapa informado."""

    texto = (lance or "").strip()
    if not texto:
        return texto

    # Só o PRIMEIRO caractere, e só se for maiúsculo do conjunto de peças:
    # lances de peão começam com letra de coluna minúscula (a-h) e não mudam,
    # assim como o roque (O-O / O-O-O), que começa com 'O'.
    if texto[0] in mapa:
        texto = mapa[texto[0]] + texto[1:]

    return _traduzir_promocao(texto, mapa)


def _traduzir_promocao(lance: str, mapa: dict[str, str]) -> str:
    """Traduz a letra logo após '=', quando houver (ex.: 'e8=D' -> 'e8=Q')."""

    indice = lance.find("=")
    if indice == -1 or indice + 1 >= len(lance):
        return lance

    letra = lance[indice + 1]
    if letra not in mapa:
        return lance
    return lance[: indice + 1] + mapa[letra] + lance[indice + 2 :]


def traduzir_lance_pt_para_san(lance: str) -> str:
    """Converte um lance em notação portuguesa para o SAN que o python-chess lê.

    Ex.: 'Cd5' -> 'Nd5', 'Txc3+' -> 'Rxc3+', 'e8=D' -> 'e8=Q'.
    Lances de peão, roque e lances já em inglês passam sem alteração (mas note
    que 'Rd2' em português é lance de REI e vira 'Kd2', não lance de torre).
    """

    return _traduzir(lance, PT_PARA_EN)


def traduzir_san_para_lance_pt(lance: str) -> str:
    """Converte um SAN em inglês para notação portuguesa, para exibição.

    Ex.: 'Nd5' -> 'Cd5', 'Kd2' -> 'Rd2', 'Rd2' -> 'Td2', 'e8=Q' -> 'e8=D'.
    """

    return _traduzir(lance, EN_PARA_PT)
