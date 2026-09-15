"""Testes unitários para o importador de índice conceitual."""

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock

from backend.rag.importar_indice_conceitual import carregar_sugestoes, importar_indice


class TestImportarIndiceConceitual(TestCase):
    """Testa a leitura do arquivo JSON e a inserção de registros."""

    def test_carregar_sugestoes_valido(self) -> None:
        """Garante extração correta de conceitos e metadados."""
        tmp_dir = Path("backend/rag/sugestoes")
        tmp_file = tmp_dir / "teste_mock_livro.json"
        try:
            payload = {
                "livro": "Livro de Teste",
                "capitulos": [
                    {
                        "capitulo": "Capítulo 1",
                        "pagina_min": 10,
                        "pagina_max": 20,
                        "conceitos_sugeridos": [
                            {
                                "conceito": "fraqueza_estrutural_de_peoes",
                                "resumo_curto": "Peões isolados geram casas fracas.",
                            },
                            {
                                "conceito": "oposição",
                                "resumo_curto": "Manobra clássica de rei.",
                            },
                        ],
                    }
                ],
            }
            tmp_file.write_text(json.dumps(payload), encoding="utf-8")

            livro, registros = carregar_sugestoes(tmp_file)
            self.assertEqual(livro, "Livro de Teste")
            self.assertEqual(len(registros), 2)
            self.assertEqual(registros[0]["capitulo"], "Capítulo 1")
            self.assertEqual(registros[0]["pagina_aprox"], 10)
            self.assertEqual(registros[0]["conceito"], "fraqueza_estrutural_de_peoes")
            self.assertEqual(registros[1]["conceito"], "oposição")
        finally:
            if tmp_file.exists():
                tmp_file.unlink()

    def test_carregar_sugestoes_arquivo_inexistente(self) -> None:
        """Deve lançar FileNotFoundError para caminho inválido."""
        with self.assertRaises(FileNotFoundError):
            carregar_sugestoes(Path("caminho/que/nao/existe.json"))

    def test_importar_indice_chama_insert(self) -> None:
        """Valida que o cliente do Supabase recebe os registros corretos."""
        client = MagicMock()
        table_mock = MagicMock()
        client.table.return_value = table_mock

        registros = [
            {
                "livro": "Livro A",
                "capitulo": "Cap 1",
                "pagina_aprox": 5,
                "conceito": "tatica",
                "resumo_curto": "Resumo",
            }
        ]

        total = importar_indice(client, "Livro A", registros, substituir=False)
        self.assertEqual(total, 1)
        client.table.assert_called_with("indice_conceitual")
        table_mock.insert.assert_called_once_with(registros)

    def test_importar_indice_com_substituir(self) -> None:
        """Valida que delete é chamado antes da inserção quando substituir=True."""
        client = MagicMock()
        table_mock = MagicMock()
        delete_mock = MagicMock()
        eq_mock = MagicMock()

        client.table.return_value = table_mock
        table_mock.delete.return_value = delete_mock
        delete_mock.eq.return_value = eq_mock

        registros = [{"livro": "Livro B", "conceito": "estrategia"}]
        importar_indice(client, "Livro B", registros, substituir=True)

        table_mock.delete.assert_called_once()
        delete_mock.eq.assert_called_once_with("livro", "Livro B")
        table_mock.insert.assert_called_once_with(registros)

