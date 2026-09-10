"""Testes do gate de autenticação (X-API-Key) do servidor da API.

Não aciona o startup real (Stockfish/Gemini/Supabase): a TestClient só
dispara os eventos de lifespan dentro de um bloco `with`, então chamamos as
rotas sem entrar nesse bloco e populamos `_state["api_keys"]` manualmente,
garantindo que nenhuma credencial real é necessária.
"""

import json
import logging
import os
import threading
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.agentes.revisar_pensamento import Settings
from backend.api import api_server

CHAVE_CORRETA = "chave-secreta-de-teste"


def _fake_settings() -> Settings:
    return Settings(
        supabase_url="https://example.test",
        supabase_service_role_key="chave",
        stockfish_path="/usr/games/stockfish",
        stockfish_depth=16,
        gemini_api_key="chave-gemini",
        limiar_lance_bom=5.0,
        limiar_lance_ruim=15.0,
    )


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

    def test_health_retorna_200_sem_necessidade_de_chave(self) -> None:
        resposta = self.client.get("/health")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "ok"})

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

    def test_explicar_posicao_sem_header_recebe_401(self) -> None:
        resposta = self.client.post(
            "/explicar-posicao",
            json={"posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"},
        )
        self.assertEqual(resposta.status_code, 401)

    def test_explicar_posicao_chave_errada_recebe_401(self) -> None:
        resposta = self.client.post(
            "/explicar-posicao",
            json={"posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"},
            headers={"X-API-Key": "chave-errada"},
        )
        self.assertEqual(resposta.status_code, 401)

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


class ExplicarPosicaoEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        api_server._state.clear()
        api_server._state["api_keys"] = {CHAVE_CORRETA: "teste"}

        class _FakeEngine:
            def set_fen_position(self, fen: str) -> None:
                pass

            def get_evaluation(
                self, searchtime: int | None = None
            ) -> dict[str, Any]:
                return {"type": "cp", "value": 350}

            def get_top_moves(
                self, n: int, verbose: bool = False
            ) -> list[dict[str, Any]]:
                return [
                    {
                        "PVMoves": "d2d4 d7d5 c2c4",
                        "Move": "d2d4",
                        "Centipawn": 350,
                    }
                ]

        class _FakeResponse:
            def __init__(self, text: str) -> None:
                self.text = text

        class _FakeGemini:
            class models:
                @staticmethod
                def generate_content(model: str, contents: str) -> _FakeResponse:
                    return _FakeResponse(
                        json.dumps(
                            {
                                "veredito": "Brancas têm vantagem decisiva (+3.50).",
                                "ameaca_concreta": "Ameaça d4 abrindo o centro.",
                                "o_que_parece_bom_mas_falha": "d5 falha após c4.",
                                "plano_conversao": "Avançar peões centrais.",
                                "resumo_didatico": "Domínio central sem contra-jogo.",
                            }
                        )
                    )

        api_server._state["engine"] = _FakeEngine()
        api_server._state["gemini_client"] = _FakeGemini()
        api_server._state["settings"] = _fake_settings()
        api_server._state["logger"] = logging.getLogger("test_api")
        api_server._state["engine_lock"] = threading.Lock()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_posicao_invalida_retorna_400(self) -> None:
        resposta = self.client.post(
            "/explicar-posicao",
            json={"posicao": "string-totalmente-invalida"},
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 400)

    def test_lado_invalido_retorna_400(self) -> None:
        resposta = self.client.post(
            "/explicar-posicao",
            json={
                "posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "lado": "AZUL",
            },
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 400)

    def test_explicar_posicao_com_fen_retorna_200_e_schema_completo(self) -> None:
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        resposta = self.client.post(
            "/explicar-posicao",
            json={"posicao": fen, "lado": "BRANCAS"},
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["fen"], fen)
        self.assertEqual(dados["lado_a_jogar"], "BRANCAS")
        self.assertEqual(dados["lado_analisado"], "BRANCAS")
        self.assertIn("avaliacao", dados)
        self.assertEqual(dados["avaliacao"]["score_cp"], 350)
        self.assertIn("linhas_taticas", dados)
        self.assertIn("elementos_posicionais", dados)
        self.assertIn("explicacao", dados)
        self.assertIn("veredito", dados["explicacao"])
        self.assertIn("ameaca_concreta", dados["explicacao"])

    def test_explicar_posicao_com_pgn_retorna_200(self) -> None:
        pgn = "1. e4 e5 2. Nf3 Nc6"
        resposta = self.client.post(
            "/explicar-posicao",
            json={"posicao": pgn},
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertIn(
            "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R", dados["fen"]
        )

    def test_engine_ocupado_retorna_503(self) -> None:
        with patch(
            "backend.agentes.explicador_posicao._acquire_engine_lock",
            side_effect=api_server.EngineIndisponivelError("Servidor ocupado"),
        ):
            resposta = self.client.post(
                "/explicar-posicao",
                json={
                    "posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
                },
                headers={"X-API-Key": CHAVE_CORRETA},
            )
            self.assertEqual(resposta.status_code, 503)
            self.assertIn("Servidor ocupado", resposta.json()["detail"])


class AnalisarPgnEndpointTest(unittest.TestCase):
    """Testes do endpoint assíncrono POST /analisar-pgn."""

    PGN_TESTE = """[Event "Test Game"]
[White "hirano28"]
[Black "opponent123"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 1-0"""

    PGN_SEM_USERNAMES = """[Event "Test Game"]
[White "jogador_a"]
[Black "jogador_b"]
[Result "1/2-1/2"]

1. e4 e5 2. Nf3 Nc6 1/2-1/2"""

    def setUp(self) -> None:
        api_server._state.clear()
        api_server._state["api_keys"] = {CHAVE_CORRETA: "teste"}
        api_server._state["supabase_client"] = MagicMock()
        api_server._state["gemini_client"] = MagicMock()
        api_server._state["engine_lock"] = threading.Lock()
        # Mock logger isola completamente a saída de testes de prints/logs
        api_server._state["logger"] = MagicMock()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_sem_header_recebe_401(self) -> None:
        resposta = self.client.post(
            "/analisar-pgn",
            json={"pgn": self.PGN_TESTE},
        )
        self.assertEqual(resposta.status_code, 401)

    def test_pgn_vazio_recebe_400(self) -> None:
        resposta = self.client.post(
            "/analisar-pgn",
            json={"pgn": "   "},
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("PGN não fornecido", resposta.json()["detail"])

    def test_pgn_invalido_recebe_400(self) -> None:
        resposta = self.client.post(
            "/analisar-pgn",
            json={"pgn": "isso aqui nao e xadrez"},
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 400)

    @patch("backend.agentes.analisar_pgn_avulso.inferir_cor_jogador", return_value=None)
    def test_sem_cor_e_sem_inferencia_recebe_422(self, mock_inferir) -> None:
        resposta = self.client.post(
            "/analisar-pgn",
            json={"pgn": self.PGN_SEM_USERNAMES, "cor": None},
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 422)
        self.assertIn("informe a cor explicitamente", resposta.json()["detail"])

    @patch("backend.api.api_server.load_analysis_settings")
    @patch("backend.api.api_server.load_linter_settings")
    @patch("backend.api.api_server.executar_pipeline_partida")
    @patch("backend.api.api_server.inserir_partida", return_value="partida_999")
    def test_retorna_202_imediatamente_e_agenda_background_task(
        self, mock_inserir, mock_executar_pipeline, mock_linter, mock_analysis
    ) -> None:
        resposta = self.client.post(
            "/analisar-pgn",
            json={"pgn": self.PGN_TESTE, "cor": "BRANCAS"},
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 202)
        dados = resposta.json()
        self.assertEqual(dados["partida_id"], "partida_999")
        self.assertTrue(dados["external_id"].startswith("manual_"))

        # Confirma que a tarefa de segundo plano rodou após a resposta
        mock_executar_pipeline.assert_called_once()
        _, kwargs = mock_executar_pipeline.call_args
        self.assertEqual(kwargs["partida_id"], "partida_999")
        self.assertIsNotNone(kwargs["engine_lock"])

    @patch("backend.api.api_server.load_analysis_settings")
    @patch("backend.api.api_server.load_linter_settings")
    @patch("backend.api.api_server.executar_pipeline_partida")
    @patch("backend.agentes.analisar_pgn_avulso.inferir_cor_jogador", return_value="BRANCAS")
    @patch("backend.api.api_server.inserir_partida", return_value="partida_888")
    def test_infere_cor_automaticamente_se_cor_for_null(
        self, mock_inserir, mock_inferir, mock_executar_pipeline, mock_linter, mock_analysis
    ) -> None:
        resposta = self.client.post(
            "/analisar-pgn",
            json={"pgn": self.PGN_TESTE, "cor": None},
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 202)
        dados = resposta.json()
        self.assertEqual(dados["partida_id"], "partida_888")
        mock_inserir.assert_called_once()
        # Argumento cor passado para inserir_partida deve ser "BRANCAS"
        args, _ = mock_inserir.call_args
        self.assertEqual(args[3], "BRANCAS")

        # Confirma que a tarefa de segundo plano foi agendada e executada
        mock_executar_pipeline.assert_called_once()
        _, kwargs = mock_executar_pipeline.call_args
        self.assertEqual(kwargs["partida_id"], "partida_888")

    @patch("backend.api.api_server.update_status")
    @patch("backend.api.api_server.load_analysis_settings")
    @patch("backend.api.api_server.load_linter_settings")
    @patch("backend.api.api_server.executar_pipeline_partida")
    def test_background_task_falha_marca_partida_como_falhou(
        self, mock_executar_pipeline, mock_linter_settings, mock_analysis_settings, mock_update
    ) -> None:
        """Verifica INTENCIONALMENTE o comportamento de falha graciosa da tarefa em background:

        Se executar_pipeline_partida levantar exceção, a tarefa deve capturar o erro,
        não derrubar o processo e atualizar o status da partida para 'falhou'.
        """
        mock_executar_pipeline.side_effect = RuntimeError("Erro simulado para testar falha graciosa")
        mock_client = MagicMock()
        api_server._state["supabase_client"] = mock_client

        api_server._executar_analise_pgn_background("partida_falha")

        mock_update.assert_called_with(mock_client, "partida_falha", "falhou")

    def test_obter_resumo_sem_api_key_recebe_401(self) -> None:
        resposta = self.client.get("/partidas/partida_123/resumo")
        self.assertEqual(resposta.status_code, 401)

    def test_obter_resumo_partida_inexistente_recebe_404(self) -> None:
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get(
            "/partidas/partida_inexistente/resumo",
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 404)
        self.assertIn("não encontrada", resposta.json()["detail"])

    def test_obter_resumo_partida_processando_retorna_resumo_nulo(self) -> None:
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = [{"id": "p1", "external_id": "ext1", "status_processamento": "processando"}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get(
            "/partidas/p1/resumo",
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["partida_id"], "p1")
        self.assertEqual(dados["status"], "processando")
        self.assertIsNone(dados["resumo"])

    def test_obter_resumo_partida_concluida_retorna_resumo_completo(self) -> None:
        mock_client = MagicMock()

        def table_side_effect(table_name: str):
            mock_table = MagicMock()
            if table_name == "partidas":
                resp = MagicMock()
                resp.data = [{"id": "p2", "external_id": "ext2", "status_processamento": "concluido"}]
                mock_table.select.return_value.eq.return_value.execute.return_value = resp
            elif table_name == "resumo_partida":
                resp = MagicMock()
                resp.data = [{
                    "narrativa": "A partida começou com uma Siciliana...",
                    "pontos_criticos": [{"numero_lance": 15, "tipo_evento": "PICO", "tags_falha": ["perda_de_material"]}],
                    "momento_chave_estrategico": "Lance 15 foi decisivo."
                }]
                mock_table.select.return_value.eq.return_value.execute.return_value = resp
            return mock_table

        mock_client.table.side_effect = table_side_effect
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get(
            "/partidas/p2/resumo",
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["partida_id"], "p2")
        self.assertEqual(dados["status"], "concluido")
        self.assertIsNotNone(dados["resumo"])
        self.assertIn("Siciliana", dados["resumo"]["narrativa"])
        self.assertEqual(len(dados["resumo"]["pontos_criticos"]), 1)

    def test_listar_partidas_recentes_sem_api_key_recebe_401(self) -> None:
        resposta = self.client.get("/partidas/recentes")
        self.assertEqual(resposta.status_code, 401)

    def test_listar_partidas_recentes_sucesso(self) -> None:
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = [
            {
                "id": "p-1",
                "external_id": "ext-1",
                "status_processamento": "processando",
                "cor_jogada": "BRANCAS",
                "resultado": "VITORIA",
                "eco_abertura": "B90",
                "data_partida": "2024-06-15",
                "created_at": "2026-09-10T01:58:29.165Z",
                "pgn": '[White "hirano28"]\n[Black "oponente"]\n\n1. e4 c5',
            }
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get(
            "/partidas/recentes",
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 200)
        itens = resposta.json()
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["partida_id"], "p-1")
        self.assertEqual(itens[0]["status"], "processando")
        self.assertEqual(itens[0]["jogadores"], "hirano28 vs oponente")
        self.assertEqual(itens[0]["eco_abertura"], "B90")

    def test_reprocessar_sem_api_key_recebe_401(self) -> None:
        resposta = self.client.post("/partidas/p123/reprocessar")
        self.assertEqual(resposta.status_code, 401)

    def test_reprocessar_partida_inexistente_recebe_404(self) -> None:
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.post(
            "/partidas/inexistente/reprocessar",
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 404)

    @patch("backend.api.api_server.update_status")
    @patch("backend.api.api_server.executar_pipeline_partida")
    @patch("backend.api.api_server.load_analysis_settings")
    @patch("backend.api.api_server.load_linter_settings")
    def test_reprocessar_partida_existente_agenda_background_task(
        self,
        mock_linter_settings: MagicMock,
        mock_analysis_settings: MagicMock,
        mock_executar: MagicMock,
        mock_update: MagicMock,
    ) -> None:
        mock_analysis_settings.return_value = MagicMock()
        mock_linter_settings.return_value = MagicMock()
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = [{"id": "p-existente", "external_id": "ext-existente"}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.post(
            "/partidas/p-existente/reprocessar",
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        self.assertEqual(resposta.status_code, 202)
        dados = resposta.json()
        self.assertEqual(dados["partida_id"], "p-existente")
        self.assertEqual(dados["external_id"], "ext-existente")
        mock_update.assert_called_with(mock_client, "p-existente", "processando")
        mock_executar.assert_called_once()


if __name__ == "__main__":
    unittest.main()


