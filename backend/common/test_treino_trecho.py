"""Testes da lógica pura do treino de trecho (D-66)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import chess

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.treino_trecho import (  # noqa: E402
    ELO_MAXIMO_STOCKFISH,
    ELO_MINIMO_STOCKFISH,
    ELO_PADRAO_OPONENTE,
    TOTAL_LANCES_PADRAO,
    classificar_trecho,
    curva_do_trecho,
    elo_do_oponente,
    lances_do_jogador_feitos,
    normalizar_progresso,
    progresso_inicial,
    queda_liquida_do_trecho,
    reconstruir_tabuleiro,
    resumo_do_veredito,
    total_lances_do_trecho,
    trecho_concluido,
)

FEN_INICIAL = chess.STARTING_FEN


class TestTotalLancesDoTrecho(unittest.TestCase):
    def test_conta_a_diferenca_mais_um(self):
        # A forma real dos 106 eventos: 8 lances do jogador, fullmove 12..19.
        self.assertEqual(total_lances_do_trecho(12, 19), 8)

    def test_janela_de_um_lance_so(self):
        self.assertEqual(total_lances_do_trecho(30, 30), 1)

    def test_sem_numero_fim_cai_no_padrao(self):
        self.assertEqual(total_lances_do_trecho(12, None), TOTAL_LANCES_PADRAO)

    def test_intervalo_invertido_cai_no_padrao(self):
        # Dado incoerente não pode gerar um trecho impossível de concluir.
        self.assertEqual(total_lances_do_trecho(19, 12), TOTAL_LANCES_PADRAO)


class TestEloDoOponente(unittest.TestCase):
    def test_usa_o_rating_do_adversario_real(self):
        self.assertEqual(elo_do_oponente(1769, 1810), 1769)

    def test_abaixo_do_piso_do_motor_e_cravado_no_piso(self):
        # 1171 é o adversário mais fraco entre os eventos reais em produção.
        self.assertEqual(elo_do_oponente(1171), ELO_MINIMO_STOCKFISH)

    def test_acima_do_teto_do_motor_e_cravado_no_teto(self):
        self.assertEqual(elo_do_oponente(4000), ELO_MAXIMO_STOCKFISH)

    def test_sem_rating_do_adversario_usa_o_proprio(self):
        self.assertEqual(elo_do_oponente(None, 1850), 1850)

    def test_sem_nenhum_rating_usa_o_padrao(self):
        self.assertEqual(elo_do_oponente(None, None), ELO_PADRAO_OPONENTE)

    def test_rating_zerado_nao_conta_como_rating(self):
        self.assertEqual(elo_do_oponente(0, 0), ELO_PADRAO_OPONENTE)


class TestReconstruirTabuleiro(unittest.TestCase):
    def test_replay_devolve_a_posicao_corrente(self):
        board = reconstruir_tabuleiro(FEN_INICIAL, ["e4", "e5", "Nf3"])
        self.assertEqual(board.fullmove_number, 2)
        self.assertEqual(board.turn, chess.BLACK)

    def test_sem_lances_devolve_a_posicao_inicial(self):
        board = reconstruir_tabuleiro(FEN_INICIAL, [])
        self.assertEqual(board.fen(), FEN_INICIAL)

    def test_san_ilegal_no_historico_estoura(self):
        # Estado corrompido, não erro do usuário: quem chama transforma isso em
        # "recomeçar o trecho", nunca num 400 culpando quem respondeu.
        with self.assertRaises(ValueError) as contexto:
            reconstruir_tabuleiro(FEN_INICIAL, ["e4", "e5", "Qxh8"])
        self.assertIn("corrompido", str(contexto.exception))


class TestNormalizarProgresso(unittest.TestCase):
    def test_none_vira_progresso_zerado(self):
        progresso = normalizar_progresso(None, FEN_INICIAL, 8)
        self.assertEqual(progresso, progresso_inicial(FEN_INICIAL, 8))

    def test_preserva_um_progresso_coerente(self):
        bruto = {
            "fen_inicial": "outra-coisa",
            "total_lances": 99,
            "lances": ["e4", "e5"],
            "win_antes": [50.0],
            "win_depois": [48.0],
        }
        progresso = normalizar_progresso(bruto, FEN_INICIAL, 8)
        self.assertEqual(progresso["lances"], ["e4", "e5"])
        self.assertEqual(progresso["win_depois"], [48.0])
        # O ponto de partida e o tamanho vêm SEMPRE do evento, nunca do jsonb.
        self.assertEqual(progresso["fen_inicial"], FEN_INICIAL)
        self.assertEqual(progresso["total_lances"], 8)

    def test_contagens_que_nao_fecham_zeram_o_progresso(self):
        bruto = {"lances": ["e4", "e5", "Nf3"], "win_antes": [50.0], "win_depois": [48.0]}
        progresso = normalizar_progresso(bruto, FEN_INICIAL, 8)
        self.assertEqual(progresso["lances"], [])

    def test_lista_com_lixo_zera_o_progresso(self):
        # Descartar só o item inválido deixaria ['e4'] — um histórico que ainda
        # "fecha" nas contagens e reconstrói a posição errada em silêncio.
        bruto = {"lances": ["e4", None], "win_antes": [50.0], "win_depois": [48.0]}
        progresso = normalizar_progresso(bruto, FEN_INICIAL, 8)
        self.assertEqual(progresso["lances"], [])

    def test_ultimo_lance_sem_resposta_do_motor_e_valido(self):
        # No fim da janela o motor não responde: 2k-1 SAN é o estado correto.
        bruto = {
            "lances": ["e4", "e5", "Nf3"],
            "win_antes": [50.0, 49.0],
            "win_depois": [49.5, 48.0],
        }
        progresso = normalizar_progresso(bruto, FEN_INICIAL, 2)
        self.assertEqual(len(progresso["lances"]), 3)

    def test_historico_impar_no_meio_do_trecho_zera_o_progresso(self):
        # Mesma forma do teste acima, mas faltando 6 lances para o fim: aqui a
        # vez seria do MOTOR, e o próximo lance do usuário entraria torto.
        bruto = {
            "lances": ["e4", "e5", "Nf3"],
            "win_antes": [50.0, 49.0],
            "win_depois": [49.5, 48.0],
        }
        progresso = normalizar_progresso(bruto, FEN_INICIAL, 8)
        self.assertEqual(progresso["lances"], [])

    def test_booleano_nao_passa_por_numero(self):
        bruto = {"lances": ["e4", "e5"], "win_antes": [True], "win_depois": [48.0]}
        progresso = normalizar_progresso(bruto, FEN_INICIAL, 8)
        self.assertEqual(progresso["lances"], [])


class TestContagemEConclusao(unittest.TestCase):
    def test_conta_os_lances_do_jogador(self):
        progresso = {"win_depois": [50.0, 48.0, 47.0], "total_lances": 8}
        self.assertEqual(lances_do_jogador_feitos(progresso), 3)
        self.assertFalse(trecho_concluido(progresso))

    def test_conclui_ao_bater_o_total(self):
        progresso = {"win_depois": [1.0] * 8, "total_lances": 8}
        self.assertTrue(trecho_concluido(progresso))


class TestQuedaLiquida(unittest.TestCase):
    def test_usa_o_primeiro_antes_e_o_ultimo_depois(self):
        # A mesma conta de detectar_erosao: win% antes do 1º lance do jogador
        # menos win% depois do último lance DELE (não da resposta do motor).
        progresso = {
            "win_antes": [61.0, 57.0, 53.0],
            "win_depois": [58.0, 54.0, 41.0],
        }
        self.assertEqual(queda_liquida_do_trecho(progresso), 20.0)

    def test_melhora_devolve_queda_negativa(self):
        progresso = {"win_antes": [40.0], "win_depois": [52.5]}
        self.assertEqual(queda_liquida_do_trecho(progresso), -12.5)

    def test_trecho_sem_lance_nenhum_nao_tem_queda(self):
        self.assertEqual(queda_liquida_do_trecho(progresso_inicial(FEN_INICIAL, 8)), 0.0)


class TestCurvaDoTrecho(unittest.TestCase):
    def test_pega_so_os_lances_do_jogador(self):
        progresso = {
            "lances": ["Nf3", "d5", "e3", "Bf5"],
            "win_antes": [61.0, 57.0],
            "win_depois": [58.0, 54.0],
        }
        curva = curva_do_trecho(progresso)
        self.assertEqual([item.lance for item in curva], ["Nf3", "e3"])
        self.assertEqual([item.numero for item in curva], [1, 2])
        self.assertEqual([item.queda for item in curva], [3.0, 3.0])

    def test_curva_de_trecho_vazio_e_vazia(self):
        self.assertEqual(curva_do_trecho(progresso_inicial(FEN_INICIAL, 8)), [])


class TestClassificarTrecho(unittest.TestCase):
    def test_abaixo_do_limiar_do_detector_e_bom(self):
        # 15% é o mesmo EROSAO_THRESHOLD_PERCENT que criou o evento: abaixo
        # dele, pelo instrumento que gerou este card, não houve erosão.
        self.assertEqual(classificar_trecho(14.9, 42.0, 15.0), "BOM")

    def test_melhorar_a_posicao_e_bom(self):
        self.assertEqual(classificar_trecho(-8.0, 42.0, 15.0), "BOM")

    def test_errar_menos_que_na_partida_e_subotimo(self):
        self.assertEqual(classificar_trecho(30.0, 42.0, 15.0), "SUBOTIMO")

    def test_repetir_a_queda_da_partida_e_ruim(self):
        self.assertEqual(classificar_trecho(42.0, 42.0, 15.0), "RUIM")

    def test_piorar_e_ruim(self):
        self.assertEqual(classificar_trecho(55.0, 42.0, 15.0), "RUIM")

    def test_sem_queda_original_so_o_limiar_absoluto_decide(self):
        # O card ainda precisa poder se formar quando o evento não guardou a
        # queda original — aí o alvo absoluto é o único critério honesto.
        self.assertEqual(classificar_trecho(30.0, None, 15.0), "RUIM")
        self.assertEqual(classificar_trecho(10.0, None, 15.0), "BOM")


class TestResumoDoVeredito(unittest.TestCase):
    def test_bom_cita_a_queda_da_partida(self):
        texto = resumo_do_veredito("BOM", 4.0, 42.0)
        self.assertIn("segurou", texto)
        self.assertIn("42.0%", texto)

    def test_melhora_e_dita_como_melhora(self):
        texto = resumo_do_veredito("BOM", -8.0, 42.0)
        self.assertIn("melhorou", texto)
        self.assertIn("8.0%", texto)

    def test_ruim_nao_ameniza(self):
        texto = resumo_do_veredito("RUIM", 50.0, 42.0)
        self.assertIn("escorregou", texto)

    def test_sem_queda_original_nao_inventa_comparacao(self):
        texto = resumo_do_veredito("SUBOTIMO", 30.0, None)
        self.assertNotIn("Na partida", texto)


if __name__ == "__main__":
    unittest.main()
