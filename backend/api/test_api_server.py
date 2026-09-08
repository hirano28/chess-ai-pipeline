"""Testes do gate de autenticação (X-API-Key) do servidor da API.

Não aciona o startup real (Stockfish/Gemini/Supabase): a TestClient só
dispara os eventos de lifespan dentro de um bloco `with`, então chamamos as
rotas sem entrar nesse bloco e populamos `_state["api_secret_key"]`
manualmente, garantindo que nenhuma credencial real é necessária.
"""

import unittest

from fastapi.testclient import TestClient

from backend.api import api_server

CHAVE_CORRETA = "chave-secreta-de-teste"


class ApiKeyAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        api_server._state.clear()
        api_server._state["api_secret_key"] = CHAVE_CORRETA
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_sem_header_recebe_401(self) -> None:
        resposta = self.client.post(
            "/revisar-avulso",
            json={"posicao": "8/8/8/8/8/8/8/8 w - - 0 1", "lance": "e4", "pensamento": "x"},
        )

        self.assertEqual(resposta.status_code, 401)

    def test_header_com_chave_errada_recebe_401(self) -> None:
        resposta = self.client.post(
            "/revisar-avulso",
            json={"posicao": "8/8/8/8/8/8/8/8 w - - 0 1", "lance": "e4", "pensamento": "x"},
            headers={"X-API-Key": "chave-errada"},
        )

        self.assertEqual(resposta.status_code, 401)

    def test_401_nao_executa_logica_de_negocio(self) -> None:
        # Sem "engine"/"gemini_client"/"supabase_client" em _state, qualquer
        # tentativa de uso lançaria KeyError em vez de retornar 401 limpo.
        # Se este teste passar com 401, a rota nunca chegou a tocar nisso.
        resposta = self.client.post(
            "/revisar-avulso",
            json={"posicao": "8/8/8/8/8/8/8/8 w - - 0 1", "lance": "e4", "pensamento": "x"},
        )

        self.assertEqual(resposta.status_code, 401)
        self.assertNotIn("engine", api_server._state)
        self.assertNotIn("gemini_client", api_server._state)
        self.assertNotIn("supabase_client", api_server._state)

    def test_endpoint_salvar_tambem_exige_chave(self) -> None:
        resposta = self.client.post(
            "/revisar-avulso/salvar",
            json={
                "lance_jogado": "e4",
                "melhor_lance": "e4",
                "queda_win_percent": 0.0,
                "qualidade_lance": "BOM",
                "qualidade_raciocinio": "SOLIDO",
                "feedback_texto": "ok",
                "analise_mestre": "ok",
                "fen": "8/8/8/8/8/8/8/8 w - - 0 1",
                "texto_pensamento": "x",
            },
        )

        self.assertEqual(resposta.status_code, 401)
        self.assertNotIn("supabase_client", api_server._state)

    def test_header_correto_passa_do_gate_de_autenticacao(self) -> None:
        # FEN/lance válidos passam pela resolução de posição; sem "engine" em
        # _state, a rota falha com 500 (KeyError) em vez de 401 - prova que o
        # gate de autenticação deixou a requisição passar.
        resposta = self.client.post(
            "/revisar-avulso",
            json={
                "posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "lance": "e4",
                "pensamento": "x",
            },
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        self.assertNotEqual(resposta.status_code, 401)


if __name__ == "__main__":
    unittest.main()
