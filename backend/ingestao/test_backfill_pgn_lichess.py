"""Testes das funções puras de backfill_pgn_lichess.py (D-62)."""

import unittest

from backend.ingestao.backfill_pgn_lichess import (
    atualizacao_da_partida,
    classificar_troca,
    comeca_de_posicao_customizada,
    contar_lances,
    lances_do_pgn,
    lotes,
)

# O que a coleta gravava antes do D-62: seis cabeçalhos e os lances, sem
# TimeControl. É exatamente por isso que backfill_cadencia.py não resolvia.
PGN_ANTIGO = """[Event "Lichess game"]
[Site "https://lichess.org/ASjC5hjq"]
[Date "2026.09.12"]
[White "dan_merzon"]
[Black "tantofaz123"]
[Result "1-0"]

1. e4 e6 2. Nf3 d5 1-0"""

# O que o Lichess devolve com pgnInJson/tags/clocks: mesma partida, mesmos
# lances, com cabeçalho completo e relógio por lance.
PGN_OFICIAL = """[Event "rated rapid game"]
[Site "https://lichess.org/ASjC5hjq"]
[Date "2026.09.12"]
[White "dan_merzon"]
[Black "tantofaz123"]
[Result "1-0"]
[WhiteElo "1892"]
[BlackElo "1924"]
[TimeControl "600+0"]
[ECO "C01"]

1. e4 { [%clk 0:10:00] } 1... e6 { [%clk 0:10:00] } 2. Nf3 { [%clk 0:09:59] } 2... d5 { [%clk 0:09:59] } 1-0"""


class LancesDoPgnTest(unittest.TestCase):
    def test_conta_meios_lances_ignorando_comentarios(self) -> None:
        self.assertEqual(contar_lances(PGN_ANTIGO), 4)
        self.assertEqual(contar_lances(PGN_OFICIAL), 4)

    def test_os_dois_pgns_descrevem_a_mesma_partida(self) -> None:
        # O que autoriza a troca: os comentários de relógio do PGN oficial não
        # alteram a sequência de lances.
        self.assertEqual(lances_do_pgn(PGN_ANTIGO), lances_do_pgn(PGN_OFICIAL))

    def test_pgn_vazio_ou_ilegivel_devolve_none(self) -> None:
        self.assertIsNone(contar_lances(""))
        self.assertIsNone(contar_lances(None))
        self.assertIsNone(lances_do_pgn(None))


class ClassificarTrocaTest(unittest.TestCase):
    def test_mesma_sequencia_e_troca_igual(self) -> None:
        self.assertEqual(classificar_troca(["e2e4", "e7e6"], ["e2e4", "e7e6"]), "igual")

    def test_prefixo_e_truncamento_do_build_pgn_antigo(self) -> None:
        # O `build_pgn()` anterior tinha um `break` ao topar com SAN que não
        # parseava e gravava a partida pela metade, sem avisar. Duas partidas
        # reais entraram assim: uma com 0 lances (virou `falhou` no Stockfish) e
        # outra com 1 lance que passou por `concluido`.
        self.assertEqual(classificar_troca(["d2d4"], ["d2d4", "d7d5", "c2c4"]), "truncado")
        self.assertEqual(classificar_troca([], ["d2d4", "d7d5"]), "truncado")

    def test_divergencia_no_meio_nao_e_truncamento(self) -> None:
        self.assertEqual(
            classificar_troca(["e2e4", "c7c5"], ["e2e4", "e7e6", "d2d4"]), "divergente"
        )

    def test_pgn_novo_menor_que_o_antigo_e_divergente(self) -> None:
        self.assertEqual(classificar_troca(["e2e4", "e7e6"], ["e2e4"]), "divergente")

    def test_posicao_customizada_explica_a_divergencia(self) -> None:
        # Caso real (`wSfk0zwh`, variant `fromPosition`): a reconstrução antiga
        # sempre partia da posição inicial padrão, então leu os mesmos SAN em
        # outro tabuleiro. O `d4` gravado é um lance diferente do `d4` jogado.
        self.assertEqual(
            classificar_troca(["d2d4"], ["d5d4", "e3d4"], True), "posicao_errada"
        )
        # Sem essa explicação, a mesma divergência continua sendo recusada.
        self.assertEqual(
            classificar_troca(["d2d4"], ["d5d4", "e3d4"], False), "divergente"
        )


