"""Testes unitários da tradução de notação PT <-> SAN em inglês."""

import unittest

from backend.common.notacao_pt import (
    traduzir_lance_pt_para_san,
    traduzir_san_para_lance_pt,
)


class TraduzirLancePtParaSanTest(unittest.TestCase):
    def test_traduz_cada_letra_de_peca(self) -> None:
        casos = {
            "Cf3": "Nf3",  # Cavalo -> kNight
            "Te1": "Re1",  # Torre -> Rook
            "Dd8": "Qd8",  # Dama -> Queen
            "Rg1": "Kg1",  # Rei -> King
            "Bb5": "Bb5",  # Bispo continua B
        }
        for lance_pt, esperado in casos.items():
            with self.subTest(lance=lance_pt):
                self.assertEqual(traduzir_lance_pt_para_san(lance_pt), esperado)

    def test_preserva_captura_xeque_e_desambiguacao(self) -> None:
        self.assertEqual(traduzir_lance_pt_para_san("Txc3+"), "Rxc3+")
        self.assertEqual(traduzir_lance_pt_para_san("Cbd2"), "Nbd2")
        self.assertEqual(traduzir_lance_pt_para_san("D1xd7#"), "Q1xd7#")

    def test_lance_de_peao_fica_inalterado(self) -> None:
        for lance in ["e4", "exd5", "d6", "cxb4+", "b1"]:
            with self.subTest(lance=lance):
                self.assertEqual(traduzir_lance_pt_para_san(lance), lance)

    def test_so_traduz_o_primeiro_caractere(self) -> None:
        # O 'd' e o 'c' de destino não podem ser confundidos com letras de peça,
        # e um 'R' que não esteja na 1ª posição também não deve ser tocado.
        self.assertEqual(traduzir_lance_pt_para_san("Cd5"), "Nd5")
        self.assertEqual(traduzir_lance_pt_para_san("Txb7"), "Rxb7")

    def test_roque_nao_muda(self) -> None:
        self.assertEqual(traduzir_lance_pt_para_san("O-O"), "O-O")
        self.assertEqual(traduzir_lance_pt_para_san("O-O-O"), "O-O-O")
        self.assertEqual(traduzir_lance_pt_para_san("O-O+"), "O-O+")

    def test_promocao_e_traduzida(self) -> None:
        self.assertEqual(traduzir_lance_pt_para_san("e8=D"), "e8=Q")
        self.assertEqual(traduzir_lance_pt_para_san("a1=T"), "a1=R")
        self.assertEqual(traduzir_lance_pt_para_san("bxc8=C+"), "bxc8=N+")
        self.assertEqual(traduzir_lance_pt_para_san("h8=B"), "h8=B")

    def test_entrada_vazia_ou_espacos(self) -> None:
        self.assertEqual(traduzir_lance_pt_para_san(""), "")
        self.assertEqual(traduzir_lance_pt_para_san("  Cf3  "), "Nf3")


class TraduzirSanParaLancePtTest(unittest.TestCase):
    def test_traduz_de_volta_cada_letra(self) -> None:
        casos = {
            "Nf3": "Cf3",
            "Re1": "Te1",
            "Qd8": "Dd8",
            "Kg1": "Rg1",
            "Bb5": "Bb5",
        }
        for san, esperado in casos.items():
            with self.subTest(san=san):
                self.assertEqual(traduzir_san_para_lance_pt(san), esperado)

    def test_rei_e_torre_nao_se_confundem_na_volta(self) -> None:
        # 'Rd2' em inglês é Torre (-> Td2); Rei em inglês é 'Kd2' (-> Rd2).
        self.assertEqual(traduzir_san_para_lance_pt("Rd2"), "Td2")
        self.assertEqual(traduzir_san_para_lance_pt("Kd2"), "Rd2")

    def test_peao_promocao_e_roque_na_volta(self) -> None:
        self.assertEqual(traduzir_san_para_lance_pt("exd5"), "exd5")
        self.assertEqual(traduzir_san_para_lance_pt("e8=Q"), "e8=D")
        self.assertEqual(traduzir_san_para_lance_pt("O-O-O"), "O-O-O")

    def test_ida_e_volta_preserva_o_lance_em_portugues(self) -> None:
        for lance_pt in ["Cf3", "Txc3+", "Dd8", "Rg1", "Bb5", "e8=D", "O-O", "exd5"]:
            with self.subTest(lance=lance_pt):
                san = traduzir_lance_pt_para_san(lance_pt)
                self.assertEqual(traduzir_san_para_lance_pt(san), lance_pt)


if __name__ == "__main__":
    unittest.main()
