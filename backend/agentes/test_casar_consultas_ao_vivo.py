"""Testes do casamento das consultas ao vivo com a partida real (D-68)."""

from __future__ import annotations

import logging
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import chess

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.agentes import casar_consultas_ao_vivo as modulo  # noqa: E402
from backend.agentes.casar_consultas_ao_vivo import (  # noqa: E402
    PosicaoNaPartida,
    adiantar_card,
    buscar_lance_critico,
    chave_posicao,
    desfecho,
    localizar_posicao,
    processar_consulta,
)

LOGGER = logging.getLogger("teste_casar")
LOGGER.addHandler(logging.NullHandler())
LOGGER.propagate = False

PGN = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d3 d6 *"


def fen_depois(lances: list[str]) -> str:
    board = chess.Board()
    for lance in lances:
        board.push_san(lance)
    return board.fen()


RESPOSTA = {"motor": {"candidatos": ["d4", "Bc4"], "melhor_lance": "d4"}}


class ChaveEPosicaoTest(unittest.TestCase):
    def test_chave_ignora_contadores_e_en_passant(self) -> None:
        a = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2")
        b = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 5 9")
        self.assertEqual(chave_posicao(a), chave_posicao(b))

    def test_acha_a_posicao_e_o_lance_seguinte(self) -> None:
        fen = fen_depois(["e4", "e5", "Nf3", "Nc6"])
        posicao = localizar_posicao(PGN, fen, "BRANCAS", 3)
        self.assertIsNotNone(posicao)
        self.assertEqual(posicao.board.san(posicao.lance_seguinte), "Bc4")

    def test_posicao_com_a_vez_do_adversario_nao_conta(self) -> None:
        fen = fen_depois(["e4", "e5", "Nf3"])
        self.assertIsNone(localizar_posicao(PGN, fen, "BRANCAS"))

    def test_posicao_que_nao_aparece_na_partida(self) -> None:
        fen = fen_depois(["d4", "d5"])
        self.assertIsNone(localizar_posicao(PGN, fen, "BRANCAS"))

    def test_partida_que_acabou_na_posicao_nao_tem_lance_seguinte(self) -> None:
        fen = fen_depois("e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6".split())
        posicao = localizar_posicao(PGN, fen, "BRANCAS")
        self.assertIsNotNone(posicao)
        self.assertIsNone(posicao.lance_seguinte)

    def test_repeticao_prefere_o_mesmo_numero_de_lance(self) -> None:
        pgn = "1. Nf3 Nf6 2. Ng1 Ng8 3. Nf3 Nf6 4. Ng1 Ng8 5. e4 *"
        inicial = chess.STARTING_FEN
        posicao = localizar_posicao(pgn, inicial, "BRANCAS", 3)
        self.assertEqual(posicao.board.fullmove_number, 3)
        self.assertEqual(posicao.board.san(posicao.lance_seguinte), "Nf3")

    def test_pgn_ilegivel_nao_quebra(self) -> None:
        self.assertIsNone(localizar_posicao("", chess.STARTING_FEN, "BRANCAS"))


class DesfechoTest(unittest.TestCase):
    def _posicao(self, lances: list[str], seguinte: str | None) -> PosicaoNaPartida:
        board = chess.Board(fen_depois(lances))
        move = board.parse_san(seguinte) if seguinte else None
        return PosicaoNaPartida(board, move)

    def test_mede_a_queda_e_compara_com_as_camadas(self) -> None:
        posicao = self._posicao(["e4", "e5", "Nf3", "Nc6"], "Bc4")
        with patch.object(modulo, "win_percent_na_posicao", side_effect=[55.0, 52.5]):
            campos = desfecho(MagicMock(), posicao, "BRANCAS", RESPOSTA)
        self.assertEqual(campos["lance_jogado"], "Bc4")
        self.assertEqual(campos["queda_win_percent_jogado"], 2.5)
        self.assertTrue(campos["lance_jogado_era_candidato"])
        self.assertFalse(campos["lance_jogado_era_o_melhor"])

    def test_lance_do_motor(self) -> None:
        posicao = self._posicao(["e4", "e5", "Nf3", "Nc6"], "d4")
        with patch.object(modulo, "win_percent_na_posicao", side_effect=[55.0, 56.0]):
            campos = desfecho(MagicMock(), posicao, "BRANCAS", RESPOSTA)
        self.assertTrue(campos["lance_jogado_era_o_melhor"])
        self.assertEqual(campos["queda_win_percent_jogado"], -1.0)

    def test_partida_acabou_ali_nao_chama_o_motor(self) -> None:
        posicao = self._posicao(["e4", "e5"], None)
        with patch.object(modulo, "win_percent_na_posicao") as motor:
            campos = desfecho(MagicMock(), posicao, "BRANCAS", RESPOSTA)
        motor.assert_not_called()
        self.assertIsNone(campos["lance_jogado"])