class PosicaoCustomizadaTest(unittest.TestCase):
    def test_detecta_setup_e_fen(self) -> None:
        com_fen = PGN_OFICIAL.replace(
            '[ECO "C01"]', '[FEN "3r1rk1/p3qp1p/8/8/8/8/PPP5/2R2RK1 b - - 0 1"]\n[SetUp "1"]'
        )
        self.assertTrue(comeca_de_posicao_customizada(com_fen))

    def test_partida_normal_nao_tem_posicao_propria(self) -> None:
        self.assertFalse(comeca_de_posicao_customizada(PGN_OFICIAL))
        self.assertFalse(comeca_de_posicao_customizada(None))


class AtualizacaoDaPartidaTest(unittest.TestCase):
    def test_troca_segura_traz_pgn_e_cadencia(self) -> None:
        campos, recusa, veredito = atualizacao_da_partida(
            {"pgn": PGN_ANTIGO}, {"pgn": PGN_OFICIAL}
        )
        self.assertEqual((recusa, veredito), ("", "igual"))
        assert campos is not None
        self.assertIn('[TimeControl "600+0"]', campos["pgn"])
        self.assertEqual(campos["cadencia"], "RAPIDA")
        self.assertEqual(campos["tempo_base_segundos"], 600)
        self.assertEqual(campos["incremento_segundos"], 0)
        # Partida íntegra não volta para a fila de análise.
        self.assertNotIn("status_processamento", campos)

    def test_partida_truncada_volta_para_pendente(self) -> None:
        truncado = PGN_ANTIGO.replace("1. e4 e6 2. Nf3 d5 1-0", "1. e4 1-0")
        campos, recusa, veredito = atualizacao_da_partida(
            {"pgn": truncado}, {"pgn": PGN_OFICIAL}
        )
        self.assertEqual((recusa, veredito), ("", "truncado"))
        assert campos is not None
        self.assertEqual(campos["status_processamento"], "pendente")

    def test_recusa_quando_os_lances_divergem(self) -> None:
        # A trava que impede o pior estrago possível: regravar por cima o PGN
        # de OUTRA partida desalinharia `lances_criticos.numero_lance`, e o
        # diagnóstico passaria a apontar para lances que não foram jogados.
        outra = PGN_OFICIAL.replace("1... e6 { [%clk 0:10:00] }", "1... c5")
        campos, recusa, _ = atualizacao_da_partida({"pgn": PGN_ANTIGO}, {"pgn": outra})
        self.assertIsNone(campos)
        self.assertIn("lances divergem", recusa)

    def test_recusa_resposta_sem_pgn(self) -> None:
        campos, recusa, _ = atualizacao_da_partida({"pgn": PGN_ANTIGO}, {})
        self.assertIsNone(campos)
        self.assertEqual(recusa, "resposta sem PGN")

    def test_aceita_quando_o_pgn_antigo_e_ilegivel(self) -> None:
        # Sem base de comparação não há o que desalinhar, e o PGN oficial só
        # pode ser melhor que um ilegível.
        campos, recusa, _ = atualizacao_da_partida({"pgn": ""}, {"pgn": PGN_OFICIAL})
        self.assertEqual(recusa, "")
        assert campos is not None
        self.assertEqual(campos["cadencia"], "RAPIDA")


class LotesTest(unittest.TestCase):
    def test_fatia_respeitando_o_teto(self) -> None:
        self.assertEqual(list(lotes([1, 2, 3, 4, 5], 2)), [[1, 2], [3, 4], [5]])

    def test_lista_vazia_nao_gera_lote(self) -> None:
        self.assertEqual(list(lotes([], 300)), [])


if __name__ == "__main__":
    unittest.main()
