"""Testes das agregações de puzzles: cálculo puro e isolamento por usuário (D-30)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from backend.agentes.insights_puzzles import (
    calcular_estatisticas_gerais,
    calcular_estatisticas_temas,
    calcular_insights_puzzles,
    fetch_puzzle_atividade,
    gerar_diagnostico_gap,
)


def _puzzle(
    puzzle_id: str,
    acertou: bool = True,
    temas: list[str] | None = None,
    rating: int | None = 1800,
) -> dict:
    return {
        "puzzle_id": puzzle_id,
        "data": "2026-09-14T20:00:00Z",
        "acertou": acertou,
        "temas": temas or ["fork", "middlegame"],
        "rating_puzzle": rating,
    }


class CalcularEstatisticasGeraisTest(unittest.TestCase):
    def test_lista_vazia_retorna_valores_zerados(self) -> None:
        res = calcular_estatisticas_gerais([])
        self.assertEqual(res["total"], 0)
        self.assertEqual(res["acertos"], 0)
        self.assertEqual(res["erros"], 0)
        self.assertEqual(res["taxa_acerto_pct"], 0.0)
        self.assertIsNone(res["rating_medio"])
        self.assertIsNone(res["rating_min"])
        self.assertIsNone(res["rating_max"])

    def test_calcula_metricas_com_acertos_erros_e_ratings(self) -> None:
        puzzles = [
            _puzzle("p1", acertou=True, rating=1700),
            _puzzle("p2", acertou=True, rating=1800),
            _puzzle("p3", acertou=False, rating=1900),
            _puzzle("p4", acertou=True, rating=None),
        ]
        res = calcular_estatisticas_gerais(puzzles)
        self.assertEqual(res["total"], 4)
        self.assertEqual(res["acertos"], 3)
        self.assertEqual(res["erros"], 1)
        self.assertEqual(res["taxa_acerto_pct"], 75.0)
        # Ratings válidos: [1700, 1800, 1900] -> média 1800.0
        self.assertEqual(res["rating_medio"], 1800.0)
        self.assertEqual(res["rating_min"], 1700)
        self.assertEqual(res["rating_max"], 1900)


class CalcularEstatisticasTemasTest(unittest.TestCase):
    def test_agrupa_por_tema_e_aplica_min_amostra(self) -> None:
        # Cria 5 puzzles com "defensiveMove" (2 acertos, 3 erros = 40%)
        puzzles = [_puzzle(f"d{i}", acertou=(i < 2), temas=["defensiveMove"]) for i in range(5)]
        # Cria 5 puzzles com "mateIn1" (5 acertos = 100%)
        puzzles.extend([_puzzle(f"m{i}", acertou=True, temas=["mateIn1"]) for i in range(5)])
        # Cria 2 puzzles com "fork" (abaixo do min_amostra=5)
        puzzles.extend([_puzzle(f"f{i}", acertou=True, temas=["fork"]) for i in range(2)])

        vulneraveis, dominados, todos = calcular_estatisticas_temas(puzzles, min_amostra=5)

        # "fork" está em todos, mas não em vulneráveis/dominados
        slugs_todos = [t["slug"] for t in todos]
        self.assertIn("fork", slugs_todos)
        self.assertIn("defensiveMove", slugs_todos)
        self.assertIn("mateIn1", slugs_todos)

        # Vulneráveis deve ter defensiveMove (40.0%)
        self.assertEqual(len(vulneraveis), 2)  # defensiveMove e mateIn1 são os únicos com >= 5
        self.assertEqual(vulneraveis[0]["slug"], "defensiveMove")
        self.assertEqual(vulneraveis[0]["taxa_acerto_pct"], 40.0)
        self.assertEqual(vulneraveis[0]["nome"], "Lance Defensivo")
        self.assertEqual(vulneraveis[0]["url_treino"], "https://lichess.org/training/defensiveMove")

        # Dominados deve ter mateIn1 (100.0%) em primeiro
        self.assertEqual(dominados[0]["slug"], "mateIn1")
        self.assertEqual(dominados[0]["taxa_acerto_pct"], 100.0)
        self.assertEqual(dominados[0]["nome"], "Mate em 1 lance")

    def test_tema_desconhecido_usa_fallback_amigavel(self) -> None:
        puzzles = [_puzzle("p1", acertou=True, temas=["novoTemaExotico"])]
        _, _, todos = calcular_estatisticas_temas(puzzles, min_amostra=1)
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0]["slug"], "novoTemaExotico")
        self.assertEqual(todos[0]["nome"], "Novo Tema Exotico")
        self.assertEqual(todos[0]["categoria"], "geral")


class GerarDiagnosticoGapTest(unittest.TestCase):
    def test_sem_historico_retorna_orientacao_inicial(self) -> None:
        resumo = {"total": 0, "rating_medio": None}
        gap = gerar_diagnostico_gap(resumo, [], [])
        self.assertIn("Sem Histórico", gap["titulo"])
        self.assertIn("Ainda não há puzzles", gap["resumo_executivo"])

    def test_com_historico_sintetiza_vulnerabilidades_e_fortalezas(self) -> None:
        resumo = {"total": 100, "rating_medio": 1850.0}
        vulneraveis = [
            {"nome": "Lance Defensivo", "slug": "defensiveMove", "taxa_acerto_pct": 45.0}
        ]
        dominados = [
            {"nome": "Mate em 1 lance", "slug": "mateIn1", "taxa_acerto_pct": 95.0}
        ]
        gap = gerar_diagnostico_gap(resumo, vulneraveis, dominados)
        self.assertIn("Gap Tático", gap["titulo"])
        self.assertIn("1850", gap["resumo_executivo"])
        self.assertIn("lance defensivo", gap["resumo_executivo"].lower())
        self.assertIn("mate em 1 lance", gap["analise_comparativa"].lower())


class FetchPuzzleAtividadeDonoTest(unittest.TestCase):
    def test_fetch_puzzle_atividade_filtra_por_user_id(self) -> None:
        client = MagicMock()
        resp_vazia = MagicMock()
        resp_vazia.data = []

        no_select = client.table.return_value.select.return_value
        no_eq = no_select.eq.return_value
        no_eq.range.return_value.execute.return_value = resp_vazia

        fetch_puzzle_atividade(client, "user-teste-123")

        client.table.assert_called_once_with("puzzle_atividade")
        no_select.eq.assert_called_once_with("user_id", "user-teste-123")


class OrquestracaoInsightsPuzzlesTest(unittest.TestCase):
    def test_calcular_insights_puzzles_completo(self) -> None:
        client = MagicMock()
        resp = MagicMock()
        resp.data = [
            _puzzle("p1", acertou=True, temas=["mateIn1"], rating=1800),
            _puzzle("p2", acertou=False, temas=["defensiveMove"], rating=1900),
        ]
        no_select = client.table.return_value.select.return_value
        no_select.eq.return_value.range.return_value.execute.return_value = resp

        resultado = calcular_insights_puzzles(client, "user-teste-123")

        self.assertIn("resumo", resultado)
        self.assertIn("temas_vulneraveis", resultado)
        self.assertIn("temas_dominados", resultado)
        self.assertIn("todos_os_temas", resultado)
        self.assertIn("diagnostico_gap", resultado)
        self.assertEqual(resultado["resumo"]["total"], 2)


if __name__ == "__main__":
    unittest.main()