class LanceCriticoECardTest(unittest.TestCase):
    def _client_lances(self, linhas):
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = linhas
        return client

    def test_pico_no_mesmo_lance_vem_antes_da_erosao(self) -> None:
        client = self._client_lances([
            {"id": "ero", "tipo_evento": "EROSAO", "numero_lance": 10, "numero_lance_fim": 17},
            {"id": "pico", "tipo_evento": "PICO", "numero_lance": 12, "numero_lance_fim": None},
        ])
        self.assertEqual(buscar_lance_critico(client, "p", 12)["id"], "pico")

    def test_erosao_que_cobre_o_lance(self) -> None:
        client = self._client_lances([
            {"id": "ero", "tipo_evento": "EROSAO", "numero_lance": 10, "numero_lance_fim": 17},
        ])
        self.assertEqual(buscar_lance_critico(client, "p", 15)["id"], "ero")
        self.assertIsNone(buscar_lance_critico(client, "p", 18))

    def _client_fila(self, linhas):
        client = MagicMock()
        cadeia = client.table.return_value.select.return_value.eq.return_value.eq.return_value
        cadeia.execute.return_value.data = linhas
        return client

    def test_adianta_card_nunca_respondido_agendado_para_depois(self) -> None:
        client = self._client_fila([{"id": 9, "proxima_revisao_data": "2026-11-18", "total_revisoes": 0}])
        self.assertTrue(adiantar_card(client, "u", "l", date(2026, 9, 17)))
        (gravado,), _ = client.table.return_value.update.call_args
        self.assertEqual(gravado, {"proxima_revisao_data": "2026-09-17"})

    def test_nao_atropela_card_que_o_sm2_ja_agendou(self) -> None:
        client = self._client_fila([{"id": 9, "proxima_revisao_data": "2026-10-01", "total_revisoes": 2}])
        self.assertFalse(adiantar_card(client, "u", "l", date(2026, 9, 17)))
        client.table.return_value.update.assert_not_called()

    def test_card_ja_vencido_fica_como_esta(self) -> None:
        client = self._client_fila([{"id": 9, "proxima_revisao_data": "2026-09-10", "total_revisoes": 0}])
        self.assertFalse(adiantar_card(client, "u", "l", date(2026, 9, 17)))


class ProcessarConsultaTest(unittest.TestCase):
    AGORA = datetime(2026, 9, 17, 23, 0, tzinfo=timezone.utc)

    def _consulta(self, **extras):
        consulta = {
            "id": "c1",
            "user_id": "u1",
            "plataforma": "LICHESS",
            "cor_jogador": "BRANCAS",
            "fen": fen_depois(["e4", "e5", "Nf3", "Nc6"]),
            "numero_lance": 3,
            "criado_em": "2026-09-17T20:00:00+00:00",
            "partida_externa_id": None,
            "resposta": RESPOSTA,
        }
        consulta.update(extras)
        return consulta

    def test_casa_e_liga_ao_lance_critico(self) -> None:
        client = MagicMock()
        with patch.object(modulo, "buscar_partidas_candidatas", return_value=[
            {"id": "outra", "pgn": "1. d4 d5 *"},
            {"id": "p1", "pgn": PGN},
        ]), patch.object(modulo, "buscar_lance_critico", return_value={"id": "lc1"}), \
                patch.object(modulo, "adiantar_card", return_value=True) as adiantar, \
                patch.object(modulo, "win_percent_na_posicao", side_effect=[55.0, 40.0]):
            status = processar_consulta(client, MagicMock(), self._consulta(), self.AGORA, LOGGER)

        self.assertEqual(status, "casada")
        (gravado,), _ = client.table.return_value.update.call_args
        self.assertEqual(gravado["partida_id"], "p1")
        self.assertEqual(gravado["lance_critico_id"], "lc1")
        self.assertEqual(gravado["queda_win_percent_jogado"], 15.0)
        adiantar.assert_called_once_with(client, "u1", "lc1", date(2026, 9, 17))

    def test_sem_partida_ainda_fica_pendente(self) -> None:
        client = MagicMock()
        with patch.object(modulo, "buscar_partidas_candidatas", return_value=[]):
            status = processar_consulta(client, MagicMock(), self._consulta(), self.AGORA, LOGGER)
        self.assertEqual(status, "pendente")
        client.table.return_value.update.assert_not_called()

    def test_desiste_depois_de_tres_dias(self) -> None:
        client = MagicMock()
        antiga = (self.AGORA - timedelta(days=4)).isoformat()
        with patch.object(modulo, "buscar_partidas_candidatas", return_value=[]):
            status = processar_consulta(
                client, MagicMock(), self._consulta(criado_em=antiga), self.AGORA, LOGGER
            )
        self.assertEqual(status, "sem_partida")
        (gravado,), _ = client.table.return_value.update.call_args
        self.assertEqual(gravado, {"casamento_status": "sem_partida"})


class BuscarPartidasCandidatasTest(unittest.TestCase):
    def test_com_id_externo_busca_direto(self) -> None:
        client = MagicMock()
        base = client.table.return_value.select.return_value.eq.return_value.eq.return_value
        base.eq.return_value.execute.return_value.data = [{"id": "p1"}]
        consulta = {"user_id": "u", "cor_jogador": "BRANCAS", "partida_externa_id": "abcd1234"}

        self.assertEqual(modulo.buscar_partidas_candidatas(client, consulta), [{"id": "p1"}])
        base.eq.assert_called_once_with("external_id", "abcd1234")
        base.gte.assert_not_called()

    def test_sem_id_externo_usa_janela_e_plataforma(self) -> None:
        client = MagicMock()
        base = client.table.return_value.select.return_value.eq.return_value.eq.return_value
        janela = base.gte.return_value.lte.return_value
        janela.eq.return_value.execute.return_value.data = []
        consulta = {
            "user_id": "u",
            "cor_jogador": "BRANCAS",
            "partida_externa_id": None,
            "plataforma": "CHESSCOM",
            "criado_em": "2026-09-17T20:00:00+00:00",
        }

        modulo.buscar_partidas_candidatas(client, consulta)

        self.assertEqual(base.gte.call_args.args[1], "2026-09-16T20:00:00+00:00")
        self.assertEqual(janela.eq.call_args.args, ("plataforma", "CHESSCOM"))


if __name__ == "__main__":
    unittest.main()
