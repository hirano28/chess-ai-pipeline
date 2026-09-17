"""Testes unitários do processamento de livros para o RAG."""

import unittest
from pathlib import Path
from unittest.mock import patch

from backend.rag.processar_livro import (
    Chunk,
    detect_chapter,
    filtrar_chunks_indexaveis,
    is_indice_chapter,
    numbered_chapter_number,
    ocr_cache_path,
    parse_args,
    split_words_with_overlap,
)


class TestDetectChapter(unittest.TestCase):
    """Testes para a detecção de capítulos em português e inglês."""

    def test_capitulo_portugues(self) -> None:
        self.assertEqual(
            detect_chapter("CAPÍTULO 1 - O CENTRO"),
            "CAPÍTULO 1 - O CENTRO",
        )
        self.assertEqual(
            detect_chapter("Parte II - Elementos Posicionais"),
            "Parte II - Elementos Posicionais",
        )

    def test_chapter_ingles(self) -> None:
        self.assertEqual(
            detect_chapter("CHAPTER 1 - FORCING MOVES"),
            "CHAPTER 1 - FORCING MOVES",
        )
        self.assertEqual(
            detect_chapter("Part 3 - Calculation Trees"),
            "Part 3 - Calculation Trees",
        )
        self.assertEqual(
            detect_chapter("SECTION IV: PROPHYLAXIS"),
            "SECTION IV: PROPHYLAXIS",
        )

    def test_capitulo_numerado(self) -> None:
        self.assertEqual(
            detect_chapter("1 - Os Lances Candidatos", allow_numbered=True),
            "1 - Os Lances Candidatos",
        )
        self.assertEqual(
            detect_chapter("12. Tactical Combinations", allow_numbered=True),
            "12. Tactical Combinations",
        )
        self.assertEqual(numbered_chapter_number("1 - Os Lances"), 1)
        self.assertEqual(numbered_chapter_number("12. Tactical"), 12)

    def test_linhas_invalidas_nao_sao_capitulos(self) -> None:
        self.assertIsNone(detect_chapter(""))
        self.assertIsNone(detect_chapter("lance normal e4 e5 sem capítulo"))
        self.assertIsNone(detect_chapter("Capítulo com vírgula, no meio da frase"))

    def test_cabecalho_repetido_com_numero_de_pagina_nao_e_capitulo(self) -> None:
        """Achado processando 'How to Calculate Chess Tactics' (D-72): o
        cabeçalho de página "PART 1: TACTICS IN CHESS 19" bate no padrão de
        capítulo e muda de linha a cada página (o número no fim), então o
        dedup de cabeçalho repetido (que exige texto idêntico) não pegava —
        virava um "capítulo" novo por página."""
        self.assertIsNone(detect_chapter("PART 1: TACTICS IN CHESS 19"))
        self.assertIsNone(detect_chapter("PART 2: THE TECHNIQUE OF CALCULATING VARIATIONS 59"))
        # Mas um título legítimo terminado no próprio número/romano do
        # padrão, sem sufixo nenhum, continua válido.
        self.assertEqual(detect_chapter("SECTION IV"), "SECTION IV")
        self.assertEqual(detect_chapter("PART 3"), "PART 3")


class TestSplitWordsWithOverlap(unittest.TestCase):
    """Testes para a divisão de texto em chunks com sobreposição."""

    def test_lista_vazia(self) -> None:
        self.assertEqual(split_words_with_overlap([], "Capítulo 1"), [])

    def test_texto_curto_gera_um_chunk(self) -> None:
        words = [("palavra", 1)] * 50
        chunks = split_words_with_overlap(words, "Capítulo 1")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].capitulo, "Capítulo 1")
        self.assertEqual(chunks[0].pagina_aprox, 1)

    def test_texto_longo_gera_multiplos_chunks_com_overlap(self) -> None:
        words = [(f"palavra{i}.", 1 + i // 100) for i in range(1200)]
        chunks = split_words_with_overlap(words, "Capítulo 2")
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertEqual(chunk.capitulo, "Capítulo 2")
            self.assertGreater(len(chunk.conteudo), 0)


class TestFiltrarChunksIndexaveis(unittest.TestCase):
    """Testes para exclusão de seções de índice."""

    def test_is_indice_chapter(self) -> None:
        self.assertTrue(is_indice_chapter("Índice de Capítulos"))
        self.assertTrue(is_indice_chapter("Table of Contents"))
        self.assertTrue(is_indice_chapter("Index of Players"))
        self.assertFalse(is_indice_chapter("Chapter 1 - Tactical Methods"))
        self.assertFalse(is_indice_chapter(None))

    def test_filtrar_chunks_remove_indices(self) -> None:
        chunks = [
            Chunk(conteudo="Índice do livro...", capitulo="Table of Contents", pagina_aprox=2),
            Chunk(conteudo="Conteúdo tático rico...", capitulo="Chapter 1", pagina_aprox=10),
            Chunk(conteudo="Índice de jogadores...", capitulo="Index of Players", pagina_aprox=175),
        ]
        filtrados = filtrar_chunks_indexaveis(chunks)
        self.assertEqual(len(filtrados), 1)
        self.assertEqual(filtrados[0].capitulo, "Chapter 1")


class TestOcrCachePath(unittest.TestCase):
    """Testes para geração do caminho de cache com separação por idioma."""

    def test_cache_path_inclui_idioma(self) -> None:
        pdf = Path("backend/rag/livros_pdf/livro_teste.pdf")
        path_por = ocr_cache_path(pdf, "por")
        path_eng = ocr_cache_path(pdf, "eng")
        self.assertIn("por", path_por.name)
        self.assertIn("eng", path_eng.name)
        self.assertNotEqual(path_por, path_eng)


class TestParseArgs(unittest.TestCase):
    """Testes para interpretação de argumentos de linha de comando."""

    def test_args_padrao(self) -> None:
        with patch("sys.argv", ["processar_livro.py", "--pdf", "teste.pdf", "--nome", "Livro Teste"]):
            args = parse_args()
            self.assertEqual(args.ocr_lang, "por")
            self.assertFalse(args.forcar_ocr)
            self.assertFalse(args.preview)

    def test_args_com_idioma_ingles(self) -> None:
        with patch(
            "sys.argv",
            ["processar_livro.py", "--pdf", "teste.pdf", "--nome", "Livro", "--ocr-lang", "eng", "--preview"],
        ):
            args = parse_args()
            self.assertEqual(args.ocr_lang, "eng")
            self.assertTrue(args.preview)


if __name__ == "__main__":
    unittest.main()

