"""Testes do servidor da API, incluindo o gate de sessão do Supabase Auth (D-25).

Não aciona o startup real (Stockfish/Gemini/Supabase): a TestClient só
dispara os eventos de lifespan dentro de um bloco `with`, então chamamos as
rotas sem entrar nesse bloco e populamos `_state` manualmente, garantindo que
nenhuma credencial real é necessária.
"""

import base64
import hashlib
import json
import logging
import os
import threading
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi import Depends, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.agentes.popular_fila_treino_espacado import _CACHE_CITACAO
from backend.agentes.revisar_pensamento import AvaliacaoLance, Settings
from backend.api import api_server

# Dono dos dados nas tabelas raiz (Fase A do multi-tenant — ver D-14).
USER_ID_TESTE = "11111111-2222-3333-4444-555555555555"
TOKEN_TESTE = "token-de-sessao-de-teste"
HEADERS_SESSAO = {"Authorization": f"Bearer {TOKEN_TESTE}"}



# D-32: as 4 rotas caras passaram a exigir também o limite diário (RPC real
# via _state["supabase_client"]). Os testes de endpoint não estão testando o
# limite em si (isso é o `LimiteDiarioTest`), então esses 4 também ganham um
# override padrão que devolve o dono sem tocar no banco - mesmo princípio do
# override de `verificar_sessao` logo abaixo. /reprocessar e
# /treino/{id}/responder ganharam o mesmo tratamento numa auditoria pós-D-49
# (tinham ficado de fora por descuido).
_LIMITES_DIARIOS_DEPENDENCIES = (
    api_server.verificar_limite_analisar_pgn,
    api_server.verificar_limite_explicar_posicao,
    api_server.verificar_limite_revisar_avulso,
    api_server.verificar_limite_reconhecer_posicao,
    api_server.verificar_limite_reprocessar,
    api_server.verificar_limite_treino_responder,
)


def setUpModule() -> None:
    """Desde D-25 toda rota exige sessão do Supabase Auth.

    Os testes de endpoint não estão testando o gate em si (isso é o
    `VerificarSessaoTest`), então injetam um dono fixo pelo mecanismo que o
    próprio FastAPI oferece — assim nenhum deles precisa mockar `auth.get_user`.
    """

    api_server.app.dependency_overrides[api_server.verificar_sessao] = (
        lambda: USER_ID_TESTE
    )
    for dependencia in _LIMITES_DIARIOS_DEPENDENCIES:
        api_server.app.dependency_overrides[dependencia] = lambda: USER_ID_TESTE


def tearDownModule() -> None:
    api_server.app.dependency_overrides.clear()


def _apenas_sessao(user_id: str = Depends(api_server.verificar_sessao)) -> str:
    """Override usado por `gate_de_sessao_real()` nas 4 rotas com limite diário.

    Valida a sessão de verdade (mesma `verificar_sessao`, sem override), mas
    sem chamar o RPC do limite diário — esses testes estão exercitando o gate
    de sessão (D-25), não o limite (isso é `LimiteDiarioTest`).
    """

    return user_id


@contextmanager
def gate_de_sessao_real():
    """Desliga o override para exercitar o gate de verdade (401 e afins)."""

    api_server.app.dependency_overrides.pop(api_server.verificar_sessao, None)
    for dependencia in _LIMITES_DIARIOS_DEPENDENCIES:
        api_server.app.dependency_overrides[dependencia] = _apenas_sessao
    try:
        yield
    finally:
        api_server.app.dependency_overrides[api_server.verificar_sessao] = (
            lambda: USER_ID_TESTE
        )
        for dependencia in _LIMITES_DIARIOS_DEPENDENCIES:
            api_server.app.dependency_overrides[dependencia] = lambda: USER_ID_TESTE


@contextmanager
def gate_de_limite_diario_real(dependencia):
    """Desliga o override de UM limite diário específico para testar o 429 de verdade.

    `dependencia` é um dos atributos `api_server.verificar_limite_*`; as
    demais rotas continuam com o limite mockado (sem tocar no banco).
    """

    api_server.app.dependency_overrides.pop(dependencia, None)
    try:
        yield
    finally:
        api_server.app.dependency_overrides[dependencia] = lambda: USER_ID_TESTE


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


class SessaoAuthTest(unittest.TestCase):
    """Gate de acesso da API: sessão do Supabase Auth, e só ela (D-25).

    Roda com `gate_de_sessao_real()` — sem o override de módulo — porque aqui o
    objeto em teste É o gate, não o endpoint.
    """

    PAYLOAD_REVISAR = {
        "posicao": "8/8/8/8/8/8/8/8 w - - 0 1",
        "lance": "e4",
        "pensamento": "x",
    }

    def setUp(self) -> None:
        api_server._state.clear()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_sem_header_authorization_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.post("/revisar-avulso", json=self.PAYLOAD_REVISAR)

        self.assertEqual(resposta.status_code, 401)

    def test_x_api_key_nao_abre_porta_nenhuma(self) -> None:
        """Mecanismo removido na auditoria pós-D-49: nenhum header substitui a sessão."""

        with gate_de_sessao_real():
            resposta = self.client.post(
                "/revisar-avulso",
                json=self.PAYLOAD_REVISAR,
                headers={"X-API-Key": "qualquer-valor"},
            )

        self.assertEqual(resposta.status_code, 401)

    def test_token_invalido_recebe_401(self) -> None:
        mock_client = MagicMock()
        mock_client.auth.get_user.side_effect = RuntimeError("token podre")
        api_server._state["supabase_client"] = mock_client

        with gate_de_sessao_real():
            resposta = self.client.post(
                "/revisar-avulso",
                json=self.PAYLOAD_REVISAR,
                headers={"Authorization": "Bearer token-invalido"},
            )

        self.assertEqual(resposta.status_code, 401)

    def test_401_nao_executa_logica_de_negocio(self) -> None:
        # Sem "engine"/"gemini_client"/"supabase_client" em _state, qualquer
        # tentativa de uso lançaria KeyError em vez de retornar 401 limpo.
        with gate_de_sessao_real():
            resposta = self.client.post("/revisar-avulso", json=self.PAYLOAD_REVISAR)

        self.assertEqual(resposta.status_code, 401)
        self.assertNotIn("engine", api_server._state)
        self.assertNotIn("gemini_client", api_server._state)
        self.assertNotIn("supabase_client", api_server._state)

    def test_todos_os_endpoints_protegidos_exigem_sessao(self) -> None:
        """Varre as rotas de verdade em vez de confiar numa lista escrita à mão."""

        publicas = {
            "/health",
            "/guia-passos",
            "/openapi.json",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
            # D-33: única rota de negócio fora do gate, e de propósito. É o
            # destino do redirect do lichess.org — chega como navegação de topo
            # do navegador, sem o header Authorization que o frontend anexa via
            # fetch. Quem autentica ali é o `state` de uso único, amarrado a um
            # user_id por /lichess/oauth/iniciar, essa sim protegida por sessão.
            # `CallbackOauthLichessTest` cobre o que ela aceita e o que recusa.
            "/lichess/oauth/callback",
        }
        verificadas = 0
        with gate_de_sessao_real():
            for rota in api_server.app.routes:
                caminho = getattr(rota, "path", "")
                metodos = getattr(rota, "methods", set()) - {"HEAD", "OPTIONS"}
                if not metodos or caminho in publicas or "{" in caminho:
                    continue
                for metodo in metodos:
                    resposta = self.client.request(metodo, caminho, json={})
                    self.assertEqual(
                        resposta.status_code,
                        401,
                        f"{metodo} {caminho} deveria exigir sessão",
                    )
                    verificadas += 1

        self.assertGreaterEqual(verificadas, 8)

    def test_health_continua_publico(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.get("/health")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "ok"})

    def test_sessao_valida_passa_do_gate(self) -> None:
        mock_client = MagicMock()
        mock_client.auth.get_user.return_value.user.id = USER_ID_TESTE
        api_server._state["supabase_client"] = mock_client

        with gate_de_sessao_real():
            # FEN válida passa da resolução de posição; sem "engine" em _state a
            # rota falha depois — o que importa é não ser 401.
            resposta = self.client.post(
                "/revisar-avulso",
                json={
                    "posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                    "lance": "e4",
                    "pensamento": "x",
                },
                headers=HEADERS_SESSAO,
            )

        self.assertNotEqual(resposta.status_code, 401)
        mock_client.auth.get_user.assert_called_once_with(TOKEN_TESTE)


