"""Testes de backend/common/cadencia.py (D-57).

Funções puras, sem rede nem banco. O ponto sensível coberto aqui é a ausência
de fallback: uma partida sem `TimeControl` precisa sair como DESCONHECIDA, e
não como blitz — chutar contaminaria exatamente a estatística que a coluna de
cadência veio limpar.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.cadencia import (  # noqa: E402
    BLITZ,
    BULLET,
    CADENCIAS,
    CLASSICA,
    CORRESPONDENCIA,
    DESCONHECIDA,
    RAPIDA,
    ROTULOS_CADENCIA,
    campos_de_cadencia,
    classificar_cadencia,
    interpretar_time_control,
    time_control_do_pgn,
)


class InterpretarTimeControlTest(unittest.TestCase):
    def test_base_com_incremento(self) -> None:
        self.assertEqual(interpretar_time_control("180+2"), (180, 2))

    def test_base_sem_incremento(self) -> None:
        self.assertEqual(interpretar_time_control("300"), (300, 0))

    def test_ausente_nao_vira_default(self) -> None:
        """`parse_time_control` do backfill de tempos chuta 300s, e faz bem —
        lá o chute é melhor que não calcular nada. Aqui seria pior que admitir
        a ignorância."""
        self.assertEqual(interpretar_time_control(None), (None, None))
        self.assertEqual(interpretar_time_control(""), (None, None))
        self.assertEqual(interpretar_time_control("-"), (None, None))
        self.assertEqual(interpretar_time_control("?"), (None, None))

    def test_formato_invalido(self) -> None:
        self.assertEqual(interpretar_time_control("abacaxi"), (None, None))
        self.assertEqual(interpretar_time_control("-30"), (None, None))

    def test_correspondencia_nao_tem_base_comparavel(self) -> None:
        self.assertEqual(interpretar_time_control("1/86400"), (None, None))


class ClassificarCadenciaTest(unittest.TestCase):
    """Cortes do Lichess sobre `base + 40 * incremento`."""

    def test_bullet(self) -> None:
        self.assertEqual(classificar_cadencia("60"), BULLET)
        self.assertEqual(classificar_cadencia("120+1"), BULLET)

    def test_blitz(self) -> None:
        self.assertEqual(classificar_cadencia("180"), BLITZ)
        self.assertEqual(classificar_cadencia("300"), BLITZ)
        self.assertEqual(classificar_cadencia("180+2"), BLITZ)

    def test_rapida(self) -> None:
        self.assertEqual(classificar_cadencia("600"), RAPIDA)
        self.assertEqual(classificar_cadencia("900+10"), RAPIDA)

    def test_classica(self) -> None:
        self.assertEqual(classificar_cadencia("5400+30"), CLASSICA)
        self.assertEqual(classificar_cadencia("1800"), CLASSICA)

    def test_incremento_empurra_para_a_faixa_de_cima(self) -> None:
        """2+1 tem só 2 minutos de base, mas o incremento faz a partida durar
        como blitz — é por isso que a estimativa usa `base + 40 * inc`."""
        self.assertEqual(classificar_cadencia("120"), BULLET)
        self.assertEqual(classificar_cadencia("120+3"), BLITZ)

    def test_sem_header_e_desconhecida(self) -> None:
        self.assertEqual(classificar_cadencia(None), DESCONHECIDA)
        self.assertEqual(classificar_cadencia("-"), DESCONHECIDA)

    def test_correspondencia(self) -> None:
        self.assertEqual(classificar_cadencia("1/86400"), CORRESPONDENCIA)

    def test_todo_resultado_esta_no_vocabulario(self) -> None:
        for entrada in ("60", "300", "600", "5400+30", "1/86400", None, "lixo"):
            self.assertIn(classificar_cadencia(entrada), CADENCIAS)

    def test_todo_valor_tem_rotulo(self) -> None:
        self.assertEqual(set(ROTULOS_CADENCIA), set(CADENCIAS))


class CamposDeCadenciaTest(unittest.TestCase):
    def test_monta_as_tres_colunas(self) -> None:
        self.assertEqual(
            campos_de_cadencia("180+2"),
            {"cadencia": BLITZ, "tempo_base_segundos": 180, "incremento_segundos": 2},
        )

    def test_sem_header_grava_nulos_e_desconhecida(self) -> None:
        self.assertEqual(
            campos_de_cadencia(None),
            {
                "cadencia": DESCONHECIDA,
                "tempo_base_segundos": None,
                "incremento_segundos": None,
            },
        )


class TimeControlDoPgnTest(unittest.TestCase):
    PGN = (
        '[Event "Rated blitz game"]\n'
        '[Site "https://lichess.org/abc"]\n'
        '[TimeControl "180+2"]\n'
        '[Result "1-0"]\n'
        "\n"
        "1. e4 e5 2. Nf3 1-0\n"
    )

    def test_le_o_header(self) -> None:
        self.assertEqual(time_control_do_pgn(self.PGN), "180+2")

    def test_pgn_sem_o_header(self) -> None:
        pgn = self.PGN.replace('[TimeControl "180+2"]\n', "")
        self.assertIsNone(time_control_do_pgn(pgn))

    def test_pgn_vazio_ou_nulo(self) -> None:
        self.assertIsNone(time_control_do_pgn(None))
        self.assertIsNone(time_control_do_pgn(""))

    def test_nao_confunde_com_texto_dos_lances(self) -> None:
        """Para de ler ao sair dos cabeçalhos: um comentário no meio da
        partida não pode ser lido como header."""
        pgn = self.PGN.replace('[TimeControl "180+2"]\n', "") + '{[TimeControl "999"]}\n'
        self.assertIsNone(time_control_do_pgn(pgn))


if __name__ == "__main__":
    unittest.main()
