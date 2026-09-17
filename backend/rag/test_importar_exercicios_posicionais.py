"""Testes de backend/rag/importar_exercicios_posicionais.py (D-55).

Cobre as funções puras (leitura da anotação do Lichess, filtros de seleção,
classificação em categoria do hexágono, procedência) e a orquestração de
`importar()` com um client Supabase mockado e um PGN de verdade em memória -
nenhum teste aqui baixa o dump real do Lichess.

O PGN usado nos testes é um trecho autêntico do broadcast de novembro/2022,
incluindo as anotações `[%eval]`, `[%clk]` e "Blunder. X was best." exatamente
no formato que o Lichess publica.
"""

from __future__ import annotations

import io
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import chess
import chess.pgn

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.rag.importar_exercicios_posicionais import (  # noqa: E402
    CATEGORIAS_APLICAVEIS,
    centipeoes,
    classificar_posicao,
    contar_pecas_maiores,
    data_da_partida,
    decisao_ainda_em_aberto,
    erro_custou_caro,
    extrair_exercicios_do_jogo,
    importar,
    interpretar_anotacao,
    lance_e_quieto,
    meses_padrao,
    nome_do_jogador,
    partida_tem_titulado,
    registro_do_erro,
    ReservatorioPorCategoria,
)

# Meio-jogo equilibrado, brancas a jogar, com peças de sobra.
FEN_MEIOJOGO = "r3r1k1/1pqn1pb1/3p1np1/p2Pp2p/2P5/PN2BP1P/1P1Q2P1/1K1R1B1R w - - 1 17"

PGN_BROADCAST = """[Event "Round 7: Aroshidze Levan - Garriga Cazorla Pere"]
[White "Aroshidze Levan"]
[Black "Garriga Cazorla Pere"]
[Result "1-0"]
[WhiteTitle "GM"]
[BlackTitle "IM"]
[UTCDate "2022.11.01"]
[BroadcastName "Campionat Absolut De Catalunya 2022"]
[GameURL "https://lichess.org/broadcast/catalunya/round-7/tLbepv3Z/cYAlXROk"]

1. d4 { [%eval 0.0] [%clk 1:30:00] } 1... d5 { [%eval 0.1] [%clk 1:30:00] } \
2. Nf3 { [%eval 0.0] [%clk 1:29:00] } 2... Nf6 { [%eval 0.1] [%clk 1:29:00] } \
3. e3?? { [%eval -2.0] } { Blunder. c4 was best. } { [%clk 1:28:00] } 1-0
"""


def carregar_jogo(pgn: str = PGN_BROADCAST) -> chess.pgn.Game:
    jogo = chess.pgn.read_game(io.StringIO(pgn))
    assert jogo is not None
    return jogo


class InterpretarAnotacaoTest(unittest.TestCase):
    """A anotação do Lichess é a fonte de "onde alguém errou e o que era
    melhor" - sem ela não haveria como achar as posições."""

    def test_le_severidade_e_melhor_lance(self) -> None:
        self.assertEqual(
            interpretar_anotacao("[%eval 2.24] Blunder. bxc4 was best. [%clk 0:34:44]"),
            ("Blunder", "bxc4"),
        )

    def test_aceita_mistake(self) -> None:
        self.assertEqual(
            interpretar_anotacao("[%eval -0.26] Mistake. a4 was best."), ("Mistake", "a4")
        )

    def test_descarta_inaccuracy(self) -> None:
        """Imprecisão de GM raramente tem resposta única o bastante para virar
        exercício; no mês de amostra elas eram 15.425 das ~21.000 anotações."""
        self.assertIsNone(interpretar_anotacao("[%eval 0.45] Inaccuracy. a4 was best."))

    def test_lance_sem_anotacao_de_erro(self) -> None:
        self.assertIsNone(interpretar_anotacao("[%eval 0.32] [%clk 1:30:01]"))

    def test_comentario_vazio_ou_nulo(self) -> None:
        self.assertIsNone(interpretar_anotacao(""))
        self.assertIsNone(interpretar_anotacao(None))


