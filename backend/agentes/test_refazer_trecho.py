"""Testes do passo do treino de trecho contra o motor (D-66).

O Stockfish é substituído por um duplo: o que precisa ser verificado aqui é o
protocolo com o motor (força limitada, restauração, quantas leituras, quando
parar), não a qualidade das jogadas dele.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import chess

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.agentes.refazer_trecho import (  # noqa: E402
    jogar_passo_do_trecho,
    lance_do_motor,
)
from backend.common.treino_trecho import (  # noqa: E402
    ProgressoCorrompidoError,
    progresso_inicial,
)


class MotorFalso:
    """Stockfish de mentira, com memória do que foi pedido a ele.

    `avaliacoes` é uma fila de centipawns devolvidos em ordem; `respostas` é a
    fila de lances (UCI) que ele "escolhe". `historico_forca` registra cada
    mudança de força, que é o que garante que o motor compartilhado não fica
    enfraquecido depois do passo (R3).
    """

    def __init__(self, avaliacoes: list[int], respostas: list[str] | None = None):
        self.avaliacoes = list(avaliacoes)
        self.respostas = list(respostas or [])
        self.fen_corrente = ""
        self.historico_forca: list[str] = []
        self.chamadas_de_avaliacao = 0

    def set_fen_position(self, fen: str) -> None:
        self.fen_corrente = fen

    def get_evaluation(self) -> dict[str, object]:
        self.chamadas_de_avaliacao += 1
        valor = self.avaliacoes.pop(0) if self.avaliacoes else 0
        return {"type": "cp", "value": valor}

    def get_best_move(self) -> str | None:
        return self.respostas.pop(0) if self.respostas else None

    def set_elo_rating(self, elo: int) -> None:
        self.historico_forca.append(f"elo:{elo}")

    def resume_full_strength(self) -> None:
        self.historico_forca.append("full")


# Posição neutra de meio-jogo com as brancas na vez; serve de janela do trecho.
FEN_JANELA = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"


class LanceDoMotorTest(unittest.TestCase):
    def test_limita_a_forca_e_devolve_ao_maximo(self) -> None:
        motor = MotorFalso([], ["b1c3"])
        board = chess.Board(FEN_JANELA)

        san = lance_do_motor(motor, board, 1500)

        self.assertEqual(san, "Nc3")
        self.assertEqual(motor.historico_forca, ["elo:1500", "full"])

    def test_devolve_forca_maxima_mesmo_se_o_motor_estourar(self) -> None:
        """O motor é um só, compartilhado (R3): sair daqui fraco envenenaria a
        próxima análise de partida sem aparecer como erro em lugar nenhum."""

        class MotorQueEstoura(MotorFalso):
            def get_best_move(self):
                raise RuntimeError("subprocesso morreu")

        motor = MotorQueEstoura([])
        with self.assertRaises(RuntimeError):
            lance_do_motor(motor, chess.Board(FEN_JANELA), 1500)

        self.assertEqual(motor.historico_forca, ["elo:1500", "full"])

    def test_lance_ilegal_do_motor_vira_none(self) -> None:
        motor = MotorFalso([], ["a1a8"])
        self.assertIsNone(lance_do_motor(motor, chess.Board(FEN_JANELA), 1500))

    def test_uci_sem_sentido_vira_none(self) -> None:
        motor = MotorFalso([], ["xyz"])
        self.assertIsNone(lance_do_motor(motor, chess.Board(FEN_JANELA), 1500))

    def test_sem_lance_nenhum_vira_none(self) -> None:
        motor = MotorFalso([], [])
        self.assertIsNone(lance_do_motor(motor, chess.Board(FEN_JANELA), 1500))


class JogarPassoDoTrechoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.progresso = progresso_inicial(FEN_JANELA, 8)

    def test_grava_lance_resposta_e_as_duas_leituras(self) -> None:
        motor = MotorFalso([100, 60], ["f8c5"])  # antes, depois

        passo = jogar_passo_do_trecho(motor, None, self.progresso, "d3", 1500)

        self.assertEqual(passo.progresso["lances"], ["d3", "Bc5"])
        self.assertEqual(len(passo.progresso["win_antes"]), 1)
        self.assertEqual(len(passo.progresso["win_depois"]), 1)
        self.assertGreater(passo.progresso["win_antes"][0], passo.progresso["win_depois"][0])
        self.assertEqual(passo.lance_oponente, "Bc5")
        self.assertFalse(passo.concluido)
        # Duas leituras por passo, nunca mais: a terceira interação com o motor
        # é a escolha da resposta, que não é avaliação.
        self.assertEqual(motor.chamadas_de_avaliacao, 2)

    def test_a_posicao_vem_do_historico_e_nao_do_cliente(self) -> None:
        motor = MotorFalso([0, 0], ["d7d6"])
        progresso = dict(
            self.progresso, lances=["d3", "Bc5"], win_antes=[50.0], win_depois=[48.0]
        )

        passo = jogar_passo_do_trecho(motor, None, progresso, "Be3", 1500)

        self.assertEqual(passo.progresso["lances"], ["d3", "Bc5", "Be3", "d6"])
        self.assertIn("Be3", passo.progresso["lances"])

    def test_ultimo_lance_da_janela_nao_pede_resposta_ao_motor(self) -> None:
        motor = MotorFalso([0, 0], ["f8c5"])
        progresso = progresso_inicial(FEN_JANELA, 1)

        passo = jogar_passo_do_trecho(motor, None, progresso, "d3", 1500)

        self.assertIsNone(passo.lance_oponente)
        self.assertTrue(passo.concluido)
        self.assertFalse(passo.fim_por_fim_de_jogo)
        self.assertEqual(motor.historico_forca, [])  # o motor nunca foi enfraquecido

    def test_mate_do_jogador_encerra_com_100_por_cento(self) -> None:
        """Sem o desvio de posição terminal, o Stockfish devolveria `mate 0`,
        que `evaluation_to_cp` lê como vantagem das BRANCAS mesmo quando quem
        deu o mate foram as pretas."""
        # Mate do louco: 1.f3 e5 2.g4, e as pretas matam com Dh4.
        fen = "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2"
        motor = MotorFalso([0], [])
        progresso = progresso_inicial(fen, 8)

        passo = jogar_passo_do_trecho(motor, None, progresso, "Qh4#", 1500)

        self.assertTrue(passo.concluido)
        self.assertTrue(passo.fim_por_fim_de_jogo)
        self.assertEqual(passo.progresso["win_depois"][-1], 100.0)
        self.assertIsNone(passo.lance_oponente)

    def test_motor_sem_resposta_encerra_sem_alegar_fim_de_partida(self) -> None:
        motor = MotorFalso([0, 0], [])

        passo = jogar_passo_do_trecho(motor, None, self.progresso, "d3", 1500)

        self.assertTrue(passo.concluido)
        self.assertFalse(passo.fim_por_fim_de_jogo)

    def test_lance_invalido_do_usuario_estoura_value_error(self) -> None:
        motor = MotorFalso([0, 0], ["f8c5"])

        with self.assertRaises(ValueError) as contexto:
            jogar_passo_do_trecho(motor, None, self.progresso, "Rxh8", 1500)

        self.assertNotIsInstance(contexto.exception, ProgressoCorrompidoError)

    def test_historico_impossivel_estoura_progresso_corrompido(self) -> None:
        motor = MotorFalso([0, 0], ["f8c5"])
        progresso = dict(self.progresso, lances=["Qh5"], win_antes=[50.0], win_depois=[50.0])

        with self.assertRaises(ProgressoCorrompidoError):
            jogar_passo_do_trecho(motor, None, progresso, "d3", 1500)

    def test_perspectiva_e_a_do_jogador_do_card(self) -> None:
        """Numa janela das PRETAS, avaliação positiva para as brancas tem que
        virar win% BAIXO — senão a queda sairia com o sinal trocado."""
        fen = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 5 4"
        motor = MotorFalso([0, 400], [])
        progresso = progresso_inicial(fen, 1)

        passo = jogar_passo_do_trecho(motor, None, progresso, "Bc5", 1500)

        self.assertEqual(passo.progresso["win_antes"][0], 50.0)
        self.assertLess(passo.progresso["win_depois"][0], 50.0)


if __name__ == "__main__":
    unittest.main()