class VerificarSessaoTest(unittest.TestCase):
    """A dependency isolada: o que ela aceita, o que rejeita e o que devolve."""

    def setUp(self) -> None:
        api_server._state.clear()

    def tearDown(self) -> None:
        api_server._state.clear()

    def _request(self, authorization: str | None) -> Request:
        headers = (
            [(b"authorization", authorization.encode())] if authorization else []
        )
        return Request(scope={"type": "http", "headers": headers})

    def test_token_valido_devolve_user_id_e_guarda_no_request_state(self) -> None:
        mock_client = MagicMock()
        mock_client.auth.get_user.return_value.user.id = USER_ID_TESTE
        api_server._state["supabase_client"] = mock_client
        request = self._request(f"Bearer {TOKEN_TESTE}")

        user_id = api_server.verificar_sessao(request)

        self.assertEqual(user_id, USER_ID_TESTE)
        self.assertEqual(request.state.user_id, USER_ID_TESTE)

    def test_sem_header_levanta_401(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            api_server.verificar_sessao(self._request(None))

        self.assertEqual(ctx.exception.status_code, 401)

    def test_header_sem_prefixo_bearer_levanta_401(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            api_server.verificar_sessao(self._request(TOKEN_TESTE))

        self.assertEqual(ctx.exception.status_code, 401)

    def test_bearer_vazio_levanta_401(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            api_server.verificar_sessao(self._request("Bearer   "))

        self.assertEqual(ctx.exception.status_code, 401)

    def test_get_user_retornando_none_levanta_401(self) -> None:
        mock_client = MagicMock()
        mock_client.auth.get_user.return_value.user = None
        api_server._state["supabase_client"] = mock_client

        with self.assertRaises(HTTPException) as ctx:
            api_server.verificar_sessao(self._request(f"Bearer {TOKEN_TESTE}"))

        self.assertEqual(ctx.exception.status_code, 401)

    def test_sem_supabase_client_levanta_401(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            api_server.verificar_sessao(self._request(f"Bearer {TOKEN_TESTE}"))

        self.assertEqual(ctx.exception.status_code, 401)


class ResolverFenEndpointTest(unittest.TestCase):
    """Testes do endpoint GET /resolver-fen (só parsing, sem Gemini/Stockfish)."""

    def setUp(self) -> None:
        api_server._state.clear()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.get(
                "/resolver-fen",
                params={"posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"},
            )
            self.assertEqual(resposta.status_code, 401)

    def test_fen_direta_retorna_a_mesma_posicao(self) -> None:
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        resposta = self.client.get(
            "/resolver-fen",
            params={"posicao": fen},
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"fen": fen})

    def test_pgn_valido_retorna_fen_final(self) -> None:
        resposta = self.client.get(
            "/resolver-fen",
            params={"posicao": "1. e4 e5 2. Nf3 Nc6"},
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.json()["fen"],
            "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
        )

    def test_posicao_invalida_recebe_400(self) -> None:
        resposta = self.client.get(
            "/resolver-fen",
            params={"posicao": "isso nao e uma posicao valida"},
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 400)


class RevisarAvulsoLanceInterpretadoTest(unittest.TestCase):
    """A interpretação PT/EN do lance precisa chegar íntegra ao dashboard."""

    def setUp(self) -> None:
        api_server._state.clear()
        api_server._state["engine"] = MagicMock()
        api_server._state["gemini_client"] = MagicMock()
        api_server._state["settings"] = _fake_settings()
        api_server._state["logger"] = logging.getLogger("test_api_server")
        api_server._state["engine_lock"] = threading.Lock()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_resposta_expoe_lance_interpretado_em_portugues(self) -> None:
        # O usuário digitou 'Cf3'; a pipeline resolve para o SAN 'Nf3' e devolve
        # a leitura em português junto, para ele conferir o que entendemos.
        resultado = {
            "fen": chess_fen_inicial(),
            "lances": ["Nf3"],
            "lance_interpretado": "Cf3",
            "avaliacoes": [
                {
                    "indice_na_sequencia": 1,
                    "lance_jogado": "Nf3",
                    "lance_interpretado": "Cf3",
                    "melhor_lance": "e4",
                    "queda_win_percent": 1.5,
                    "qualidade_lance": "BOM",
                    "qualidade_raciocinio": "SOLIDO",
                    "feedback_texto": "ok",
                    "analise_mestre": "ok",
                    "top_candidatos": [],
                    "checklist_rotina": {},
                }
            ],
            "resumo_geral": None,
        }

        with patch.object(
            api_server, "processar_revisao_sequencia", return_value=resultado
        ):
            resposta = self.client.post(
                "/revisar-avulso",
                json={
                    "posicao": chess_fen_inicial(),
                    "lance": "Cf3",
                    "pensamento": "Desenvolvo o cavalo.",
                },
                headers=HEADERS_SESSAO,
            )

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["lance_interpretado"], "Cf3")
        self.assertEqual(corpo["avaliacoes"][0]["lance_interpretado"], "Cf3")
        self.assertEqual(corpo["avaliacoes"][0]["lance_jogado"], "Nf3")


def chess_fen_inicial() -> str:
    return "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"



class ExplicarPosicaoEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        api_server._state.clear()

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
        # explicacoes_posicao é tabela raiz: a persistência exige user_id (D-14).
        self._env = patch.dict(os.environ, {"DEFAULT_USER_ID": USER_ID_TESTE})
        self._env.start()
        self.addCleanup(self._env.stop)
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_posicao_invalida_retorna_400(self) -> None:
        resposta = self.client.post(
            "/explicar-posicao",
            json={"posicao": "string-totalmente-invalida"},
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 400)

    def test_lado_invalido_retorna_400(self) -> None:
        resposta = self.client.post(
            "/explicar-posicao",
            json={
                "posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "lado": "AZUL",
            },
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 400)

    def test_explicar_posicao_com_fen_retorna_200_e_schema_completo(self) -> None:
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        resposta = self.client.post(
            "/explicar-posicao",
            json={"posicao": fen, "lado": "BRANCAS"},
            headers=HEADERS_SESSAO,
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
            headers=HEADERS_SESSAO,
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
                headers=HEADERS_SESSAO,
            )
            self.assertEqual(resposta.status_code, 503)
            self.assertIn("Servidor ocupado", resposta.json()["detail"])

    def test_explicar_posicao_persiste_e_devolve_id(self) -> None:
        # Fecha P-10: a explicação gerada precisa ser salva em
        # explicacoes_posicao, e o id da linha criada precisa voltar na
        # resposta (usado pelo frontend para marcar o item como "ativo").
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = [{"id": "explicacao-nova-123"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.post(
            "/explicar-posicao",
            json={
                "posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "lado": "BRANCAS",
            },
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["id"], "explicacao-nova-123")
        mock_client.table.assert_any_call("explicacoes_posicao")
        payload_inserido = mock_client.table.return_value.insert.call_args[0][0]
        self.assertEqual(
            payload_inserido["fen"],
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        )
        self.assertEqual(payload_inserido["lado_analisado"], "BRANCAS")
        self.assertIn("resultado", payload_inserido)
        # O dono vem da sessao (override do modulo injeta USER_ID_TESTE).
        self.assertEqual(payload_inserido["user_id"], USER_ID_TESTE)

    def test_explicar_posicao_com_sessao_valida_usa_user_id_real(self) -> None:
        with gate_de_sessao_real():
            # Fase B.2 (D-17): com Authorization: Bearer válido, a linha nasce
            # com o dono real da sessão, não o DEFAULT_USER_ID de sempre.
            user_id_sessao = "99999999-8888-7777-6666-555555555555"
            mock_client = MagicMock()
            resp_mock = MagicMock()
            resp_mock.data = [{"id": "explicacao-nova-456"}]
            mock_client.table.return_value.insert.return_value.execute.return_value = resp_mock
            mock_user_response = MagicMock()
            mock_user_response.user.id = user_id_sessao
            mock_client.auth.get_user.return_value = mock_user_response
            api_server._state["supabase_client"] = mock_client

            resposta = self.client.post(
                "/explicar-posicao",
                json={
                    "posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                    "lado": "BRANCAS",
                },
                headers=HEADERS_SESSAO,
            )

            self.assertEqual(resposta.status_code, 200)
            mock_client.auth.get_user.assert_called_once_with(TOKEN_TESTE)
            payload_inserido = mock_client.table.return_value.insert.call_args[0][0]
            self.assertEqual(payload_inserido["user_id"], user_id_sessao)

    def test_explicar_posicao_retorna_200_mesmo_se_persistencia_falhar(self) -> None:
        # A persistência é um efeito colateral: se salvar falhar, o usuário
        # ainda recebe a explicação (só sem id) - não pode virar erro 500.
        mock_client = MagicMock()
        mock_client.table.return_value.insert.return_value.execute.side_effect = (
            RuntimeError("Falha simulada de conexão com o banco")
        )
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.post(
            "/explicar-posicao",
            json={
                "posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
            },
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(resposta.json()["id"])
        self.assertIn("explicacao", resposta.json())

    def test_explicar_posicao_sem_supabase_client_no_state_continua_200(self) -> None:
        # setUp desta classe não coloca "supabase_client" em _state (padrão já
        # existente nos outros testes) - confirma que o KeyError resultante
        # também é tratado como falha graciosa de persistência, não erro 500.
        resposta = self.client.post(
            "/explicar-posicao",
            json={
                "posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
            },
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(resposta.json()["id"])


class ExplicacoesPosicaoRecentesEndpointTest(unittest.TestCase):
    """Testes do endpoint GET /explicacoes-posicao/recentes."""

    def setUp(self) -> None:
        api_server._state.clear()
        self.client = TestClient(api_server.app)
        # Leitura agora filtra por dono (Fase B.3 — D-18); sem Authorization
        # Bearer nestes testes, cai no fallback DEFAULT_USER_ID de sempre.
        self._env = patch.dict(os.environ, {"DEFAULT_USER_ID": USER_ID_TESTE})
        self._env.start()
        self.addCleanup(self._env.stop)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.get("/explicacoes-posicao/recentes")
            self.assertEqual(resposta.status_code, 401)

    def test_lista_com_sucesso_embute_resultado_completo(self) -> None:
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resultado_completo = {
            "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "lado_a_jogar": "BRANCAS",
            "lado_analisado": "BRANCAS",
            "avaliacao": {
                "score_cp": 0,
                "mate": None,
                "win_percent": 50.0,
                "lado_vencedor": "EQUILIBRADO",
                "descricao": "Posição inicial",
            },
            "linhas_taticas": [],
            "refutacao_defesa": None,
            "elementos_posicionais": {},
            "explicacao": {
                "veredito": "Posição equilibrada.",
                "ameaca_concreta": "Nenhuma ainda.",
                "o_que_parece_bom_mas_falha": "N/A",
                "plano_conversao": "Desenvolver as peças.",
                "resumo_didatico": "Início de partida.",
            },
        }
        resp_mock.data = [
            {
                "id": "exp-1",
                "fen": resultado_completo["fen"],
                "lado_analisado": "BRANCAS",
                "resultado": resultado_completo,
                "created_at": "2026-09-11T10:00:00Z",
            }
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get(
            "/explicacoes-posicao/recentes",
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 200)
        itens = resposta.json()
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["id"], "exp-1")
        self.assertEqual(itens[0]["lado_analisado"], "BRANCAS")
        # O resultado embutido é o suficiente para restaurar a tela sem outra
        # chamada de rede (não existe endpoint "buscar por id" nesta API).
        self.assertEqual(
            itens[0]["resultado"]["explicacao"]["veredito"], "Posição equilibrada."
        )
        # Sem Authorization: Bearer, o filtro cai no DEFAULT_USER_ID (D-18).
        mock_client.table.return_value.select.return_value.eq.assert_called_once_with(
            "user_id", USER_ID_TESTE
        )

    def test_filtra_pelo_user_id_da_sessao_quando_autorizacao_valida(self) -> None:
        with gate_de_sessao_real():
            # Fase B.3 (D-18): a listagem também respeita a sessão real, não só a escrita.
            user_id_sessao = "99999999-8888-7777-6666-555555555555"
            mock_client = MagicMock()
            resp_mock = MagicMock()
            resp_mock.data = []
            mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = resp_mock
            mock_user_response = MagicMock()
            mock_user_response.user.id = user_id_sessao
            mock_client.auth.get_user.return_value = mock_user_response
            api_server._state["supabase_client"] = mock_client

            resposta = self.client.get(
                "/explicacoes-posicao/recentes",
                headers=HEADERS_SESSAO,
            )

            self.assertEqual(resposta.status_code, 200)
            mock_client.table.return_value.select.return_value.eq.assert_called_once_with(
                "user_id", user_id_sessao
            )

    def test_banco_indisponivel_retorna_503(self) -> None:
        resposta = self.client.get(
            "/explicacoes-posicao/recentes",
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 503)


class ReconhecerPosicaoEndpointTest(unittest.TestCase):
    """Testes do endpoint POST /reconhecer-posicao (reconhecimento via Gemini visão).

    O conteúdo binário enviado como "imagem" não precisa ser um PNG/JPG real:
    o content-type explícito no upload já é suficiente para exercitar a
    validação, e as chamadas ao Gemini são sempre mockadas nestes testes.
    """

    IMAGEM_FAKE = b"bytes-de-imagem-fake-para-teste"

    def setUp(self) -> None:
        api_server._state.clear()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def _mock_gemini(self, texto_resposta: str) -> MagicMock:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = texto_resposta
        mock_client.models.generate_content.return_value = mock_response
        return mock_client

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.post(
                "/reconhecer-posicao",
                files={"imagem": ("foto.png", self.IMAGEM_FAKE, "image/png")},
            )
            self.assertEqual(resposta.status_code, 401)

    def test_arquivo_que_nao_e_imagem_recebe_400(self) -> None:
        resposta = self.client.post(
            "/reconhecer-posicao",
            files={
                "imagem": ("documento.pdf", b"%PDF-1.4 conteudo falso", "application/pdf")
            },
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 400)

    def test_arquivo_vazio_recebe_400(self) -> None:
        resposta = self.client.post(
            "/reconhecer-posicao",
            files={"imagem": ("foto.png", b"", "image/png")},
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 400)

    def test_imagem_maior_que_limite_recebe_400(self) -> None:
        dados_grandes = b"\x00" * (api_server.RECONHECER_POSICAO_MAX_BYTES + 1)
        resposta = self.client.post(
            "/reconhecer-posicao",
            files={"imagem": ("foto.png", dados_grandes, "image/png")},
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 400)

    def test_fen_invalido_do_gemini_recebe_422(self) -> None:
        api_server._state["gemini_client"] = self._mock_gemini("isso não é um FEN válido")

        resposta = self.client.post(
            "/reconhecer-posicao",
            files={"imagem": ("foto.png", self.IMAGEM_FAKE, "image/png")},
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 422)
        self.assertIn("Não foi possível reconhecer", resposta.json()["detail"])

    def test_fen_valido_retorna_200(self) -> None:
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        api_server._state["gemini_client"] = self._mock_gemini(fen)

        resposta = self.client.post(
            "/reconhecer-posicao",
            files={"imagem": ("foto.png", self.IMAGEM_FAKE, "image/png")},
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"fen": fen})

    def test_fen_com_fence_markdown_e_limpo_antes_de_validar(self) -> None:
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        api_server._state["gemini_client"] = self._mock_gemini(f"```\n{fen}\n```")

        resposta = self.client.post(
            "/reconhecer-posicao",
            files={"imagem": ("foto.png", self.IMAGEM_FAKE, "image/png")},
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["fen"], fen)

    def test_falha_ao_consultar_gemini_retorna_500(self) -> None:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("indisponível")
        api_server._state["gemini_client"] = mock_client

        resposta = self.client.post(
            "/reconhecer-posicao",
            files={"imagem": ("foto.png", self.IMAGEM_FAKE, "image/png")},
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 500)


class RevisarAvulsoSalvarEndpointTest(unittest.TestCase):
    """Testes de sucesso do POST /revisar-avulso/salvar (o 401 já é coberto em ApiKeyAuthTest)."""

    def setUp(self) -> None:
        api_server._state.clear()
        # revisao_exercicio_avulso é tabela raiz: o insert exige user_id (D-14).
        self._env = patch.dict(os.environ, {"DEFAULT_USER_ID": USER_ID_TESTE})
        self._env.start()
        self.addCleanup(self._env.stop)
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_salvar_com_sucesso_devolve_id_da_linha_criada(self) -> None:
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = [{"id": "revisao-nova-456"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

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
                "fen": chess_fen_inicial(),
                "texto_pensamento": "x",
            },
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["status"], "salvo")
        self.assertEqual(dados["id"], "revisao-nova-456")
        mock_client.table.assert_any_call("revisao_exercicio_avulso")
        # Ponta a ponta pela API: a linha nova nasce com o dono preenchido.
        payload = mock_client.table.return_value.insert.call_args[0][0]
        self.assertEqual(payload["user_id"], USER_ID_TESTE)

    def test_salvar_com_sessao_valida_usa_user_id_real(self) -> None:
        with gate_de_sessao_real():
            # Gate real: o user_id vem do token, validado por auth.get_user (D-25).
            user_id_sessao = "99999999-8888-7777-6666-555555555555"
            mock_client = MagicMock()
            resp_mock = MagicMock()
            resp_mock.data = [{"id": "revisao-nova-789"}]
            mock_client.table.return_value.insert.return_value.execute.return_value = resp_mock
            mock_user_response = MagicMock()
            mock_user_response.user.id = user_id_sessao
            mock_client.auth.get_user.return_value = mock_user_response
            api_server._state["supabase_client"] = mock_client

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
                    "fen": chess_fen_inicial(),
                    "texto_pensamento": "x",
                },
                headers=HEADERS_SESSAO,
            )

            self.assertEqual(resposta.status_code, 200)
            mock_client.auth.get_user.assert_called_once_with(TOKEN_TESTE)
            payload = mock_client.table.return_value.insert.call_args[0][0]
            self.assertEqual(payload["user_id"], user_id_sessao)

    def test_falha_ao_salvar_retorna_500(self) -> None:
        mock_client = MagicMock()
        mock_client.table.return_value.insert.return_value.execute.side_effect = (
            RuntimeError("Falha simulada")
        )
        api_server._state["supabase_client"] = mock_client

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
                "fen": chess_fen_inicial(),
                "texto_pensamento": "x",
            },
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 500)


class RevisoesAvulsasRecentesEndpointTest(unittest.TestCase):
    """Testes do endpoint GET /revisoes-avulsas/recentes."""

    def setUp(self) -> None:
        api_server._state.clear()
        self.client = TestClient(api_server.app)
        # Leitura agora filtra por dono (Fase B.3 — D-18); sem Authorization
        # Bearer nestes testes, cai no fallback DEFAULT_USER_ID de sempre.
        self._env = patch.dict(os.environ, {"DEFAULT_USER_ID": USER_ID_TESTE})
        self._env.start()
        self.addCleanup(self._env.stop)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.get("/revisoes-avulsas/recentes")
            self.assertEqual(resposta.status_code, 401)

    def test_lista_com_sucesso(self) -> None:
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = [
            {
                "id": "rev-1",
                "fen": chess_fen_inicial(),
                "lance_jogado": "e4",
                "melhor_lance": "e4",
                "queda_win_percent": 0.0,
                "texto_pensamento": "Abro o centro.",
                "qualidade_lance": "BOM",
                "qualidade_raciocinio": "SOLIDO",
                "feedback_texto": "Lance principal, sem contestação.",
                "created_at": "2026-09-11T10:00:00Z",
            }
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get(
            "/revisoes-avulsas/recentes",
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 200)
        itens = resposta.json()
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["id"], "rev-1")
        self.assertEqual(itens[0]["lance_jogado"], "e4")
        self.assertEqual(itens[0]["qualidade_lance"], "BOM")
        # Sem Authorization: Bearer, o filtro cai no DEFAULT_USER_ID (D-18).
        mock_client.table.return_value.select.return_value.eq.assert_called_once_with(
            "user_id", USER_ID_TESTE
        )

    def test_filtra_pelo_user_id_da_sessao_quando_autorizacao_valida(self) -> None:
        with gate_de_sessao_real():
            # Fase B.3 (D-18): a listagem também respeita a sessão real, não só a escrita.
            user_id_sessao = "99999999-8888-7777-6666-555555555555"
            mock_client = MagicMock()
            resp_mock = MagicMock()
            resp_mock.data = []
            mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = resp_mock
            mock_user_response = MagicMock()
            mock_user_response.user.id = user_id_sessao
            mock_client.auth.get_user.return_value = mock_user_response
            api_server._state["supabase_client"] = mock_client

            resposta = self.client.get(
                "/revisoes-avulsas/recentes",
                headers=HEADERS_SESSAO,
            )

            self.assertEqual(resposta.status_code, 200)
            mock_client.table.return_value.select.return_value.eq.assert_called_once_with(
                "user_id", user_id_sessao
            )

    def test_banco_indisponivel_retorna_503(self) -> None:
        resposta = self.client.get(
            "/revisoes-avulsas/recentes",
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 503)


class InsightsRepertorioEndpointTest(unittest.TestCase):
    """Testes do endpoint GET /insights/repertorio.

    O cálculo das 4 agregações já é testado a fundo com dados sintéticos em
    backend/agentes/test_insights_repertorio.py; aqui só verificamos que a
    rota autentica, delega pra `calcular_insights_repertorio` e serializa o
    resultado, sem reimplementar aquele cálculo com um MagicMock encadeado
    de 4 tabelas diferentes.
    """

    def setUp(self) -> None:
        api_server._state.clear()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.get("/insights/repertorio")
            self.assertEqual(resposta.status_code, 401)

    def test_banco_indisponivel_retorna_503(self) -> None:
        resposta = self.client.get(
            "/insights/repertorio",
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 503)

    @patch("backend.api.api_server.calcular_insights_repertorio")
    def test_retorna_o_payload_calculado(self, mock_calcular: MagicMock) -> None:
        payload_esperado = {
            "taxa_vitoria_por_cor": {
                "BRANCAS": {"total": 10, "vitorias": 6, "taxa_vitoria_pct": 60.0}
            },
            "por_abertura_e_cor": [
                {
                    "abertura_normalizada": "Francesa",
                    "cor_jogada": "BRANCAS",
                    "total": 20,
                    "vitorias": 12,
                    "taxa_vitoria_pct": 60.0,
                    "precisao_media_abertura": None,
                    "precisao_media_meiojogo": None,
                    "precisao_media_final": None,
                }
            ],
            "lance_pico_por_abertura": [],
            "categorias_por_abertura": {},
        }
        mock_calcular.return_value = payload_esperado
        api_server._state["supabase_client"] = MagicMock()

        resposta = self.client.get(
            "/insights/repertorio",
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), payload_esperado)
        # D-30: o dono da sessão também é repassado, não só o client.
        mock_calcular.assert_called_once_with(
            api_server._state["supabase_client"], USER_ID_TESTE
        )

    @patch("backend.api.api_server.calcular_insights_repertorio")
    def test_filtra_pelo_dono_real_da_sessao(self, mock_calcular: MagicMock) -> None:
        """D-30: sem isso, a rota (e o cálculo por trás) misturava dado de todo mundo."""
        mock_calcular.return_value = {
            "taxa_vitoria_por_cor": {},
            "por_abertura_e_cor": [],
            "lance_pico_por_abertura": [],
            "categorias_por_abertura": {},
        }
        user_id_sessao = "99999999-8888-7777-6666-555555555555"
        mock_client = MagicMock()
        mock_user_response = MagicMock()
        mock_user_response.user.id = user_id_sessao
        mock_client.auth.get_user.return_value = mock_user_response
        api_server._state["supabase_client"] = mock_client

        with gate_de_sessao_real():
            resposta = self.client.get(
                "/insights/repertorio",
                headers=HEADERS_SESSAO,
            )

        self.assertEqual(resposta.status_code, 200)
        mock_calcular.assert_called_once_with(mock_client, user_id_sessao)

    @patch("backend.api.api_server.calcular_insights_repertorio")
    def test_falha_no_calculo_retorna_500(self, mock_calcular: MagicMock) -> None:
        mock_calcular.side_effect = RuntimeError("consulta falhou")
        api_server._state["supabase_client"] = MagicMock()

        resposta = self.client.get(
            "/insights/repertorio",
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 500)