class FiltrosDeSelecaoTest(unittest.TestCase):
    def test_posicao_equilibrada_esta_em_aberto(self) -> None:
        self.assertTrue(decisao_ainda_em_aberto(50))
        self.assertTrue(decisao_ainda_em_aberto(-300))

    def test_posicao_ja_decidida_e_descartada(self) -> None:
        """"Ache o melhor lance" numa posição ganha treina conversão, que é
        outra habilidade - e o usuário não teria como saber qual cobramos."""
        self.assertFalse(decisao_ainda_em_aberto(900))
        self.assertFalse(decisao_ainda_em_aberto(-900))

    def test_queda_grande_vira_exercicio(self) -> None:
        self.assertTrue(erro_custou_caro(50, -150))

    def test_queda_pequena_nao_vira_exercicio(self) -> None:
        self.assertFalse(erro_custou_caro(50, 10))

    def test_centipeoes_do_ponto_de_vista_de_quem_joga(self) -> None:
        avaliacao = chess.engine.PovScore(chess.engine.Cp(120), chess.WHITE)
        self.assertEqual(centipeoes(avaliacao, chess.WHITE), 120)
        self.assertEqual(centipeoes(avaliacao, chess.BLACK), -120)

    def test_centipeoes_sem_avaliacao(self) -> None:
        self.assertIsNone(centipeoes(None, chess.WHITE))

    def test_mate_vira_numero_grande_em_vez_de_estourar(self) -> None:
        avaliacao = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)
        self.assertGreater(centipeoes(avaliacao, chess.WHITE) or 0, 1000)


