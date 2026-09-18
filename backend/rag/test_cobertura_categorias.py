"""Testes unitários do relatório de cobertura por categoria."""

import unittest
from unittest.mock import patch

from backend.agentes.agente2_analista import HEXAGON_CATEGORIES
from backend.agentes.agente3_prescritor import CATEGORY_SEARCH_TERMS
from backend.rag.cobertura_categorias import parse_args


class InvariantesDeCategoriaTest(unittest.TestCase):
    """As 6 categorias do Hexágono devem sempre ter termo de busca definido.

    Achado desta sessão (D-79/D-80): duas categorias já ficaram travadas
    em contagem baixa por causa de termo de busca desalinhado com o
    conceito salvo, não por falta de dado real. Este teste não evita esse
    tipo de gap semântico, mas evita o caso mais grosseiro: uma categoria
    nova sem NENHUM termo, que `buscar_conceitos()` devolveria vazia
    silenciosamente.
    """

    def test_toda_categoria_do_hexagono_tem_termo_de_busca(self) -> None:
        sem_termo = [c for c in HEXAGON_CATEGORIES if c not in CATEGORY_SEARCH_TERMS]
        self.assertEqual(sem_termo, [])


class ParseArgsTest(unittest.TestCase):
    def test_default_sem_flag_livros(self) -> None:
        with patch("sys.argv", ["cobertura_categorias.py"]):
            args = parse_args()
            self.assertFalse(args.livros)

    def test_flag_livros(self) -> None:
        with patch("sys.argv", ["cobertura_categorias.py", "--livros"]):
            args = parse_args()
            self.assertTrue(args.livros)


if __name__ == "__main__":
    unittest.main()