class InsightsPuzzlesEndpointTest(unittest.TestCase):
    """Testes do endpoint GET /insights/puzzles."""

    def setUp(self) -> None:
        api_server._state.clear()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.get("/insights/puzzles")
            self.assertEqual(resposta.status_code, 401)

    def test_banco_indisponivel_retorna_503(self) -> None:
        resposta = self.client.get(
            "/insights/puzzles",
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 503)

    @patch("backend.api.api_server.calcular_insights_puzzles")
    def test_retorna_o_payload_calculado(self, mock_calcular: MagicMock) -> None:
        payload_esperado = {
            "resumo": {
                "total": 50,
                "acertos": 35,
                "erros": 15,
                "taxa_acerto_pct": 70.0,
                "rating_medio": 1850.0,
                "rating_min": 1500,
                "rating_max": 2100,
            },
            "temas_vulneraveis": [
                {
                    "slug": "defensiveMove",
                    "nome": "Lance Defensivo",
                    "descricao": "Defesa",
                    "categoria": "defesa",
                    "total": 10,
                    "acertos": 4,
                    "taxa_acerto_pct": 40.0,
                    "url_treino": "https://lichess.org/training/defensiveMove",
                }
            ],
            "temas_dominados": [
                {
                    "slug": "mateIn1",
                    "nome": "Mate em 1 lance",
                    "descricao": "Mate",
                    "categoria": "mate",
                    "total": 10,
                    "acertos": 10,
                    "taxa_acerto_pct": 100.0,
                    "url_treino": "https://lichess.org/training/mateIn1",
                }
            ],
            "todos_os_temas": [],
            "diagnostico_gap": {
                "titulo": "Gap Tático",
                "resumo_executivo": "Resumo",
                "analise_comparativa": "Comparativo",
                "sugestao_foco": "Foco",
            },
        }
        mock_calcular.return_value = payload_esperado
        api_server._state["supabase_client"] = MagicMock()

        resposta = self.client.get(
            "/insights/puzzles",
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), payload_esperado)
        mock_calcular.assert_called_once_with(
            api_server._state["supabase_client"], USER_ID_TESTE
        )

    @patch("backend.api.api_server.calcular_insights_puzzles")
    def test_filtra_pelo_dono_real_da_sessao(self, mock_calcular: MagicMock) -> None:
        mock_calcular.return_value = {
            "resumo": {},
            "temas_vulneraveis": [],
            "temas_dominados": [],
            "todos_os_temas": [],
            "diagnostico_gap": {},
        }
        user_id_sessao = "99999999-8888-7777-6666-555555555555"
        mock_client = MagicMock()
        mock_user_response = MagicMock()
        mock_user_response.user.id = user_id_sessao
        mock_client.auth.get_user.return_value = mock_user_response
        api_server._state["supabase_client"] = mock_client

        with gate_de_sessao_real():
            resposta = self.client.get(
                "/insights/puzzles",
                headers=HEADERS_SESSAO,
            )

        self.assertEqual(resposta.status_code, 200)
        mock_calcular.assert_called_once_with(mock_client, user_id_sessao)

    @patch("backend.api.api_server.calcular_insights_puzzles")
    def test_falha_no_calculo_retorna_500(self, mock_calcular: MagicMock) -> None:
        mock_calcular.side_effect = RuntimeError("consulta falhou")
        api_server._state["supabase_client"] = MagicMock()

        resposta = self.client.get(
            "/insights/puzzles",
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 500)