class LanceQuietoTest(unittest.TestCase):
    """O filtro central do D-55: é ele que separa decisão posicional de tática
    disfarçada, e portanto o que torna ESTRATEGIA um rótulo honesto."""

    def setUp(self) -> None:
        self.board = chess.Board(FEN_MEIOJOGO)

    def test_lance_tranquilo_passa(self) -> None:
        self.assertTrue(lance_e_quieto(self.board, self.board.parse_san("Bf4")))

    def test_captura_nao_passa(self) -> None:
        self.assertFalse(lance_e_quieto(self.board, self.board.parse_san("Nxa5")))

    def test_xeque_nao_passa(self) -> None:
        board = chess.Board("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
        self.assertFalse(lance_e_quieto(board, board.parse_san("Ra8+")))

    def test_promocao_nao_passa(self) -> None:
        board = chess.Board("8/P7/8/8/8/8/8/K6k w - - 0 1")
        self.assertFalse(lance_e_quieto(board, board.parse_san("a8=Q")))


class ClassificarPosicaoTest(unittest.TestCase):
    def test_relogio_baixo_vence_qualquer_outra_leitura(self) -> None:
        """Errar com dois minutos é falha de gestão de tempo, seja qual for a
        natureza do lance. É esta categoria que o D-49 declarou impossível com
        puzzles - e estava certo: puzzle não tem relógio, broadcast tem."""
        board = chess.Board(FEN_MEIOJOGO)
        captura = board.parse_san("Nxa5")
        self.assertEqual(
            classificar_posicao(board, captura, segundos_restantes=45),
            "GESTAO_DE_TEMPO",
        )

    def test_lance_tatico_com_relogio_folgado_e_descartado(self) -> None:
        board = chess.Board(FEN_MEIOJOGO)
        self.assertIsNone(
            classificar_posicao(board, board.parse_san("Nxa5"), segundos_restantes=3600)
        )

    def test_sem_relogio_no_pgn_ainda_classifica(self) -> None:
        board = chess.Board(FEN_MEIOJOGO)
        self.assertEqual(
            classificar_posicao(board, board.parse_san("Bf4"), segundos_restantes=None),
            "ESTRATEGIA",
        )

    def test_poucas_pecas_e_final(self) -> None:
        board = chess.Board("8/5pk1/6p1/8/8/6P1/5PK1/3R4 w - - 0 40")
        self.assertEqual(
            classificar_posicao(board, board.parse_san("Rd7"), segundos_restantes=None),
            "FINAIS",
        )

    def test_lance_de_peao_no_meiojogo_e_estrutura(self) -> None:
        board = chess.Board(FEN_MEIOJOGO)
        self.assertEqual(
            classificar_posicao(board, board.parse_san("g4"), segundos_restantes=None),
            "ESTRUTURA_DE_PEOES",
        )

    def test_so_produz_as_quatro_categorias_previstas(self) -> None:
        """TATICA e CALCULO ficam de fora por construção: são exatamente o que
        o filtro de lance quieto exclui, e já têm 300 exercícios cada (D-49)."""
        self.assertEqual(
            CATEGORIAS_APLICAVEIS,
            frozenset({"ESTRATEGIA", "FINAIS", "ESTRUTURA_DE_PEOES", "GESTAO_DE_TEMPO"}),
        )

    def test_conta_pecas_ignorando_reis_e_peoes(self) -> None:
        self.assertEqual(contar_pecas_maiores(chess.Board()), 14)
        self.assertEqual(contar_pecas_maiores(chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1")), 0)


class ProcedenciaTest(unittest.TestCase):
    """A licença dos broadcasts é CC BY-SA 4.0: a atribuição não é enfeite."""

    def test_nome_com_titulo(self) -> None:
        self.assertEqual(nome_do_jogador("Aroshidze Levan", "GM"), "GM Aroshidze Levan")

    def test_nome_sem_titulo(self) -> None:
        self.assertEqual(nome_do_jogador("Fulano", ""), "Fulano")

    def test_nome_ausente_vira_none(self) -> None:
        self.assertIsNone(nome_do_jogador("?", "GM"))
        self.assertIsNone(nome_do_jogador(None, None))

    def test_data_preferindo_utcdate(self) -> None:
        self.assertEqual(
            data_da_partida({"UTCDate": "2022.11.01", "Date": "2020.01.01"}),
            date(2022, 11, 1),
        )

    def test_data_desconhecida_do_broadcast(self) -> None:
        """'????.??.??' aparece o tempo todo nos broadcasts; é falta de dado,
        não erro a tratar."""
        self.assertIsNone(data_da_partida({"Date": "????.??.??"}))
        self.assertIsNone(data_da_partida({}))


class RegistroDoErroTest(unittest.TestCase):
    def _chamar(self, **overrides):
        board = chess.Board(FEN_MEIOJOGO)
        argumentos = {
            "board": board,
            "comentario_do_lance": "[%eval -2.0] Blunder. Bf4 was best.",
            "avaliacao_antes": chess.engine.PovScore(chess.engine.Cp(20), chess.WHITE),
            "avaliacao_depois": chess.engine.PovScore(chess.engine.Cp(-200), chess.WHITE),
            "segundos_restantes": 3600,
            "headers": {
                "GameURL": "https://lichess.org/broadcast/x/y/z",
                "White": "Aroshidze Levan",
                "WhiteTitle": "GM",
                "Black": "Garriga Cazorla Pere",
                "BlackTitle": "IM",
                "BroadcastName": "Campionat Absolut De Catalunya 2022",
                "UTCDate": "2022.11.01",
            },
        }
        argumentos.update(overrides)
        return registro_do_erro(**argumentos)

    def test_monta_o_registro_completo(self) -> None:
        registro = self._chamar()

        self.assertIsNotNone(registro)
        assert registro is not None
        self.assertEqual(registro["categoria_hexagono"], "ESTRATEGIA")
        self.assertEqual(registro["severidade"], "Blunder")
        self.assertEqual(registro["queda_centipeoes"], 220)
        self.assertEqual(registro["fen"], FEN_MEIOJOGO)
        self.assertEqual(registro["brancas"], "GM Aroshidze Levan")
        self.assertEqual(registro["evento"], "Campionat Absolut De Catalunya 2022")
        self.assertEqual(registro["data_partida"], "2022-11-01")

    def test_nao_guarda_a_resposta_certa(self) -> None:
        """Mesma decisão do D-49, e aqui ela também resolve o problema de
        posição posicional ter vários lances bons: quem avalia é o Stockfish
        na hora, medindo queda - não a comparação com um gabarito."""
        registro = self._chamar()

        assert registro is not None
        self.assertNotIn("melhor_lance", registro)
        self.assertNotIn("solucao", registro)

    def test_relogio_so_e_guardado_quando_e_o_exercicio(self) -> None:
        folgado = self._chamar()
        assert folgado is not None
        self.assertIsNone(folgado["segundos_restantes"])

        apertado = self._chamar(segundos_restantes=45)
        assert apertado is not None
        self.assertEqual(apertado["categoria_hexagono"], "GESTAO_DE_TEMPO")
        self.assertEqual(apertado["segundos_restantes"], 45)

    def test_san_ilegal_de_transmissao_ao_vivo_e_descartado(self) -> None:
        """Operador de torneio digita lance errado; o PGN publicado carrega o
        erro. Isso é dado ruim, não exceção a propagar."""
        self.assertIsNone(
            self._chamar(comentario_do_lance="[%eval -2.0] Blunder. Qz9 was best.")
        )

    def test_sem_avaliacao_nao_da_para_filtrar(self) -> None:
        self.assertIsNone(self._chamar(avaliacao_antes=None))

    def test_sem_url_da_partida_nao_ha_procedencia(self) -> None:
        self.assertIsNone(self._chamar(headers={"White": "Fulano"}))


class ExigirTituloTest(unittest.TestCase):
    """Sem este filtro a primeira execução real trouxe 1200 exercícios de um
    único dia de opens juvenis — OTB de verdade, mas longe de "partida real
    conhecida"."""

    def test_reconhece_titulo_em_qualquer_um_dos_lados(self) -> None:
        self.assertTrue(partida_tem_titulado({"WhiteTitle": "GM"}))
        self.assertTrue(partida_tem_titulado({"BlackTitle": "WIM"}))

    def test_partida_sem_titulo_nenhum(self) -> None:
        self.assertFalse(partida_tem_titulado({"White": "Fulano", "Black": "Beltrano"}))
        self.assertFalse(partida_tem_titulado({"WhiteTitle": ""}))

    def test_titulo_nao_fide_nao_conta(self) -> None:
        self.assertFalse(partida_tem_titulado({"WhiteTitle": "LM"}))

    def test_jogo_sem_titulado_e_ignorado_por_padrao(self) -> None:
        pgn = PGN_BROADCAST.replace('[WhiteTitle "GM"]\n', "").replace(
            '[BlackTitle "IM"]\n', ""
        )
        self.assertEqual(extrair_exercicios_do_jogo(carregar_jogo(pgn)), [])

    def test_filtro_pode_ser_desligado_para_priorizar_volume(self) -> None:
        pgn = PGN_BROADCAST.replace('[WhiteTitle "GM"]\n', "").replace(
            '[BlackTitle "IM"]\n', ""
        )
        self.assertEqual(
            len(extrair_exercicios_do_jogo(carregar_jogo(pgn), exigir_titulo=False)), 1
        )


class ExtrairDoJogoTest(unittest.TestCase):
    def test_encontra_o_erro_anotado_na_partida_real(self) -> None:
        exercicios = extrair_exercicios_do_jogo(carregar_jogo())

        self.assertEqual(len(exercicios), 1)
        exercicio = exercicios[0]
        self.assertEqual(exercicio["numero_lance"], 3)
        self.assertEqual(exercicio["ply"], 4)
        self.assertEqual(exercicio["categoria_hexagono"], "ESTRUTURA_DE_PEOES")
        self.assertEqual(exercicio["brancas"], "GM Aroshidze Levan")
        self.assertIn("rnbqkb1r", exercicio["fen"])

    def test_partida_sem_erro_anotado_nao_rende_exercicio(self) -> None:
        pgn = PGN_BROADCAST.replace("Blunder. c4 was best.", "")
        self.assertEqual(extrair_exercicios_do_jogo(carregar_jogo(pgn)), [])


class ImportarTest(unittest.TestCase):
    def test_upsert_em_lote_com_a_chave_de_conflito_certa(self) -> None:
        client = MagicMock()
        with patch(
            "backend.rag.importar_exercicios_posicionais.iterar_jogos_broadcast",
            return_value=iter([carregar_jogo()]),
        ):
            resumo = importar(client, MagicMock(), meses=["2022-11"])

        self.assertEqual(resumo["partidas_lidas"], 1)
        self.assertEqual(resumo["exercicios_importados"], 1)
        (lote,), kwargs = client.table.return_value.upsert.call_args
        self.assertEqual(kwargs.get("on_conflict"), "jogo_url,ply")
        self.assertEqual(len(lote), 1)
        client.table.assert_called_with("exercicios_posicionais")

    def test_mesma_partida_repetida_no_dump_nao_duplica_no_lote(self) -> None:
        """Rodadas retransmitidas repetem partidas. O upsert aguenta, mas o
        Postgres recusa a mesma chave duas vezes no MESMO lote."""
        client = MagicMock()
        with patch(
            "backend.rag.importar_exercicios_posicionais.iterar_jogos_broadcast",
            return_value=iter([carregar_jogo(), carregar_jogo()]),
        ):
            resumo = importar(client, MagicMock(), meses=["2022-11"])

        self.assertEqual(resumo["partidas_lidas"], 2)
        self.assertEqual(resumo["exercicios_importados"], 1)

    def test_teto_por_categoria_e_respeitado(self) -> None:
        client = MagicMock()
        with patch(
            "backend.rag.importar_exercicios_posicionais.iterar_jogos_broadcast",
            return_value=iter([carregar_jogo()]),
        ):
            resumo = importar(client, MagicMock(), meses=["2022-11"], teto_por_categoria=0)

        self.assertEqual(resumo["exercicios_importados"], 0)
        client.table.return_value.upsert.assert_not_called()

    def test_le_o_mes_inteiro_em_vez_de_parar_no_teto(self) -> None:
        """Parar cedo foi o que enviesou a primeira importação para os
        primeiros dias do mês. Agora o reservatório vê tudo."""
        client = MagicMock()
        jogos = [carregar_jogo() for _ in range(5)]
        with patch(
            "backend.rag.importar_exercicios_posicionais.iterar_jogos_broadcast",
            return_value=iter(jogos),
        ):
            resumo = importar(client, MagicMock(), meses=["2022-11"], teto_por_categoria=1)

        self.assertEqual(resumo["partidas_lidas"], 5)


class ReservatorioTest(unittest.TestCase):
    """Amostragem por reservatório (D-58).

    A primeira importação do D-55 aceitava os primeiros N e parava de ler: os
    1200 exercícios saíram quase todos do mesmo dia, de meia dúzia de torneios.
    Aumentar o teto não resolveria — o viés estava em onde a leitura parava.
    """

    def _registro(self, i: int) -> dict[str, int]:
        return {"id": i}

    def test_guarda_tudo_enquanto_cabe(self) -> None:
        reservatorio = ReservatorioPorCategoria(3)
        for i in range(3):
            reservatorio.oferecer("ESTRATEGIA", self._registro(i))

        self.assertEqual(reservatorio.contagem(), {"ESTRATEGIA": 3})
        self.assertEqual(len(reservatorio.coletar()), 3)

    def test_nunca_passa_do_teto(self) -> None:
        reservatorio = ReservatorioPorCategoria(5)
        for i in range(500):
            reservatorio.oferecer("ESTRATEGIA", self._registro(i))

        self.assertEqual(reservatorio.contagem(), {"ESTRATEGIA": 5})

    def test_amostra_o_stream_inteiro_e_nao_so_o_comeco(self) -> None:
        """O teste que importa: com 5 vagas e 1000 candidatos, a amostra tem
        que alcançar o fim do arquivo, não só os primeiros itens."""
        vindos_do_fim = 0
        for _ in range(40):
            reservatorio = ReservatorioPorCategoria(5)
            for i in range(1000):
                reservatorio.oferecer("ESTRATEGIA", self._registro(i))
            if any(item["id"] > 500 for item in reservatorio.coletar()):
                vindos_do_fim += 1

        # Com amostragem uniforme, a chance de NENHUM dos 5 vir da segunda
        # metade é (1/2)^5 ≈ 3%; em 40 rodadas, exigir 30 é folgado.
        self.assertGreater(vindos_do_fim, 30)

    def test_separa_as_categorias(self) -> None:
        reservatorio = ReservatorioPorCategoria(2)
        for i in range(10):
            reservatorio.oferecer("ESTRATEGIA", self._registro(i))
        for i in range(10):
            reservatorio.oferecer("FINAIS", self._registro(i))

        self.assertEqual(reservatorio.contagem(), {"ESTRATEGIA": 2, "FINAIS": 2})

    def test_teto_zero_nao_guarda_nada(self) -> None:
        reservatorio = ReservatorioPorCategoria(0)
        reservatorio.oferecer("ESTRATEGIA", self._registro(1))

        self.assertEqual(reservatorio.coletar(), [])


class MesesPadraoTest(unittest.TestCase):
    def test_usa_o_ultimo_mes_completo(self) -> None:
        """Calculado, e não fixado numa constante: uma data escrita à mão no
        default envelhece em silêncio e baixa sempre o mesmo mês antigo."""
        self.assertEqual(meses_padrao(date(2026, 9, 16)), ["2026-08"])

    def test_vira_o_ano_em_janeiro(self) -> None:
        self.assertEqual(meses_padrao(date(2026, 1, 5)), ["2025-12"])


if __name__ == "__main__":
    unittest.main()
