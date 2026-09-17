"""Testes unitários do loop multi-perfil de coletar_partidas.py (D-28) e da
extração de cadência da resposta do Lichess (D-62)."""

import unittest
from unittest.mock import MagicMock, patch

from backend.ingestao.coletar_partidas import (
    PARAMETROS_PARTIDA,
    Settings,
    build_pgn,
    coletar_para_perfil,
    time_control_da_partida,
    to_record,
)


# Recorte fiel de uma resposta real da API do Lichess, conferida em 17/09/2026
# com `pgnInJson/tags/clocks` ligados (AGENTS.md §2.3: confirmar o formato antes
# de escrever o parser). O que importa aqui é a coexistência do header
# `TimeControl` no PGN com o campo estruturado `clock` no NDJSON.
PGN_REAL = """[Event "rated rapid game"]
[Site "https://lichess.org/ASjC5hjq"]
[Date "2026.09.12"]
[White "dan_merzon"]
[Black "tantofaz123"]
[Result "1-0"]
[WhiteElo "1892"]
[BlackElo "1924"]
[TimeControl "600+0"]
[ECO "C01"]
[Termination "Time forfeit"]

1. e4 { [%clk 0:10:00] } 1... e6 { [%clk 0:10:00] } 1-0"""


class ColetarParaPerfilTest(unittest.TestCase):
    def _settings(self) -> Settings:
        return Settings(
            supabase_url="https://x.supabase.co",
            supabase_service_role_key="chave",
            lichess_token="token",
            limit=20,
        )

    @patch("backend.ingestao.coletar_partidas.insert_game")
    @patch("backend.ingestao.coletar_partidas.already_exists", return_value=False)
    @patch("backend.ingestao.coletar_partidas.fetch_games")
    def test_grava_com_o_user_id_do_perfil(
        self, fetch_mock, already_exists_mock, insert_mock
    ) -> None:
        fetch_mock.return_value = [
            {
                "id": "jogo-1",
                "players": {"white": {"user": {"name": "laisxadrez"}}, "black": {}},
                "winner": "white",
                "moves": "e4 e5",
            }
        ]
        client = MagicMock()
        logger = MagicMock()
        settings = self._settings()

        inserted, existing, failed = coletar_para_perfil(
            client, settings, logger, "user-lais", "laisxadrez"
        )

        self.assertEqual((inserted, existing, failed), (1, 0, 0))
        fetch_mock.assert_called_once_with(settings, logger, "laisxadrez")
        insert_mock.assert_called_once()
        _record_arg, user_id_arg = insert_mock.call_args[0][1:]
        self.assertEqual(user_id_arg, "user-lais")

    @patch("backend.ingestao.coletar_partidas.insert_game")
    @patch("backend.ingestao.coletar_partidas.already_exists", return_value=False)
    @patch("backend.ingestao.coletar_partidas.fetch_games")
    def test_uma_partida_com_falha_nao_impede_as_demais(
        self, fetch_mock, already_exists_mock, insert_mock
    ) -> None:
        fetch_mock.return_value = [
            {},  # sem "id" -> game["id"] explode antes de chegar em to_record
            {
                "id": "jogo-2",
                "players": {"white": {"user": {"name": "laisxadrez"}}, "black": {}},
                "winner": "white",
                "moves": "e4 e5",
            },
        ]
        client = MagicMock()

        inserted, existing, failed = coletar_para_perfil(
            client, self._settings(), MagicMock(), "user-lais", "laisxadrez"
        )

        self.assertEqual((inserted, existing, failed), (1, 0, 1))


class CadenciaDaColetaTest(unittest.TestCase):
    """D-62 — o Lichess parou de perder TimeControl e relógio na ingestão."""

    def _jogo(self, **extra):
        base = {
            "id": "ASjC5hjq",
            "players": {
                "white": {"user": {"name": "dan_merzon"}, "rating": 1892},
                "black": {"user": {"name": "tantofaz123"}, "rating": 1924},
            },
            "winner": "white",
            "moves": "e4 e6",
            "clock": {"initial": 600, "increment": 0, "totalTime": 600},
            "pgn": PGN_REAL,
        }
        base.update(extra)
        return base

    def test_pede_pgn_tags_e_relogio_na_api(self) -> None:
        # O defeito original não estava no parser e sim no pedido: sem estes
        # parâmetros o NDJSON vem sem `pgn` e sem header nenhum.
        self.assertEqual(PARAMETROS_PARTIDA["pgnInJson"], "true")
        self.assertEqual(PARAMETROS_PARTIDA["tags"], "true")
        self.assertEqual(PARAMETROS_PARTIDA["clocks"], "true")

    def test_usa_o_pgn_oficial_quando_ele_vem(self) -> None:
        pgn = build_pgn(self._jogo())
        self.assertIn('[TimeControl "600+0"]', pgn)
        self.assertIn("[%clk 0:10:00]", pgn)

    def test_grava_cadencia_a_partir_do_time_control(self) -> None:
        registro = to_record(self._jogo(), "tantofaz123")
        # 600 + 40*0 = 600s, acima do corte de blitz (479) — partida rápida.
        self.assertEqual(registro["cadencia"], "RAPIDA")
        self.assertEqual(registro["tempo_base_segundos"], 600)
        self.assertEqual(registro["incremento_segundos"], 0)

    def test_campo_clock_e_a_reserva_quando_o_pgn_nao_traz_header(self) -> None:
        # Se o PGN vier sem TimeControl, o NDJSON ainda tem o relógio
        # estruturado. Antes do D-62 os dois eram ignorados.
        sem_header = "\n".join(
            linha for linha in PGN_REAL.splitlines() if "TimeControl" not in linha
        )
        self.assertEqual(
            time_control_da_partida(self._jogo(pgn=sem_header), sem_header), "600+0"
        )

    def test_o_pgn_vence_o_clock_quando_os_dois_existem(self) -> None:
        # Uma verdade só por partida: as colunas têm que concordar com o PGN
        # gravado, senão rodar backfill_cadencia.py depois daria outra resposta.
        jogo = self._jogo(clock={"initial": 60, "increment": 0, "totalTime": 60})
        self.assertEqual(time_control_da_partida(jogo, PGN_REAL), "600+0")
        self.assertEqual(to_record(jogo, "tantofaz123")["cadencia"], "RAPIDA")

    def test_sem_relogio_nenhum_admite_desconhecida_em_vez_de_chutar(self) -> None:
        jogo = self._jogo(pgn="", clock=None)
        registro = to_record(jogo, "tantofaz123")
        self.assertEqual(registro["cadencia"], "DESCONHECIDA")
        self.assertIsNone(registro["tempo_base_segundos"])

    def test_correspondencia_nao_vira_cadencia_de_relogio(self) -> None:
        # `days` em vez de `clock`: sem base comparável, e chutar aqui poluiria
        # a estatística de cadência que a coluna existe para limpar.
        jogo = self._jogo(pgn="", clock=None, daysPerTurn=1)
        self.assertIsNone(time_control_da_partida(jogo, None))


if __name__ == "__main__":
    unittest.main()
