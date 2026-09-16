"""Testes de backend/rag/importar_exercicios_taticos.py.

Cobre só as funções puras (mapeamento tema->categoria, cálculo de FEN pós-
lance-de-preparo, filtros de qualidade, contagem de teto por categoria) e a
orquestração de `importar()` com um client Supabase mockado e um stream de
linhas fake - nenhum teste aqui chama a rede real do Lichess.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.rag.importar_exercicios_taticos import (  # noqa: E402
    categoria_ainda_aceita,
    categoria_do_tema,
    fen_apos_lance_preparo,
    importar,
    linha_atende_filtros,
    processar_linha,
    todas_categorias_completas,
)

FEN_POSICAO_INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class CategoriaDoTemaTest(unittest.TestCase):
    def test_devolve_categoria_do_primeiro_tema_mapeado(self) -> None:
        self.assertEqual(categoria_do_tema(["middlegame", "fork", "short"]), "TATICA")

    def test_ignora_temas_nao_mapeados_e_usa_o_proximo(self) -> None:
        self.assertEqual(categoria_do_tema(["opening", "mateIn2"]), "CALCULO")

    def test_devolve_none_quando_nenhum_tema_bate(self) -> None:
        self.assertIsNone(categoria_do_tema(["opening", "middlegame", "short"]))

    def test_lista_vazia_devolve_none(self) -> None:
        self.assertIsNone(categoria_do_tema([]))


class FenAposLancePreparoTest(unittest.TestCase):
    def test_aplica_o_lance_de_preparo_ao_fen_bruto(self) -> None:
        fen_resultado = fen_apos_lance_preparo(FEN_POSICAO_INICIAL, "e2e4")
        self.assertTrue(fen_resultado.startswith("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"))
        self.assertIn(" b ", fen_resultado)

    def test_lance_invalido_lanca_value_error(self) -> None:
        with self.assertRaises(ValueError):
            fen_apos_lance_preparo(FEN_POSICAO_INICIAL, "e2e5")

    def test_fen_invalido_lanca_value_error(self) -> None:
        with self.assertRaises(ValueError):
            fen_apos_lance_preparo("isso nao e um fen", "e2e4")


class LinhaAtendeFiltrosTest(unittest.TestCase):
    def test_dentro_da_faixa_passa(self) -> None:
        self.assertTrue(linha_atende_filtros(1500, 80, 1000, 2200, 50))

    def test_rating_abaixo_do_minimo_falha(self) -> None:
        self.assertFalse(linha_atende_filtros(900, 80, 1000, 2200, 50))

    def test_rating_acima_do_maximo_falha(self) -> None:
        self.assertFalse(linha_atende_filtros(2500, 80, 1000, 2200, 50))

    def test_popularidade_abaixo_do_minimo_falha(self) -> None:
        self.assertFalse(linha_atende_filtros(1500, 10, 1000, 2200, 50))

    def test_rating_nulo_falha(self) -> None:
        self.assertFalse(linha_atende_filtros(None, 80, 1000, 2200, 50))

    def test_popularidade_nula_falha(self) -> None:
        self.assertFalse(linha_atende_filtros(1500, None, 1000, 2200, 50))


class ProcessarLinhaTest(unittest.TestCase):
    def _linha_valida(self, **overrides: str) -> dict[str, str]:
        linha = {
            "PuzzleId": "00sHx",
            "FEN": FEN_POSICAO_INICIAL,
            "Moves": "e2e4 e7e5",
            "Rating": "1500",
            "Popularity": "80",
            "Themes": "opening fork short",
        }
        linha.update(overrides)
        return linha

    def test_linha_valida_gera_registro_completo(self) -> None:
        registro = processar_linha(self._linha_valida())
        assert registro is not None
        self.assertEqual(registro["puzzle_id_lichess"], "00sHx")
        self.assertEqual(registro["categoria_hexagono"], "TATICA")
        self.assertEqual(registro["temas_lichess"], ["opening", "fork", "short"])
        self.assertEqual(registro["rating"], 1500)
        self.assertEqual(registro["popularidade"], 80)
        self.assertIn(" b ", registro["fen"])

    def test_tema_nao_mapeado_pula_a_linha(self) -> None:
        self.assertIsNone(processar_linha(self._linha_valida(Themes="opening middlegame")))

    def test_fora_da_faixa_de_rating_pula_a_linha(self) -> None:
        self.assertIsNone(processar_linha(self._linha_valida(Rating="50")))

    def test_lance_de_preparo_invalido_pula_a_linha(self) -> None:
        self.assertIsNone(processar_linha(self._linha_valida(Moves="e2e5")))

    def test_rating_nao_numerico_pula_a_linha(self) -> None:
        self.assertIsNone(processar_linha(self._linha_valida(Rating="n/a")))

    def test_linha_sem_puzzle_id_pula_a_linha(self) -> None:
        self.assertIsNone(processar_linha(self._linha_valida(PuzzleId="")))


class TetoPorCategoriaTest(unittest.TestCase):
    def test_categoria_ainda_aceita_abaixo_do_teto(self) -> None:
        self.assertTrue(categoria_ainda_aceita({"TATICA": 2}, "TATICA", 3))

    def test_categoria_nao_aceita_no_teto(self) -> None:
        self.assertFalse(categoria_ainda_aceita({"TATICA": 3}, "TATICA", 3))

    def test_categoria_sem_entrada_ainda_aceita(self) -> None:
        self.assertTrue(categoria_ainda_aceita({}, "FINAIS", 3))

    def test_todas_completas_quando_todas_batem_o_teto(self) -> None:
        contador = {"TATICA": 3, "CALCULO": 3, "FINAIS": 3, "ESTRUTURA_DE_PEOES": 3}
        categorias = frozenset(contador.keys())
        self.assertTrue(todas_categorias_completas(contador, categorias, 3))

    def test_nao_completas_quando_falta_uma_categoria(self) -> None:
        contador = {"TATICA": 3, "CALCULO": 1}
        categorias = frozenset({"TATICA", "CALCULO"})
        self.assertFalse(todas_categorias_completas(contador, categorias, 3))


class ImportarTest(unittest.TestCase):
    def test_filtra_mapeia_e_faz_upsert_em_lote(self) -> None:
        linhas = [
            {
                "PuzzleId": "aaaaa",
                "FEN": FEN_POSICAO_INICIAL,
                "Moves": "e2e4 e7e5",
                "Rating": "1500",
                "Popularity": "80",
                "Themes": "fork short",
            },
            {
                "PuzzleId": "bbbbb",
                "FEN": FEN_POSICAO_INICIAL,
                "Moves": "e2e4 e7e5",
                "Rating": "1500",
                "Popularity": "80",
                "Themes": "opening middlegame",
            },
        ]
        client = MagicMock()
        logger = MagicMock()
        with patch(
            "backend.rag.importar_exercicios_taticos.iterar_linhas_dump", return_value=iter(linhas)
        ):
            resumo = importar(client, logger)

        self.assertEqual(resumo["linhas_lidas"], 2)
        self.assertEqual(resumo["exercicios_importados"], 1)
        self.assertEqual(resumo["linhas_puladas"], 1)
        self.assertEqual(resumo["TATICA"], 1)
        client.table.assert_called_with("exercicios_taticos")
        upsert_mock = client.table.return_value.upsert
        upsert_mock.assert_called_once()
        (lote,), kwargs = upsert_mock.call_args
        self.assertEqual(len(lote), 1)
        self.assertEqual(kwargs.get("on_conflict"), "puzzle_id_lichess")

    def test_para_de_ler_quando_todas_categorias_batem_o_teto(self) -> None:
        def gerar_linhas():
            for indice in range(10):
                yield {
                    "PuzzleId": f"puzzle{indice}",
                    "FEN": FEN_POSICAO_INICIAL,
                    "Moves": "e2e4 e7e5",
                    "Rating": "1500",
                    "Popularity": "80",
                    "Themes": "fork",
                }

        client = MagicMock()
        logger = MagicMock()
        with patch(
            "backend.rag.importar_exercicios_taticos.CATEGORIAS_APLICAVEIS",
            frozenset({"TATICA"}),
        ), patch(
            "backend.rag.importar_exercicios_taticos.iterar_linhas_dump",
            return_value=gerar_linhas(),
        ):
            resumo = importar(client, logger, teto_por_categoria=2)

        self.assertEqual(resumo["exercicios_importados"], 2)
        self.assertLess(resumo["linhas_lidas"], 10)


if __name__ == "__main__":
    unittest.main()