class TeoriaAberturaEndpointTest(unittest.TestCase):
    """Testes do endpoint GET /partidas/{partida_id}/teoria-abertura."""

    def setUp(self) -> None:
        api_server._state.clear()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.get("/partidas/partida-123/teoria-abertura")
            self.assertEqual(resposta.status_code, 401)

    def test_banco_indisponivel_retorna_503(self) -> None:
        resposta = self.client.get(
            "/partidas/partida-123/teoria-abertura",
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 503)

    def test_partida_nao_encontrada_retorna_404(self) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_resp
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get(
            "/partidas/inexistente/teoria-abertura",
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 404)

    @patch("backend.api.api_server.obter_access_token_lichess")
    @patch("backend.api.api_server.detectar_saida_teoria")
    def test_detecta_teoria_com_sucesso(
        self, mock_detectar: MagicMock, mock_token: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [
            {"id": "partida-123", "pgn": "1. e4 e5 2. Nf3 *", "cor_jogada": "BRANCAS"}
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_resp
        api_server._state["supabase_client"] = mock_client

        mock_token.return_value = "token-teste"
        mock_detectar.return_value = {
            "sucesso": True,
            "disponivel": True,
            "ply_saida": 4,
            "nome_abertura": "King's Pawn Opening",
        }

        resposta = self.client.get(
            "/partidas/partida-123/teoria-abertura",
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["nome_abertura"], "King's Pawn Opening")
        mock_detectar.assert_called_once_with(
            "1. e4 e5 2. Nf3 *", token="token-teste", cor_jogada="BRANCAS"
        )


class SyzygyEndpointTest(unittest.TestCase):
    """Testes do endpoint GET /analise/syzygy."""

    def setUp(self) -> None:
        api_server._state.clear()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.get(
                "/analise/syzygy",
                params={"fen": "8/8/8/4k3/8/8/4Q3/4K3 b - - 0 1"},
            )
            self.assertEqual(resposta.status_code, 401)

    @patch("backend.api.api_server.consultar_syzygy")
    def test_consulta_apenas_fen(self, mock_consultar: MagicMock) -> None:
        mock_consultar.return_value = {"category": "win", "dtz": 5}
        resposta = self.client.get(
            "/analise/syzygy",
            params={"fen": "8/8/8/4k3/8/8/4Q3/4K3 b - - 0 1"},
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["elegivel_syzygy"])
        self.assertEqual(resposta.json()["dados"]["category"], "win")

    @patch("backend.api.api_server.avaliar_lance_final_syzygy")
    def test_consulta_com_lance(self, mock_avaliar: MagicMock) -> None:
        mock_avaliar.return_value = {
            "elegivel_syzygy": True,
            "eh_blunder_teorico": True,
            "tipo_erro_final": "erro_conversao",
        }
        resposta = self.client.get(
            "/analise/syzygy",
            params={"fen": "8/8/8/4k3/8/8/4Q3/4K3 w - - 0 1", "lance": "Kd2"},
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["eh_blunder_teorico"])
        self.assertEqual(resposta.json()["tipo_erro_final"], "erro_conversao")

    @patch("backend.api.api_server.consultar_syzygy")
    def test_fen_inelegivel_retorna_elegivel_false(self, mock_consultar: MagicMock) -> None:
        mock_consultar.return_value = None
        resposta = self.client.get(
            "/analise/syzygy",
            params={"fen": "posicao_invalida"},
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.json()["elegivel_syzygy"])



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
        api_server._state["supabase_client"] = MagicMock()
        api_server._state["gemini_client"] = MagicMock()
        api_server._state["engine_lock"] = threading.Lock()
        # Mock logger isola completamente a saída de testes de prints/logs
        api_server._state["logger"] = MagicMock()
        # partidas é tabela raiz: inserir_partida exige user_id (D-14); sem
        # Authorization Bearer nestes testes, cai no fallback DEFAULT_USER_ID (D-17).
        self._env = patch.dict(os.environ, {"DEFAULT_USER_ID": USER_ID_TESTE})
        self._env.start()
        self.addCleanup(self._env.stop)
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.post(
                "/analisar-pgn",
                json={"pgn": self.PGN_TESTE},
            )
            self.assertEqual(resposta.status_code, 401)

    def test_pgn_vazio_recebe_400(self) -> None:
        resposta = self.client.post(
            "/analisar-pgn",
            json={"pgn": "   "},
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("PGN não fornecido", resposta.json()["detail"])

    def test_pgn_invalido_recebe_400(self) -> None:
        resposta = self.client.post(
            "/analisar-pgn",
            json={"pgn": "isso aqui nao e xadrez"},
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 400)

    @patch("backend.agentes.analisar_pgn_avulso.inferir_cor_jogador", return_value=None)
    def test_sem_cor_e_sem_inferencia_recebe_422(self, mock_inferir) -> None:
        resposta = self.client.post(
            "/analisar-pgn",
            json={"pgn": self.PGN_SEM_USERNAMES, "cor": None},
            headers=HEADERS_SESSAO,
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
            headers=HEADERS_SESSAO,
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
        # O dono vem da sessao (override do modulo injeta USER_ID_TESTE).
        _, kwargs_inserir = mock_inserir.call_args
        self.assertEqual(kwargs_inserir["user_id"], USER_ID_TESTE)

    @patch("backend.api.api_server.load_analysis_settings")
    @patch("backend.api.api_server.load_linter_settings")
    @patch("backend.api.api_server.executar_pipeline_partida")
    def test_analisar_pgn_com_sessao_valida_usa_user_id_real(
        self, mock_executar_pipeline, mock_linter, mock_analysis
    ) -> None:
        # Gate real (sem override), SEM mockar inserir_partida: prova a amarração
        # de ponta a ponta, do token até o payload que vai pro Supabase (D-25).
        user_id_sessao = "99999999-8888-7777-6666-555555555555"
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = [{"id": "partida-real-001"}]
        mock_client.table.return_value.upsert.return_value.execute.return_value = resp_mock
        mock_user_response = MagicMock()
        mock_user_response.user.id = user_id_sessao
        mock_client.auth.get_user.return_value = mock_user_response
        api_server._state["supabase_client"] = mock_client

        with gate_de_sessao_real():
            resposta = self.client.post(
                "/analisar-pgn",
                json={"pgn": self.PGN_TESTE, "cor": "BRANCAS"},
                headers=HEADERS_SESSAO,
            )

        self.assertEqual(resposta.status_code, 202)
        mock_client.auth.get_user.assert_called_once_with(TOKEN_TESTE)
        payload = mock_client.table.return_value.upsert.call_args[0][0]
        self.assertEqual(payload["user_id"], user_id_sessao)

    @patch("backend.api.api_server.load_analysis_settings")
    @patch("backend.api.api_server.load_linter_settings")
    @patch("backend.api.api_server.executar_pipeline_partida")
    @patch("backend.api.api_server.inserir_partida", return_value="partida_777")
    def test_infere_cor_pelo_perfil_de_quem_esta_logado(
        self, mock_inserir, mock_executar_pipeline, mock_linter, mock_analysis
    ) -> None:
        """D-28: o auto-detect usa o perfil de QUEM CHAMOU, não um username fixo.

        Sem isso, colar o PGN de outra pessoa logada nunca detectaria a cor
        dela sozinho - só reconheceria o dono de sempre.
        """
        perfil_mock = MagicMock()
        perfil_mock.data = {"lichess_username": "opponent123", "chesscom_username": None}
        api_server._state["supabase_client"].table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = perfil_mock

        resposta = self.client.post(
            "/analisar-pgn",
            json={"pgn": self.PGN_TESTE, "cor": None},
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 202)
        args, _kwargs = mock_inserir.call_args
        self.assertEqual(args[3], "PRETAS")

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
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 202)
        dados = resposta.json()
        self.assertEqual(dados["partida_id"], "partida_888")
        mock_inserir.assert_called_once()
        # Argumento cor passado para inserir_partida deve ser "BRANCAS"
        args, kwargs = mock_inserir.call_args
        self.assertEqual(args[3], "BRANCAS")
        self.assertEqual(kwargs["user_id"], USER_ID_TESTE)

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

    def test_obter_resumo_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.get("/partidas/partida_123/resumo")
            self.assertEqual(resposta.status_code, 401)

    def test_obter_resumo_partida_inexistente_recebe_404(self) -> None:
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get(
            "/partidas/partida_inexistente/resumo",
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 404)
        self.assertIn("não encontrada", resposta.json()["detail"])

    def test_obter_resumo_filtra_pelo_dono_da_sessao(self) -> None:
        """D-29: sem o filtro por user_id, qualquer sessão lia o resumo de QUALQUER partida."""
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get(
            "/partidas/partida-de-outro-dono/resumo",
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 404)
        mock_client.table.return_value.select.return_value.eq.assert_called_once_with(
            "id", "partida-de-outro-dono"
        )
        mock_client.table.return_value.select.return_value.eq.return_value.eq.assert_called_once_with(
            "user_id", USER_ID_TESTE
        )

    def test_obter_resumo_partida_processando_retorna_resumo_nulo(self) -> None:
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = [{"id": "p1", "external_id": "ext1", "status_processamento": "processando"}]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get(
            "/partidas/p1/resumo",
            headers=HEADERS_SESSAO,
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
                mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = resp
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
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["partida_id"], "p2")
        self.assertEqual(dados["status"], "concluido")
        self.assertIsNotNone(dados["resumo"])
        self.assertIn("Siciliana", dados["resumo"]["narrativa"])
        self.assertEqual(len(dados["resumo"]["pontos_criticos"]), 1)

    def test_obter_resumo_partida_anexa_fen_aos_pontos_criticos(self) -> None:
        """O FEN mora em lances_criticos, não no JSON do resumo: a junção é
        feita na leitura para que partidas analisadas antes desta mudança
        também ganhem miniatura, sem reprocessar nada."""
        fen_lance_15 = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
        mock_client = MagicMock()

        def table_side_effect(table_name: str):
            mock_table = MagicMock()
            if table_name == "partidas":
                resp = MagicMock()
                resp.data = [{"id": "p3", "external_id": None, "status_processamento": "concluido"}]
                mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = resp
            elif table_name == "resumo_partida":
                resp = MagicMock()
                resp.data = [{
                    "narrativa": "…",
                    "pontos_criticos": [
                        {"numero_lance": 15, "tipo_evento": "PICO", "tags_falha": []},
                        {"numero_lance": 22, "tipo_evento": "EROSAO", "tags_falha": []},
                    ],
                    "momento_chave_estrategico": "",
                }]
                mock_table.select.return_value.eq.return_value.execute.return_value = resp
            elif table_name == "lances_criticos":
                resp = MagicMock()
                # O lance 22 não tem FEN gravado (linha anterior ao D-27).
                resp.data = [
                    {"numero_lance": 15, "fen_antes_lance": fen_lance_15},
                    {"numero_lance": 22, "fen_antes_lance": None},
                ]
                mock_table.select.return_value.eq.return_value.execute.return_value = resp
            return mock_table

        mock_client.table.side_effect = table_side_effect
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get("/partidas/p3/resumo", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        pontos = resposta.json()["resumo"]["pontos_criticos"]
        self.assertEqual(pontos[0]["fen"], fen_lance_15)
        self.assertNotIn("fen", pontos[1])

    def test_obter_resumo_partida_sobrevive_a_falha_ao_buscar_fen(self) -> None:
        """A miniatura é enfeite: se a consulta de lances_criticos cair, o
        resumo ainda precisa chegar inteiro na tela."""
        mock_client = MagicMock()

        def table_side_effect(table_name: str):
            mock_table = MagicMock()
            if table_name == "partidas":
                resp = MagicMock()
                resp.data = [{"id": "p4", "external_id": None, "status_processamento": "concluido"}]
                mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = resp
            elif table_name == "resumo_partida":
                resp = MagicMock()
                resp.data = [{
                    "narrativa": "Narrativa preservada.",
                    "pontos_criticos": [{"numero_lance": 15, "tipo_evento": "PICO", "tags_falha": []}],
                    "momento_chave_estrategico": "",
                }]
                mock_table.select.return_value.eq.return_value.execute.return_value = resp
            elif table_name == "lances_criticos":
                mock_table.select.return_value.eq.return_value.execute.side_effect = RuntimeError(
                    "banco fora do ar"
                )
            return mock_table

        mock_client.table.side_effect = table_side_effect
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get("/partidas/p4/resumo", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["resumo"]["narrativa"], "Narrativa preservada.")
        self.assertNotIn("fen", dados["resumo"]["pontos_criticos"][0])

    def test_listar_partidas_recentes_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
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
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get(
            "/partidas/recentes",
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 200)
        itens = resposta.json()
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["partida_id"], "p-1")
        self.assertEqual(itens[0]["status"], "processando")
        self.assertEqual(itens[0]["jogadores"], "hirano28 vs oponente")
        self.assertEqual(itens[0]["eco_abertura"], "B90")
        # Sem Authorization: Bearer, o filtro cai no DEFAULT_USER_ID (D-18).
        mock_client.table.return_value.select.return_value.eq.return_value.eq.assert_called_once_with(
            "user_id", USER_ID_TESTE
        )

    def test_listar_partidas_recentes_inclui_fen_final_para_miniatura(self) -> None:
        """A miniatura do histórico depende deste campo — sem ele, a lista de
        partidas volta a ser só texto e não dá pra bater o olho e reconhecer."""
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = [
            {
                "id": "p-1",
                "status_processamento": "concluido",
                "pgn": '[White "a"]\n[Black "b"]\n\n1. e4 c5 2. Nf3',
            }
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get("/partidas/recentes", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.json()[0]["fen_final"],
            "rnbqkbnr/pp1ppppp/8/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2",
        )

    def test_listar_partidas_recentes_com_pgn_invalido_nao_quebra(self) -> None:
        """PGN truncado/sem lances devolve fen_final nulo — a linha aparece sem
        miniatura, em vez de derrubar o histórico inteiro."""
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = [
            {"id": "p-1", "status_processamento": "falhou", "pgn": "isso não é um PGN"},
            {"id": "p-2", "status_processamento": "falhou", "pgn": None},
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get("/partidas/recentes", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        itens = resposta.json()
        self.assertIsNone(itens[0]["fen_final"])
        self.assertIsNone(itens[1]["fen_final"])

    def test_listar_partidas_recentes_filtra_pelo_user_id_da_sessao(self) -> None:
        with gate_de_sessao_real():
            # Fase B.3 (D-18): a listagem também respeita a sessão real, não só a escrita.
            user_id_sessao = "99999999-8888-7777-6666-555555555555"
            mock_client = MagicMock()
            resp_mock = MagicMock()
            resp_mock.data = []
            mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = resp_mock
            mock_user_response = MagicMock()
            mock_user_response.user.id = user_id_sessao
            mock_client.auth.get_user.return_value = mock_user_response
            api_server._state["supabase_client"] = mock_client

            resposta = self.client.get(
                "/partidas/recentes",
                headers=HEADERS_SESSAO,
            )

            self.assertEqual(resposta.status_code, 200)
            mock_client.table.return_value.select.return_value.eq.return_value.eq.assert_called_once_with(
                "user_id", user_id_sessao
            )

    def test_reprocessar_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.post("/partidas/p123/reprocessar")
            self.assertEqual(resposta.status_code, 401)

    def test_reprocessar_partida_inexistente_recebe_404(self) -> None:
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.post(
            "/partidas/inexistente/reprocessar",
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 404)

    def test_reprocessar_filtra_pelo_dono_da_sessao(self) -> None:
        """D-29: sem o filtro por user_id, qualquer sessão reagendava a análise de QUALQUER partida."""
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.post(
            "/partidas/partida-de-outro-dono/reprocessar",
            headers=HEADERS_SESSAO,
        )

        self.assertEqual(resposta.status_code, 404)
        mock_client.table.return_value.select.return_value.eq.assert_called_once_with(
            "id", "partida-de-outro-dono"
        )
        mock_client.table.return_value.select.return_value.eq.return_value.eq.assert_called_once_with(
            "user_id", USER_ID_TESTE
        )

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
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = resp_mock
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.post(
            "/partidas/p-existente/reprocessar",
            headers=HEADERS_SESSAO,
        )
        self.assertEqual(resposta.status_code, 202)
        dados = resposta.json()
        self.assertEqual(dados["partida_id"], "p-existente")
        self.assertEqual(dados["external_id"], "ext-existente")
        mock_update.assert_called_with(mock_client, "p-existente", "processando")
        mock_executar.assert_called_once()


class LimiteDiarioTest(unittest.TestCase):
    """A dependency isolada (D-32): incrementa via RPC, compara com o limite, barra com 429."""

    def setUp(self) -> None:
        api_server._state.clear()

    def tearDown(self) -> None:
        api_server._state.clear()

    def _client_com_contagem(self, contagem: int) -> MagicMock:
        mock_client = MagicMock()
        resposta = MagicMock()
        resposta.data = contagem
        mock_client.rpc.return_value.execute.return_value = resposta
        api_server._state["supabase_client"] = mock_client
        return mock_client

    def test_sob_o_limite_devolve_user_id_e_chama_o_rpc_com_o_p_user_id_e_p_rota_certos(self) -> None:
        mock_client = self._client_com_contagem(5)
        api_server._state["limites_diarios"] = {"rota-teste": 20}
        dependency = api_server.limite_diario("rota-teste")

        user_id = dependency(user_id=USER_ID_TESTE)

        self.assertEqual(user_id, USER_ID_TESTE)
        mock_client.rpc.assert_called_once_with(
            "incrementar_uso_diario",
            {"p_user_id": USER_ID_TESTE, "p_rota": "rota-teste"},
        )

    def test_exatamente_no_limite_ainda_passa(self) -> None:
        self._client_com_contagem(20)
        api_server._state["limites_diarios"] = {"rota-teste": 20}
        dependency = api_server.limite_diario("rota-teste")

        user_id = dependency(user_id=USER_ID_TESTE)

        self.assertEqual(user_id, USER_ID_TESTE)

    def test_estourando_o_limite_levanta_429_com_mensagem_clara(self) -> None:
        self._client_com_contagem(21)
        api_server._state["limites_diarios"] = {"rota-teste": 20}
        dependency = api_server.limite_diario("rota-teste")

        with self.assertRaises(HTTPException) as ctx:
            dependency(user_id=USER_ID_TESTE)

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.detail, api_server.MENSAGEM_LIMITE_DIARIO)

    def test_falha_no_rpc_retorna_500_em_vez_de_deixar_passar(self) -> None:
        mock_client = MagicMock()
        mock_client.rpc.return_value.execute.side_effect = RuntimeError("conexao caiu")
        api_server._state["supabase_client"] = mock_client
        api_server._state["limites_diarios"] = {"rota-teste": 20}
        dependency = api_server.limite_diario("rota-teste")

        with self.assertRaises(HTTPException) as ctx:
            dependency(user_id=USER_ID_TESTE)

        self.assertEqual(ctx.exception.status_code, 500)

    def test_sem_supabase_client_retorna_503(self) -> None:
        api_server._state["limites_diarios"] = {"rota-teste": 20}
        dependency = api_server.limite_diario("rota-teste")

        with self.assertRaises(HTTPException) as ctx:
            dependency(user_id=USER_ID_TESTE)

        self.assertEqual(ctx.exception.status_code, 503)

    def test_resolver_limites_diarios_le_env_vars_com_defaults_do_codigo(self) -> None:
        with patch.dict(os.environ, {"LIMITE_DIARIO_ANALISAR_PGN": "7"}, clear=False):
            limites = api_server._resolver_limites_diarios()

        self.assertEqual(limites["analisar-pgn"], 7)
        self.assertEqual(limites["explicar-posicao"], 50)
        self.assertEqual(limites["revisar-avulso"], 50)
        self.assertEqual(limites["reconhecer-posicao"], 30)


class LimiteDiarioIntegracaoRevisarAvulsoTest(unittest.TestCase):
    """Confirma, através da rota de verdade, que o 429 barra ANTES do Stockfish rodar."""

    PAYLOAD = {
        "posicao": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "lance": "e4",
        "pensamento": "x",
    }

    def setUp(self) -> None:
        api_server._state.clear()
        api_server._state["engine"] = MagicMock()
        api_server._state["gemini_client"] = MagicMock()
        api_server._state["settings"] = _fake_settings()
        api_server._state["logger"] = logging.getLogger("test_api_server")
        api_server._state["engine_lock"] = threading.Lock()
        api_server._state["limites_diarios"] = {"revisar-avulso": 2}
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_estourando_o_limite_recebe_429_e_nao_chama_o_motor(self) -> None:
        mock_client = MagicMock()
        resposta_rpc = MagicMock()
        resposta_rpc.data = 3  # acima do limite de 2 configurado no setUp
        mock_client.rpc.return_value.execute.return_value = resposta_rpc
        api_server._state["supabase_client"] = mock_client

        with gate_de_limite_diario_real(api_server.verificar_limite_revisar_avulso), patch.object(
            api_server, "processar_revisao_sequencia"
        ) as mock_processar:
            resposta = self.client.post(
                "/revisar-avulso", json=self.PAYLOAD, headers=HEADERS_SESSAO
            )

        self.assertEqual(resposta.status_code, 429)
        self.assertEqual(resposta.json()["detail"], api_server.MENSAGEM_LIMITE_DIARIO)
        mock_processar.assert_not_called()
        mock_client.rpc.assert_called_once_with(
            "incrementar_uso_diario",
            {"p_user_id": USER_ID_TESTE, "p_rota": "revisar-avulso"},
        )

    def test_dentro_do_limite_chama_o_motor_normalmente(self) -> None:
        mock_client = MagicMock()
        resposta_rpc = MagicMock()
        resposta_rpc.data = 1  # dentro do limite de 2
        mock_client.rpc.return_value.execute.return_value = resposta_rpc
        api_server._state["supabase_client"] = mock_client

        resultado = {
            "fen": chess_fen_inicial(),
            "lances": ["e4"],
            "lance_interpretado": "e4",
            "avaliacoes": [],
            "resumo_geral": None,
        }

        with gate_de_limite_diario_real(api_server.verificar_limite_revisar_avulso), patch.object(
            api_server, "processar_revisao_sequencia", return_value=resultado
        ) as mock_processar:
            resposta = self.client.post(
                "/revisar-avulso", json=self.PAYLOAD, headers=HEADERS_SESSAO
            )

        self.assertEqual(resposta.status_code, 200)
        mock_processar.assert_called_once()


class LimiteDiarioIntegracaoReprocessarTest(unittest.TestCase):
    """Auditoria pós-D-49: /reprocessar ganhou o mesmo teto das rotas caras do D-32."""

    def setUp(self) -> None:
        api_server._state.clear()
        api_server._state["limites_diarios"] = {"reprocessar": 2}
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_estourando_o_limite_recebe_429_e_nao_agenda_o_reprocessamento(self) -> None:
        mock_client = MagicMock()
        resposta_rpc = MagicMock()
        resposta_rpc.data = 3  # acima do limite de 2 configurado no setUp
        mock_client.rpc.return_value.execute.return_value = resposta_rpc
        api_server._state["supabase_client"] = mock_client

        with gate_de_limite_diario_real(api_server.verificar_limite_reprocessar), patch.object(
            api_server, "_executar_analise_pgn_background"
        ) as mock_executar_background:
            resposta = self.client.post(
                "/partidas/p-existente/reprocessar", headers=HEADERS_SESSAO
            )

        self.assertEqual(resposta.status_code, 429)
        self.assertEqual(resposta.json()["detail"], api_server.MENSAGEM_LIMITE_DIARIO)
        mock_executar_background.assert_not_called()
        # 429 antes até de consultar se a partida existe/pertence ao dono.
        mock_client.table.assert_not_called()

    def test_dentro_do_limite_agenda_normalmente(self) -> None:
        mock_client = MagicMock()
        resposta_rpc = MagicMock()
        resposta_rpc.data = 1  # dentro do limite de 2
        mock_client.rpc.return_value.execute.return_value = resposta_rpc
        resp_partida = MagicMock()
        resp_partida.data = [{"id": "p-existente", "external_id": "ext-existente"}]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = resp_partida
        api_server._state["supabase_client"] = mock_client

        with gate_de_limite_diario_real(api_server.verificar_limite_reprocessar), patch.object(
            api_server, "update_status"
        ) as mock_update_status, patch.object(
            api_server, "_executar_analise_pgn_background"
        ) as mock_executar_background:
            resposta = self.client.post(
                "/partidas/p-existente/reprocessar", headers=HEADERS_SESSAO
            )

        self.assertEqual(resposta.status_code, 202)
        mock_update_status.assert_called_once()
        mock_executar_background.assert_called_once()


class LimiteDiarioIntegracaoTreinoResponderTest(unittest.TestCase):
    """Auditoria pós-D-49: /treino/{id}/responder ganhou um teto (bem mais alto,
    já que o próprio D-48 quer permitir muitas repetições por dia)."""

    def setUp(self) -> None:
        api_server._state.clear()
        api_server._state["engine"] = MagicMock()
        api_server._state["engine_lock"] = threading.Lock()
        api_server._state["settings"] = _fake_settings()
        api_server._state["limites_diarios"] = {"treino-responder": 2}
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_estourando_o_limite_recebe_429_e_nao_chama_o_stockfish(self) -> None:
        mock_client = MagicMock()
        resposta_rpc = MagicMock()
        resposta_rpc.data = 3  # acima do limite de 2 configurado no setUp
        mock_client.rpc.return_value.execute.return_value = resposta_rpc
        api_server._state["supabase_client"] = mock_client

        with gate_de_limite_diario_real(api_server.verificar_limite_treino_responder), patch.object(
            api_server, "avaliar_lance_avulso"
        ) as mock_avaliar:
            resposta = self.client.post(
                "/treino/7/responder", json={"lance": "e4"}, headers=HEADERS_SESSAO
            )

        self.assertEqual(resposta.status_code, 429)
        self.assertEqual(resposta.json()["detail"], api_server.MENSAGEM_LIMITE_DIARIO)
        mock_avaliar.assert_not_called()
        # 429 antes até de consultar a linha da fila.
        mock_client.table.assert_not_called()

    def test_dentro_do_limite_avalia_normalmente(self) -> None:
        mock_client = MagicMock()
        resposta_rpc = MagicMock()
        resposta_rpc.data = 1  # dentro do limite de 2
        mock_client.rpc.return_value.execute.return_value = resposta_rpc
        resp_fila = MagicMock()
        resp_fila.data = [
            {
                "id": 7,
                "lance_id": "lance-uuid-1",
                "origem": "lance_critico",
                "intervalo_dias": 0,
                "fator_facilidade": 2.5,
                "repeticoes": 0,
                "total_revisoes": 0,
                "livro_citado": None,
                "capitulo_citado": None,
                "pagina_citada": None,
                "lances_criticos": {"fen_antes_lance": chess_fen_inicial()},
            }
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = resp_fila
        # Consulta a diagnosticos (causa raiz/tags) do card lance_critico: sem
        # linha encontrada, caminho válido (diagnostico vira {}), não um erro.
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        api_server._state["supabase_client"] = mock_client
        avaliacao_fake = AvaliacaoLance(
            lance_jogado="e4",
            melhor_lance="e4",
            queda_win_percent=0.5,
            linha_principal=["e4", "e5"],
            top_candidatos=[],
        )

        with gate_de_limite_diario_real(api_server.verificar_limite_treino_responder), patch.object(
            api_server, "avaliar_lance_avulso", return_value=avaliacao_fake
        ) as mock_avaliar:
            resposta = self.client.post(
                "/treino/7/responder", json={"lance": "e4"}, headers=HEADERS_SESSAO
            )

        self.assertEqual(resposta.status_code, 200)
        mock_avaliar.assert_called_once()


class PkceTest(unittest.TestCase):
    """O par PKCE precisa bater com a RFC 7636 — senão o Lichess recusa o S256."""

    def test_code_challenge_e_o_sha256_do_verifier_em_base64url_sem_padding(self) -> None:
        code_verifier, code_challenge = api_server._gerar_par_pkce()

        esperado = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
            .decode("ascii")
            .rstrip("=")
        )
        self.assertEqual(code_challenge, esperado)
        self.assertNotIn("=", code_challenge)

    def test_verifier_respeita_o_tamanho_e_o_alfabeto_exigidos(self) -> None:
        code_verifier, _ = api_server._gerar_par_pkce()

        self.assertGreaterEqual(len(code_verifier), 43)
        self.assertLessEqual(len(code_verifier), 128)
        self.assertRegex(code_verifier, r"^[A-Za-z0-9\-._~]+$")

    def test_cada_chamada_gera_um_verifier_diferente(self) -> None:
        primeiro, _ = api_server._gerar_par_pkce()
        segundo, _ = api_server._gerar_par_pkce()

        self.assertNotEqual(primeiro, segundo)


class IniciarOauthLichessTest(unittest.TestCase):
    """POST /lichess/oauth/iniciar: monta a URL e guarda o verifier no servidor."""

    def setUp(self) -> None:
        api_server._state.clear()
        api_server._state["lichess_oauth"] = {
            "client_id": "chess-ai-pipeline",
            "redirect_uri": "http://localhost:8000/lichess/oauth/callback",
            "scopes": "puzzle:read",
            "frontend_url": "http://localhost:4200",
        }
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_monta_a_url_de_autorizacao_com_os_parametros_do_pkce(self) -> None:
        api_server._state["supabase_client"] = MagicMock()

        resposta = self.client.post("/lichess/oauth/iniciar", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        url = resposta.json()["url_autorizacao"]
        self.assertTrue(url.startswith("https://lichess.org/oauth?"))
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], ["chess-ai-pipeline"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["scope"], ["puzzle:read"])
        self.assertEqual(
            query["redirect_uri"], ["http://localhost:8000/lichess/oauth/callback"]
        )
        self.assertTrue(query["code_challenge"][0])
        self.assertTrue(query["state"][0])

    def test_guarda_o_state_amarrado_ao_user_id_da_sessao(self) -> None:
        mock_client = MagicMock()
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.post("/lichess/oauth/iniciar", headers=HEADERS_SESSAO)

        gravado = mock_client.table.return_value.insert.call_args[0][0]
        self.assertEqual(gravado["user_id"], USER_ID_TESTE)
        query = parse_qs(urlparse(resposta.json()["url_autorizacao"]).query)
        self.assertEqual(gravado["state"], query["state"][0])

    def test_o_code_verifier_fica_no_banco_e_nunca_na_resposta(self) -> None:
        mock_client = MagicMock()
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.post("/lichess/oauth/iniciar", headers=HEADERS_SESSAO)

        gravado = mock_client.table.return_value.insert.call_args[0][0]
        corpo = resposta.text
        self.assertTrue(gravado["code_verifier"])
        # O verifier é o segredo que faz o PKCE valer: se vazasse para o
        # navegador, interceptar o `code` voltaria a ser suficiente.
        self.assertNotIn(gravado["code_verifier"], corpo)

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.post("/lichess/oauth/iniciar")

        self.assertEqual(resposta.status_code, 401)


class CallbackOauthLichessTest(unittest.TestCase):
    """GET /lichess/oauth/callback: valida o state, troca o código, grava o token."""

    STATE = "state-aleatorio-de-teste"
    CODE = "codigo-devolvido-pelo-lichess"

    def setUp(self) -> None:
        api_server._state.clear()
        api_server._state["lichess_oauth"] = {
            "client_id": "chess-ai-pipeline",
            "redirect_uri": "http://localhost:8000/lichess/oauth/callback",
            "scopes": "puzzle:read",
            "frontend_url": "http://localhost:4200",
        }
        self.client = TestClient(api_server.app, follow_redirects=False)

    def tearDown(self) -> None:
        api_server._state.clear()

    def _client_com_state(self, expires_at: datetime | None = None) -> MagicMock:
        mock_client = MagicMock()
        resposta = MagicMock()
        resposta.data = [
            {
                "state": self.STATE,
                "user_id": USER_ID_TESTE,
                "code_verifier": "verifier-guardado-no-servidor",
                "expires_at": (
                    expires_at or datetime.now(timezone.utc) + timedelta(minutes=5)
                ).isoformat(),
            }
        ]
        mock_client.table.return_value.delete.return_value.eq.return_value.execute.return_value = resposta
        api_server._state["supabase_client"] = mock_client
        return mock_client

    def _resposta_do_lichess(self, payload: dict) -> MagicMock:
        resposta = MagicMock()
        resposta.json.return_value = payload
        resposta.raise_for_status.return_value = None
        return resposta

    def test_fluxo_feliz_grava_o_token_do_dono_do_state_e_redireciona(self) -> None:
        mock_client = self._client_com_state()

        with patch.object(
            api_server.requests,
            "post",
            return_value=self._resposta_do_lichess(
                {"access_token": "token-real-do-lichess", "expires_in": 31536000}
            ),
        ) as mock_post:
            resposta = self.client.get(
                f"/lichess/oauth/callback?code={self.CODE}&state={self.STATE}"
            )

        self.assertEqual(resposta.status_code, 303)
        self.assertEqual(
            resposta.headers["location"], "http://localhost:4200/perfil?conectado=lichess"
        )
        enviado = mock_post.call_args.kwargs["data"]
        self.assertEqual(enviado["grant_type"], "authorization_code")
        self.assertEqual(enviado["code"], self.CODE)
        self.assertEqual(enviado["code_verifier"], "verifier-guardado-no-servidor")
        gravado = mock_client.table.return_value.upsert.call_args[0][0]
        self.assertEqual(gravado["user_id"], USER_ID_TESTE)
        self.assertEqual(gravado["access_token"], "token-real-do-lichess")
        self.assertEqual(gravado["scopes"], "puzzle:read")

    def test_nenhum_dado_sensivel_aparece_na_url_de_retorno(self) -> None:
        self._client_com_state()

        with patch.object(
            api_server.requests,
            "post",
            return_value=self._resposta_do_lichess(
                {"access_token": "token-real-do-lichess", "expires_in": 31536000}
            ),
        ):
            resposta = self.client.get(
                f"/lichess/oauth/callback?code={self.CODE}&state={self.STATE}"
            )

        destino = resposta.headers["location"]
        self.assertNotIn("token-real-do-lichess", destino)
        self.assertNotIn(self.CODE, destino)
        self.assertNotIn(self.STATE, destino)

    def test_state_desconhecido_nao_troca_codigo_nenhum(self) -> None:
        """CSRF: state forjado não existe na tabela, então o fluxo morre aqui."""
        mock_client = MagicMock()
        vazia = MagicMock()
        vazia.data = []
        mock_client.table.return_value.delete.return_value.eq.return_value.execute.return_value = vazia
        api_server._state["supabase_client"] = mock_client

        with patch.object(api_server.requests, "post") as mock_post:
            resposta = self.client.get(
                f"/lichess/oauth/callback?code={self.CODE}&state=forjado-por-atacante"
            )

        self.assertEqual(resposta.status_code, 303)
        self.assertIn("erro=lichess_state_invalido", resposta.headers["location"])
        mock_post.assert_not_called()

    def test_state_expirado_e_recusado(self) -> None:
        self._client_com_state(
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )

        with patch.object(api_server.requests, "post") as mock_post:
            resposta = self.client.get(
                f"/lichess/oauth/callback?code={self.CODE}&state={self.STATE}"
            )

        self.assertIn("erro=lichess_state_expirado", resposta.headers["location"])
        mock_post.assert_not_called()

    def test_state_e_consumido_em_uso_unico(self) -> None:
        """A linha é deletada na validação: replay do mesmo state não passa."""
        mock_client = self._client_com_state()

        with patch.object(
            api_server.requests,
            "post",
            return_value=self._resposta_do_lichess(
                {"access_token": "token-real-do-lichess", "expires_in": 31536000}
            ),
        ):
            self.client.get(
                f"/lichess/oauth/callback?code={self.CODE}&state={self.STATE}"
            )

        mock_client.table.return_value.delete.return_value.eq.assert_called_once_with(
            "state", self.STATE
        )

    def test_usuario_que_nega_no_lichess_volta_com_marcador_de_negado(self) -> None:
        api_server._state["supabase_client"] = MagicMock()

        resposta = self.client.get("/lichess/oauth/callback?error=access_denied")

        self.assertIn("erro=lichess_negado", resposta.headers["location"])

    def test_falha_na_troca_do_codigo_nao_grava_nada(self) -> None:
        mock_client = self._client_com_state()

        with patch.object(
            api_server.requests, "post", side_effect=RuntimeError("lichess fora do ar")
        ):
            resposta = self.client.get(
                f"/lichess/oauth/callback?code={self.CODE}&state={self.STATE}"
            )

        self.assertIn("erro=lichess_troca_falhou", resposta.headers["location"])
        mock_client.table.return_value.upsert.assert_not_called()


class ObterAccessTokenLichessTest(unittest.TestCase):
    """A função por onde todo consumidor futuro deve pegar o token (D-33)."""

    def setUp(self) -> None:
        api_server._state.clear()

    def tearDown(self) -> None:
        api_server._state.clear()

    def _client_com_token(self, expires_at: str | None) -> MagicMock:
        mock_client = MagicMock()
        resposta = MagicMock()
        resposta.data = [{"access_token": "token-valido", "expires_at": expires_at}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = resposta
        return mock_client

    def test_token_valido_e_devolvido(self) -> None:
        futuro = (datetime.now(timezone.utc) + timedelta(days=300)).isoformat()

        token = api_server.obter_access_token_lichess(
            self._client_com_token(futuro), USER_ID_TESTE
        )

        self.assertEqual(token, "token-valido")

    def test_token_expirado_devolve_none_em_vez_de_token_morto(self) -> None:
        passado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

        token = api_server.obter_access_token_lichess(
            self._client_com_token(passado), USER_ID_TESTE
        )

        self.assertIsNone(token)

    def test_conta_sem_lichess_conectado_devolve_none(self) -> None:
        mock_client = MagicMock()
        vazia = MagicMock()
        vazia.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = vazia

        token = api_server.obter_access_token_lichess(mock_client, USER_ID_TESTE)

        self.assertIsNone(token)


class StatusOauthLichessTest(unittest.TestCase):
    """GET /lichess/oauth/status: informa se o usuário logado tem token válido (D-35)."""

    def setUp(self) -> None:
        api_server._state.clear()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_usuario_conectado_com_token_valido(self) -> None:
        mock_client = MagicMock()
        futuro = (datetime.now(timezone.utc) + timedelta(days=300)).isoformat()
        resp = MagicMock()
        resp.data = [{"access_token": "token-valido", "expires_at": futuro}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get("/lichess/oauth/status", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertTrue(dados["conectado"])
        self.assertEqual(dados["expires_at"], futuro)

    def test_usuario_desconectado_retorna_falso(self) -> None:
        mock_client = MagicMock()
        vazia = MagicMock()
        vazia.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = vazia
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get("/lichess/oauth/status", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertFalse(dados["conectado"])
        self.assertIsNone(dados["expires_at"])

    def test_usuario_com_token_expirado_retorna_falso(self) -> None:
        mock_client = MagicMock()
        passado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        resp = MagicMock()
        resp.data = [{"access_token": "token-morto", "expires_at": passado}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.get("/lichess/oauth/status", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertFalse(dados["conectado"])

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.get("/lichess/oauth/status")

        self.assertEqual(resposta.status_code, 401)


class DesconectarOauthLichessTest(unittest.TestCase):
    """POST /lichess/oauth/desconectar: remove o token OAuth do usuário (D-35)."""

    def setUp(self) -> None:
        api_server._state.clear()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def test_desconectar_remove_token_do_user_id(self) -> None:
        mock_client = MagicMock()
        api_server._state["supabase_client"] = mock_client

        resposta = self.client.post("/lichess/oauth/desconectar", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"desconectado": True})
        mock_client.table.assert_called_with("lichess_oauth_tokens")
        mock_client.table.return_value.delete.return_value.eq.assert_called_once_with(
            "user_id", USER_ID_TESTE
        )

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.post("/lichess/oauth/desconectar")

        self.assertEqual(resposta.status_code, 401)


class ObterFilaTreinoTest(unittest.TestCase):
    """GET /treino/fila (D-48): lista os cards vencidos hoje, sem revelar a causa."""

    def setUp(self) -> None:
        api_server._state.clear()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def _mockar_client(self) -> MagicMock:
        mock_client = MagicMock()
        api_server._state["supabase_client"] = mock_client
        return mock_client

    def test_devolve_itens_sem_revelar_causa_do_erro(self) -> None:
        mock_client = self._mockar_client()
        base = mock_client.table.return_value.select.return_value.eq.return_value
        base.lte.return_value.order.return_value.execute.return_value.data = [
            {
                "id": 7,
                "repeticoes": 1,
                "total_revisoes": 2,
                "lances_criticos": {
                    "numero_lance": 14,
                    "fen_antes_lance": chess_fen_inicial(),
                    "partidas": {
                        "cor_jogada": "BRANCAS",
                        "data_partida": "2026-09-10",
                        "plataforma": "LICHESS",
                    },
                },
            }
        ]
        base.gt.return_value.gte.return_value.execute.return_value.data = []

        resposta = self.client.get("/treino/fila", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["feitas_hoje"], 0)
        self.assertEqual(corpo["total_hoje"], 1)
        item = corpo["itens"][0]
        self.assertEqual(item["fila_id"], 7)
        self.assertEqual(item["fen"], chess_fen_inicial())
        self.assertEqual(item["numero_lance"], 14)
        self.assertEqual(item["cor_jogada"], "BRANCAS")
        # Nenhum campo de diagnóstico (tags_falha, causa raiz, citação) existe
        # na resposta - é a garantia de que o card não vaza a resposta antes
        # do usuário tentar o lance.
        self.assertNotIn("tags_falha", item)
        self.assertNotIn("raiz_conceitual_violada", item)
        self.assertNotIn("livro_citado", item)

    def test_pula_item_sem_fen_registrada(self) -> None:
        mock_client = self._mockar_client()
        base = mock_client.table.return_value.select.return_value.eq.return_value
        base.lte.return_value.order.return_value.execute.return_value.data = [
            {
                "id": 1,
                "repeticoes": 0,
                "total_revisoes": 0,
                "lances_criticos": {"numero_lance": 3, "fen_antes_lance": None, "partidas": {}},
            }
        ]
        base.gt.return_value.gte.return_value.execute.return_value.data = []

        resposta = self.client.get("/treino/fila", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["itens"], [])

    def test_conta_feitas_hoje_separado_das_pendentes(self) -> None:
        mock_client = self._mockar_client()
        base = mock_client.table.return_value.select.return_value.eq.return_value
        base.lte.return_value.order.return_value.execute.return_value.data = []
        base.gt.return_value.gte.return_value.execute.return_value.data = [
            {"id": 1},
            {"id": 2},
            {"id": 3},
        ]

        resposta = self.client.get("/treino/fila", headers=HEADERS_SESSAO)

        corpo = resposta.json()
        self.assertEqual(corpo["feitas_hoje"], 3)
        self.assertEqual(corpo["total_hoje"], 3)
        self.assertEqual(corpo["itens"], [])

    def test_sem_supabase_devolve_503(self) -> None:
        resposta = self.client.get("/treino/fila", headers=HEADERS_SESSAO)
        self.assertEqual(resposta.status_code, 503)

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.get("/treino/fila")

        self.assertEqual(resposta.status_code, 401)

    def test_item_de_exercicio_tatico_devolve_origem_e_categoria(self) -> None:
        """D-49: card vindo do catálogo tático não tem numero_lance/cor_jogada,
        mas devolve origem+categoria pro frontend distinguir o selo."""
        mock_client = self._mockar_client()
        base = mock_client.table.return_value.select.return_value.eq.return_value
        base.lte.return_value.order.return_value.execute.return_value.data = [
            {
                "id": 9,
                "origem": "exercicio_tatico",
                "repeticoes": 0,
                "total_revisoes": 0,
                "exercicios_taticos": {
                    "fen": chess_fen_inicial(),
                    "categoria_hexagono": "TATICA",
                },
            }
        ]
        base.gt.return_value.gte.return_value.execute.return_value.data = []

        resposta = self.client.get("/treino/fila", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        item = resposta.json()["itens"][0]
        self.assertEqual(item["origem"], "exercicio_tatico")
        self.assertEqual(item["categoria"], "TATICA")
        self.assertIsNone(item["numero_lance"])
        self.assertIsNone(item["cor_jogada"])

    def test_pula_exercicio_tatico_sem_fen_registrada(self) -> None:
        mock_client = self._mockar_client()
        base = mock_client.table.return_value.select.return_value.eq.return_value
        base.lte.return_value.order.return_value.execute.return_value.data = [
            {
                "id": 9,
                "origem": "exercicio_tatico",
                "repeticoes": 0,
                "total_revisoes": 0,
                "exercicios_taticos": {"fen": None, "categoria_hexagono": "TATICA"},
            }
        ]
        base.gt.return_value.gte.return_value.execute.return_value.data = []

        resposta = self.client.get("/treino/fila", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["itens"], [])


class ResponderTreinoTest(unittest.TestCase):
    """POST /treino/{fila_id}/responder (D-48): avalia via Stockfish e reagenda."""

    def setUp(self) -> None:
        api_server._state.clear()
        api_server._state["engine"] = MagicMock()
        api_server._state["engine_lock"] = threading.Lock()
        api_server._state["settings"] = _fake_settings()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()

    def _mockar_fila(
        self, mock_client: MagicMock, fila_row: dict[str, Any] | None
    ) -> None:
        resposta = mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute
        resposta.return_value.data = [fila_row] if fila_row else []

    def _mockar_diagnostico(
        self, mock_client: MagicMock, diagnostico_row: dict[str, Any] | None
    ) -> None:
        resposta = mock_client.table.return_value.select.return_value.eq.return_value.execute
        resposta.return_value.data = [diagnostico_row] if diagnostico_row else []

    def test_card_inexistente_ou_de_outro_dono_devolve_404(self) -> None:
        mock_client = MagicMock()
        api_server._state["supabase_client"] = mock_client
        self._mockar_fila(mock_client, None)

        resposta = self.client.post(
            "/treino/999/responder", json={"lance": "e4"}, headers=HEADERS_SESSAO
        )

        self.assertEqual(resposta.status_code, 404)

    def test_lance_bom_devolve_qualidade_e_reagenda_para_amanha(self) -> None:
        mock_client = MagicMock()
        api_server._state["supabase_client"] = mock_client
        self._mockar_fila(
            mock_client,
            {
                "id": 7,
                "lance_id": "lance-uuid-1",
                "intervalo_dias": 0,
                "fator_facilidade": 2.5,
                "repeticoes": 0,
                "total_revisoes": 0,
                "livro_citado": "Meu Sistema",
                "capitulo_citado": "4",
                "pagina_citada": 88,
                "lances_criticos": {"fen_antes_lance": chess_fen_inicial()},
            },
        )
        self._mockar_diagnostico(
            mock_client,
            {
                "raiz_conceitual_violada": "Não avaliou o centro antes de decidir.",
                "tags_falha": ["calculo_tatico_deficiente"],
            },
        )
        avaliacao_fake = AvaliacaoLance(
            lance_jogado="e4",
            melhor_lance="e4",
            queda_win_percent=0.5,
            linha_principal=["e4", "e5"],
            top_candidatos=[],
        )

        with patch.object(api_server, "avaliar_lance_avulso", return_value=avaliacao_fake):
            resposta = self.client.post(
                "/treino/7/responder", json={"lance": "e4"}, headers=HEADERS_SESSAO
            )

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["qualidade_lance"], "BOM")
        self.assertEqual(corpo["melhor_lance"], "e4")
        self.assertEqual(
            corpo["raiz_conceitual_violada"], "Não avaliou o centro antes de decidir."
        )
        self.assertEqual(corpo["tags_falha"], ["calculo_tatico_deficiente"])
        self.assertEqual(corpo["livro_citado"], "Meu Sistema")
        self.assertEqual(corpo["repeticoes"], 1)

        # Reagendamento de verdade: 1ª repetição boa vira 1 dia (SM-2).
        payload_update = mock_client.table.return_value.update.call_args[0][0]
        self.assertEqual(payload_update["repeticoes"], 1)
        self.assertEqual(payload_update["intervalo_dias"], 1)
        self.assertEqual(payload_update["total_revisoes"], 1)
        mock_client.table.return_value.update.return_value.eq.assert_called_once_with(
            "id", 7
        )

    def test_lance_ruim_reseta_a_serie(self) -> None:
        mock_client = MagicMock()
        api_server._state["supabase_client"] = mock_client
        self._mockar_fila(
            mock_client,
            {
                "id": 7,
                "lance_id": "lance-uuid-1",
                "intervalo_dias": 30,
                "fator_facilidade": 2.8,
                "repeticoes": 5,
                "total_revisoes": 5,
                "livro_citado": None,
                "capitulo_citado": None,
                "pagina_citada": None,
                "lances_criticos": {"fen_antes_lance": chess_fen_inicial()},
            },
        )
        self._mockar_diagnostico(mock_client, None)
        avaliacao_ruim = AvaliacaoLance(
            lance_jogado="a3",
            melhor_lance="e4",
            queda_win_percent=25.0,
            linha_principal=[],
            top_candidatos=[],
        )

        with patch.object(api_server, "avaliar_lance_avulso", return_value=avaliacao_ruim):
            resposta = self.client.post(
                "/treino/7/responder", json={"lance": "a3"}, headers=HEADERS_SESSAO
            )

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["qualidade_lance"], "RUIM")
        self.assertEqual(corpo["repeticoes"], 0)
        payload_update = mock_client.table.return_value.update.call_args[0][0]
        self.assertEqual(payload_update["repeticoes"], 0)
        self.assertEqual(payload_update["intervalo_dias"], 1)

    def test_lance_ilegal_devolve_400(self) -> None:
        mock_client = MagicMock()
        api_server._state["supabase_client"] = mock_client
        self._mockar_fila(
            mock_client,
            {
                "id": 7,
                "lance_id": "lance-uuid-1",
                "intervalo_dias": 0,
                "fator_facilidade": 2.5,
                "repeticoes": 0,
                "total_revisoes": 0,
                "livro_citado": None,
                "capitulo_citado": None,
                "pagina_citada": None,
                "lances_criticos": {"fen_antes_lance": chess_fen_inicial()},
            },
        )

        resposta = self.client.post(
            "/treino/7/responder", json={"lance": "Txz9"}, headers=HEADERS_SESSAO
        )

        self.assertEqual(resposta.status_code, 400)

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.post("/treino/7/responder", json={"lance": "e4"})

        self.assertEqual(resposta.status_code, 401)

    def test_exercicio_tatico_nao_consulta_diagnosticos(self) -> None:
        """D-49: card de catálogo não tem diagnosticos associado - raiz/tags
        voltam vazias, sem tentar consultar uma tabela que não tem a ver."""
        mock_client = MagicMock()
        api_server._state["supabase_client"] = mock_client
        self._mockar_fila(
            mock_client,
            {
                "id": 9,
                "lance_id": None,
                "origem": "exercicio_tatico",
                "intervalo_dias": 0,
                "fator_facilidade": 2.5,
                "repeticoes": 0,
                "total_revisoes": 0,
                "livro_citado": "Livro X",
                "capitulo_citado": "2",
                "pagina_citada": 10,
                "exercicios_taticos": {"fen": chess_fen_inicial()},
            },
        )
        avaliacao_fake = AvaliacaoLance(
            lance_jogado="e4",
            melhor_lance="e4",
            queda_win_percent=0.5,
            linha_principal=["e4", "e5"],
            top_candidatos=[],
        )

        with patch.object(api_server, "avaliar_lance_avulso", return_value=avaliacao_fake):
            resposta = self.client.post(
                "/treino/9/responder", json={"lance": "e4"}, headers=HEADERS_SESSAO
            )

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["qualidade_lance"], "BOM")
        self.assertIsNone(corpo["raiz_conceitual_violada"])
        self.assertEqual(corpo["tags_falha"], [])
        self.assertEqual(corpo["livro_citado"], "Livro X")
        nomes_tabelas = [chamada.args[0] for chamada in mock_client.table.call_args_list]
        self.assertNotIn("diagnosticos", nomes_tabelas)


class FocarCategoriaTreinoTest(unittest.TestCase):
    """POST /treino/foco/{categoria} (D-49): injeta exercícios do catálogo
    tático na fila de hoje, focados numa categoria fraca."""

    def setUp(self) -> None:
        api_server._state.clear()
        _CACHE_CITACAO.clear()
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server._state.clear()
        _CACHE_CITACAO.clear()

    def _mockar_tabelas(
        self,
        ja_na_fila: list[dict[str, Any]],
        candidatos: list[dict[str, Any]],
    ) -> dict[str, MagicMock]:
        mocks: dict[str, MagicMock] = {}

        def table_side_effect(nome_tabela: str):
            mock_tabela = MagicMock()
            mocks[nome_tabela] = mock_tabela
            if nome_tabela == "fila_treino_espacado":
                resp = MagicMock()
                resp.data = ja_na_fila
                mock_tabela.select.return_value.eq.return_value.eq.return_value.execute.return_value = resp
            elif nome_tabela == "exercicios_taticos":
                resp = MagicMock()
                resp.data = candidatos
                mock_tabela.select.return_value.eq.return_value.execute.return_value = resp
            elif nome_tabela == "indice_conceitual":
                # buscar_conceitos (agente3_prescritor.py): sem conceito
                # indexado pra essa busca - resolver_citacao devolve None e a
                # linha fica com os 3 campos de citação nulos (não é erro).
                resp = MagicMock()
                resp.data = []
                mock_tabela.select.return_value.ilike.return_value.execute.return_value = resp
            return mock_tabela

        mock_client = MagicMock()
        mock_client.table.side_effect = table_side_effect
        api_server._state["supabase_client"] = mock_client
        return mocks

    def test_categoria_invalida_devolve_400(self) -> None:
        resposta = self.client.post("/treino/foco/NAO_EXISTE", headers=HEADERS_SESSAO)
        self.assertEqual(resposta.status_code, 400)

    def test_insere_exercicios_novos_da_categoria(self) -> None:
        candidatos = [{"id": f"ex-{i}"} for i in range(3)]
        mocks = self._mockar_tabelas(ja_na_fila=[], candidatos=candidatos)

        resposta = self.client.post("/treino/foco/TATICA", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["adicionados"], 3)
        upsert_mock = mocks["fila_treino_espacado"].upsert
        (linhas,), kwargs = upsert_mock.call_args
        self.assertEqual(len(linhas), 3)
        self.assertTrue(all(linha["origem"] == "exercicio_tatico" for linha in linhas))
        self.assertEqual(kwargs.get("on_conflict"), "user_id,exercicio_id")
        self.assertTrue(kwargs.get("ignore_duplicates"))

    def test_exclui_exercicios_ja_na_fila_do_usuario(self) -> None:
        candidatos = [{"id": "ex-1"}, {"id": "ex-2"}]
        mocks = self._mockar_tabelas(
            ja_na_fila=[{"exercicio_id": "ex-1"}], candidatos=candidatos
        )

        resposta = self.client.post("/treino/foco/TATICA", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["adicionados"], 1)
        upsert_mock = mocks["fila_treino_espacado"].upsert
        (linhas,), _ = upsert_mock.call_args
        self.assertEqual(linhas[0]["exercicio_id"], "ex-2")

    def test_sem_candidatos_novos_nao_chama_upsert(self) -> None:
        mocks = self._mockar_tabelas(
            ja_na_fila=[{"exercicio_id": "ex-1"}], candidatos=[{"id": "ex-1"}]
        )

        resposta = self.client.post("/treino/foco/TATICA", headers=HEADERS_SESSAO)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["adicionados"], 0)
        mocks["fila_treino_espacado"].upsert.assert_not_called()

    def test_sem_sessao_recebe_401(self) -> None:
        with gate_de_sessao_real():
            resposta = self.client.post("/treino/foco/TATICA")

        self.assertEqual(resposta.status_code, 401)


if __name__ == "__main__":
    unittest.main()


