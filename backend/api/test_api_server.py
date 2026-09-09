"""Testes do gate de autenticação (X-API-Key) do servidor da API.

Não aciona o startup real (Stockfish/Gemini/Supabase): a TestClient só
dispara os eventos de lifespan dentro de um bloco `with`, então chamamos as
rotas sem entrar nesse bloco e populamos `_state["api_keys"]` manualmente,
garantindo que nenhuma credencial real é necessária.
"""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.api import api_server

CHAVE_CORRETA = "chave-secreta-de-teste"


class ApiKeyAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        api_server._state.clear()
        api_server._state["api_keys"] = {CHAVE_CORRETA: "teste"}
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

    def test_multiplas_chaves_validas_sao_aceitas(self) -> None:
        api_server._state["api_keys"] = {
            "chave-da-ana": "ana",
            "chave-do-bruno": "bruno",
        }
        payload = {
            "posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "lance": "e4",
            "pensamento": "x",
        }

        resposta_ana = self.client.post(
            "/revisar-avulso", json=payload, headers={"X-API-Key": "chave-da-ana"}
        )
        resposta_bruno = self.client.post(
            "/revisar-avulso", json=payload, headers={"X-API-Key": "chave-do-bruno"}
        )

        self.assertNotEqual(resposta_ana.status_code, 401)
        self.assertNotEqual(resposta_bruno.status_code, 401)

    def test_chave_inexistente_entre_multiplas_recebe_401(self) -> None:
        api_server._state["api_keys"] = {
            "chave-da-ana": "ana",
            "chave-do-bruno": "bruno",
        }

        resposta = self.client.post(
            "/revisar-avulso",
            json={"posicao": "8/8/8/8/8/8/8/8 w - - 0 1", "lance": "e4", "pensamento": "x"},
            headers={"X-API-Key": "chave-que-nao-existe"},
        )

        self.assertEqual(resposta.status_code, 401)

    def test_verificar_api_key_guarda_nome_no_request_state_e_retorna(self) -> None:
        # Chama a dependency diretamente (fora do ciclo de request do FastAPI) para
        # verificar que ela guarda o nome em request.state E o retorna, cobrindo
        # as duas formas de acesso mencionadas nos requisitos.
        api_server._state["api_keys"] = {"chave-da-ana": "ana"}
        request = Request(scope={"type": "http", "headers": []})

        nome = api_server.verificar_api_key(request=request, x_api_key="chave-da-ana")

        self.assertEqual(nome, "ana")
        self.assertEqual(request.state.api_key_nome, "ana")


class ResolverApiKeysTest(unittest.TestCase):
    """Testa o parse de API_SECRET_KEYS e a compatibilidade com API_SECRET_KEY."""

    def test_parse_multiplas_chaves(self) -> None:
        resultado = api_server._parse_api_keys(
            "ana:chave-da-ana,bruno:chave-do-bruno,carla:chave-da-carla"
        )

        self.assertEqual(
            resultado,
            {
                "chave-da-ana": "ana",
                "chave-do-bruno": "bruno",
                "chave-da-carla": "carla",
            },
        )

    def test_parse_ignora_espacos_e_entradas_vazias(self) -> None:
        resultado = api_server._parse_api_keys(" ana : chave-da-ana , , bruno:chave-do-bruno ")

        self.assertEqual(resultado, {"chave-da-ana": "ana", "chave-do-bruno": "bruno"})

    def test_parse_entrada_sem_dois_pontos_levanta_erro(self) -> None:
        with self.assertRaises(RuntimeError):
            api_server._parse_api_keys("ana-sem-separador")

    def test_resolver_usa_api_secret_keys_quando_definida(self) -> None:
        with patch.dict(
            os.environ,
            {"API_SECRET_KEYS": "ana:chave-da-ana,bruno:chave-do-bruno"},
            clear=False,
        ):
            os.environ.pop("API_SECRET_KEY", None)
            resultado = api_server._resolver_api_keys()

        self.assertEqual(
            resultado, {"chave-da-ana": "ana", "chave-do-bruno": "bruno"}
        )

    def test_resolver_cai_para_api_secret_key_legada(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("API_SECRET_KEYS", None)
            os.environ["API_SECRET_KEY"] = "chave-antiga"
            resultado = api_server._resolver_api_keys()

        self.assertEqual(resultado, {"chave-antiga": "eu"})

    def test_resolver_prioriza_api_secret_keys_sobre_a_legada(self) -> None:
        with patch.dict(
            os.environ,
            {"API_SECRET_KEYS": "ana:chave-da-ana", "API_SECRET_KEY": "chave-antiga"},
            clear=False,
        ):
            resultado = api_server._resolver_api_keys()

        self.assertEqual(resultado, {"chave-da-ana": "ana"})

    def test_resolver_sem_nenhuma_variavel_levanta_erro(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("API_SECRET_KEYS", None)
            os.environ.pop("API_SECRET_KEY", None)

            with self.assertRaises(RuntimeError):
                api_server._resolver_api_keys()


if __name__ == "__main__":
    unittest.main()
