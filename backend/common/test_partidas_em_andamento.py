"""Testes da leitura de partidas em andamento no Lichess e no Chess.com (D-69)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import chess

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.common import partidas_em_andamento as modulo  # noqa: E402
from backend.common.partidas_em_andamento import (  # noqa: E402
    CacheDeEstado,
    PartidaEmAndamento,
    PlataformaIndisponivelError,
    completar_lances,
    estado_lichess,
    listar_chesscom,
    listar_lichess,
)

LANCES = "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6 O-O O-O".split()


def fen_apos(lances: list[str]) -> str:
    board = chess.Board()
    for lance in lances:
        board.push_san(lance)
    return board.fen()


def ultimo_uci(lances: list[str]) -> str:
    board = chess.Board()
    for lance in lances:
        board.push_san(lance)
    return board.peek().uci()


def resposta(status: int, corpo: dict | None = None) -> MagicMock:
    falsa = MagicMock()
    falsa.status_code = status
    falsa.json.return_value = corpo or {}
    return falsa


class CompletarLancesTest(unittest.TestCase):
    def test_historico_ja_em_dia_volta_igual(self) -> None:
        self.assertEqual(completar_lances(None, LANCES, fen_apos(LANCES)), LANCES)

    def test_reconstroi_os_lances_que_o_atraso_escondeu(self) -> None:
        """O Lichess atrasa em 3 lances os endpoints públicos de partida em andamento."""
        achado = completar_lances(None, LANCES[:-3], fen_apos(LANCES), ultimo_uci(LANCES))
        self.assertEqual(achado, LANCES)

    def test_ultimo_lance_conhecido_e_respeitado(self) -> None:
        # Com o último lance errado, não existe caminho.
        self.assertIsNone(completar_lances(None, LANCES[:-2], fen_apos(LANCES), "a2a3"))

    def test_posicao_inalcancavel_devolve_none(self) -> None:
        self.assertIsNone(completar_lances(None, ["e4"], fen_apos(["d4", "d5", "c4"])))

    def test_historico_ilegivel_devolve_none(self) -> None:
        self.assertIsNone(completar_lances(None, ["Qxh8"], chess.STARTING_FEN))

    def test_teto_de_nos_vira_historico_incompleto_e_nao_espera(self) -> None:
        with patch.object(modulo, "MAX_NOS_BUSCA", 1):
            self.assertIsNone(completar_lances(None, LANCES[:-4], fen_apos(LANCES)))

    def test_parte_de_posicao_propria(self) -> None:
        inicial = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
        board = chess.Board(inicial)
        board.push_san("e4")
        board.push_san("Kd7")
        self.assertEqual(completar_lances(inicial, [], board.fen()), ["e4", "Kd7"])


class ListarLichessTest(unittest.TestCase):
    ITEM = {
        "gameId": "abcd1234",
        "fullId": "abcd1234SEGR",
        "color": "black",
        "fen": fen_apos(["e4"]),
        "isMyTurn": True,
        "lastMove": "e2e4",
        "opponent": {"id": "professor", "username": "Professor", "rating": 1900},
        "rated": False,
        "speed": "rapid",
        "variant": {"key": "standard"},
    }

    def test_mapeia_partida_contra_humano_sem_expor_o_full_id(self) -> None:
        with patch.object(modulo.requests, "get", return_value=resposta(200, {"nowPlaying": [self.ITEM]})) as get:
            partidas = listar_lichess("token")

        (partida,) = partidas
        self.assertEqual(partida.game_id, "abcd1234")
        self.assertEqual(partida.cor, "PRETAS")
        self.assertTrue(partida.vez_do_jogador)
        self.assertEqual(partida.adversario, "Professor (1900)")
        self.assertEqual(partida.ultimo_lance_uci, "e2e4")
        self.assertNotIn("abcd1234SEGR", repr(partida))
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer token")

    def test_adversario_bot_do_lichess(self) -> None:
        item = {**self.ITEM, "opponent": {"ai": 5}}
        with patch.object(modulo.requests, "get", return_value=resposta(200, {"nowPlaying": [item]})):
            self.assertEqual(listar_lichess("t")[0].adversario, "Stockfish nível 5")

    def test_variantes_que_mudam_as_regras_ficam_de_fora(self) -> None:
        item = {**self.ITEM, "variant": {"key": "crazyhouse"}}
        with patch.object(modulo.requests, "get", return_value=resposta(200, {"nowPlaying": [item]})):
            self.assertEqual(listar_lichess("t"), [])

    def test_token_recusado_pede_para_reconectar(self) -> None:
        with patch.object(modulo.requests, "get", return_value=resposta(401)):
            with self.assertRaises(PlataformaIndisponivelError) as contexto:
                listar_lichess("t")
        self.assertIn("Reconecte", str(contexto.exception))

    def test_limite_de_requisicoes_vira_erro_legivel(self) -> None:
        with patch.object(modulo.requests, "get", return_value=resposta(429)):
            with self.assertRaises(PlataformaIndisponivelError) as contexto:
                listar_lichess("t")
        self.assertIn("um minuto", str(contexto.exception))

    def test_fen_sem_vez_e_completada_pela_cor(self) -> None:
        item = {**self.ITEM, "fen": fen_apos(["e4"]).split()[0]}
        with patch.object(modulo.requests, "get", return_value=resposta(200, {"nowPlaying": [item]})):
            self.assertEqual(listar_lichess("t")[0].fen.split()[1], "b")


class EstadoLichessTest(unittest.TestCase):
    def _partida_atual(self, lances: list[str]) -> PartidaEmAndamento:
        return PartidaEmAndamento(
            plataforma="LICHESS", game_id="g1", cor="BRANCAS", fen=fen_apos(lances),
            vez_do_jogador=True, adversario="x", ranqueada=False, ritmo="rapid",
            ultimo_lance_uci=ultimo_uci(lances),
        )

    def test_com_estado_conhecido_nem_pede_o_export(self) -> None:
        conhecido = self._partida_atual(LANCES[:-2])
        conhecido.lances = LANCES[:-2]
        with patch.object(modulo, "listar_lichess", return_value=[self._partida_atual(LANCES)]), \
                patch.object(modulo, "historico_lichess") as export:
            estado = estado_lichess("t", "g1", conhecido)
        export.assert_not_called()
        self.assertEqual(estado.lances, LANCES)
        self.assertTrue(estado.historico_completo)

    def test_sem_conhecido_usa_o_export_atrasado_e_completa(self) -> None:
        with patch.object(modulo, "listar_lichess", return_value=[self._partida_atual(LANCES)]), \
                patch.object(modulo, "historico_lichess", return_value=(None, LANCES[:-3])):
            estado = estado_lichess("t", "g1")
        self.assertEqual(estado.lances, LANCES)

    def test_sem_caminho_marca_historico_incompleto_mas_mantem_a_posicao(self) -> None:
        atual = self._partida_atual(LANCES)
        with patch.object(modulo, "listar_lichess", return_value=[atual]), \
                patch.object(modulo, "historico_lichess", return_value=(None, ["d4"])):
            estado = estado_lichess("t", "g1")
        self.assertFalse(estado.historico_completo)
        self.assertEqual(estado.fen, atual.fen)

    def test_partida_que_nao_esta_mais_em_andamento(self) -> None:
        with patch.object(modulo, "listar_lichess", return_value=[]):
            self.assertIsNone(estado_lichess("t", "g1"))


class ListarChesscomTest(unittest.TestCase):
    def _jogo(self, **extras):
        jogo = {
            "url": "https://www.chess.com/game/daily/123456",
            "fen": fen_apos(["e4", "e5"]),
            "pgn": '[Event "Daily"]\n\n1. e4 e5 *',
            "turn": "white",
            "white": "https://api.chess.com/pub/player/Edinho230",
            "black": "https://api.chess.com/pub/player/aluno_do_clube",
            "rated": True,
            "rules": "chess",
            "time_class": "daily",
        }
        jogo.update(extras)
        return jogo

    def test_mapeia_partida_diaria(self) -> None:
        with patch.object(modulo.requests, "get", return_value=resposta(200, {"games": [self._jogo()]})):
            (partida,) = listar_chesscom("edinho230")
        self.assertEqual(partida.game_id, "123456")
        self.assertEqual(partida.cor, "BRANCAS")
        self.assertTrue(partida.vez_do_jogador)
        self.assertEqual(partida.adversario, "aluno_do_clube")
        self.assertEqual(partida.lances, ["e4", "e5"])
        self.assertEqual(partida.url, "https://www.chess.com/game/daily/123456")

    def test_chess960_fica_de_fora(self) -> None:
        with patch.object(modulo.requests, "get", return_value=resposta(200, {"games": [self._jogo(rules="chess960")]})):
            self.assertEqual(listar_chesscom("edinho230"), [])

    def test_usuario_inexistente_nao_e_erro(self) -> None:
        with patch.object(modulo.requests, "get", return_value=resposta(404)):
            self.assertEqual(listar_chesscom("ninguem"), [])


class CacheDeEstadoTest(unittest.TestCase):
    def test_recente_expira_mas_ultimo_continua_disponivel(self) -> None:
        cache = CacheDeEstado(validade_segundos=10)
        chave = ("u", "LICHESS", "g1")
        cache.guardar(chave, "estado")  # type: ignore[arg-type]
        self.assertEqual(cache.recente(chave), (True, "estado"))

        with patch.object(modulo.time, "monotonic", return_value=modulo.time.monotonic() + 60):
            self.assertEqual(cache.recente(chave), (False, None))
        self.assertEqual(cache.ultimo(chave), "estado")

    def test_tamanho_maximo_descarta_o_mais_antigo(self) -> None:
        cache = CacheDeEstado(maximo=2)
        cache.guardar(("u", "L", "1"), None)
        cache.guardar(("u", "L", "2"), None)
        cache.guardar(("u", "L", "3"), None)
        self.assertEqual(len(cache._itens), 2)
        self.assertNotIn(("u", "L", "1"), cache._itens)


if __name__ == "__main__":
    unittest.main()
