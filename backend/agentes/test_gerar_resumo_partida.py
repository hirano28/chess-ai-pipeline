"""Testes unitários para gerar_resumo_partida.py."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from backend.agentes.gerar_resumo_partida import (
    DadosPartida,
    LanceCriticoComDiagnostico,
    PontoCritico,
    ResumoPartida,
    build_prompt_resumo,
    classificar_tags_por_hexagono,
    coletar_lances_permitidos,
    correction_prompt_narrativa,
    enriquecer_com_dados_motor,
    fallback_resumo,
    gerar_resumo_gemini,
    parse_resumo,
    reconstruir_posicao_antes,
    selecionar_evento_chave,
    strip_json_fences,
    validar_narrativa,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _lance_pico(
    numero: int = 15,
    notacao: str = "Bxf7+",
    tags: list[str] | None = None,
    diagnostico: str = "Perda de material por captura descuidada",
    queda: float = 25.0,
) -> LanceCriticoComDiagnostico:
    return LanceCriticoComDiagnostico(
        numero_lance=numero,
        numero_lance_fim=None,
        tipo_evento="PICO",
        lance_notacao=notacao,
        queda_win_percent=queda,
        avaliacao_antes_cp=50,
        avaliacao_depois_cp=-200,
        tags_falha=tags or ["perda_de_material", "calculo_tatico_deficiente"],
        diagnostico_mecanico=diagnostico,
        tipo_erro="CONTEUDO",
    )


def _lance_erosao(
    inicio: int = 20,
    fim: int = 28,
    tags: list[str] | None = None,
    diagnostico: str = "Perda gradual por passividade",
) -> LanceCriticoComDiagnostico:
    return LanceCriticoComDiagnostico(
        numero_lance=inicio,
        numero_lance_fim=fim,
        tipo_evento="EROSAO",
        lance_notacao=None,
        queda_win_percent=18.0,
        avaliacao_antes_cp=100,
        avaliacao_depois_cp=-50,
        tags_falha=tags or ["passividade_excessiva", "avaliacao_posicional_incorreta"],
        diagnostico_mecanico=diagnostico,
        tipo_erro="PROCESSO",
    )


def _dados_partida(
    lances: list[LanceCriticoComDiagnostico] | None = None,
    metricas: dict | None = None,
    apuro: int = 0,
    com_tempo: int = 0,
) -> DadosPartida:
    return DadosPartida(
        partida_id="test123",
        cor_jogada="BRANCAS",
        eco_abertura="B90",
        resultado="0-1",
        lances_criticos=lances or [_lance_pico(), _lance_erosao()],
        metricas_lichess=metricas,
        lances_em_apuro_de_tempo=apuro,
        total_lances_criticos_com_tempo=com_tempo,
    )


# ---------------------------------------------------------------------------
# Testes: classificar_tags_por_hexagono
# ---------------------------------------------------------------------------

class TestClassificarTagsPorHexagono(unittest.TestCase):
    """Testes para a classificação de tags_falha nas categorias do hexágono."""

    def test_tags_tatica_reconhecidas(self):
        resultado = classificar_tags_por_hexagono([
            "calculo_tatico_deficiente", "perda_de_material"
        ])
        self.assertEqual(resultado["TATICA"], 2)

    def test_tags_estrategia_reconhecidas(self):
        resultado = classificar_tags_por_hexagono([
            "avaliacao_posicional_incorreta", "simplificacao_prematura"
        ])
        self.assertEqual(resultado["ESTRATEGIA"], 2)

    def test_mix_de_categorias(self):
        resultado = classificar_tags_por_hexagono([
            "calculo_tatico_deficiente",
            "erro_tecnico_de_final",
            "gestao_de_tempo_ruim",
        ])
        self.assertEqual(resultado["TATICA"], 1)
        self.assertEqual(resultado["FINAIS"], 1)
        self.assertEqual(resultado["GESTAO_DE_TEMPO"], 1)

    def test_tag_desconhecida_ignorada(self):
        resultado = classificar_tags_por_hexagono(["tag_inexistente"])
        self.assertEqual(sum(resultado.values()), 0)

    def test_lista_vazia(self):
        resultado = classificar_tags_por_hexagono([])
        self.assertEqual(sum(resultado.values()), 0)

    def test_todas_categorias_presentes_na_saida(self):
        resultado = classificar_tags_por_hexagono(["perda_de_material"])
        self.assertIn("TATICA", resultado)
        self.assertIn("ESTRATEGIA", resultado)
        self.assertIn("FINAIS", resultado)
        self.assertIn("ESTRUTURA_DE_PEOES", resultado)
        self.assertIn("GESTAO_DE_TEMPO", resultado)
        self.assertIn("CALCULO", resultado)


# ---------------------------------------------------------------------------
# Testes: build_prompt_resumo
# ---------------------------------------------------------------------------

class TestBuildPromptResumo(unittest.TestCase):
    """Testes para a construção do prompt do Gemini."""

    def test_prompt_contem_dados_da_partida(self):
        dados = _dados_partida()
        prompt = build_prompt_resumo(dados)
        self.assertIn("test123", prompt)
        self.assertIn("BRANCAS", prompt)
        self.assertIn("B90", prompt)
        self.assertIn("0-1", prompt)

    def test_prompt_contem_lance_pico(self):
        dados = _dados_partida()
        prompt = build_prompt_resumo(dados)
        self.assertIn("PICO", prompt)
        self.assertIn("Bxf7+", prompt)
        self.assertIn("perda_de_material", prompt)

    def test_prompt_contem_erosao(self):
        dados = _dados_partida()
        prompt = build_prompt_resumo(dados)
        self.assertIn("EROSÃO", prompt)
        self.assertIn("20", prompt)
        self.assertIn("28", prompt)

    def test_prompt_contem_metricas_lichess(self):
        metricas = {"precisao_propria": 78, "acpl": 45, "blunders": 2, "erros": 3, "imprecisoes": 5}
        dados = _dados_partida(metricas=metricas)
        prompt = build_prompt_resumo(dados)
        self.assertIn("78", prompt)
        self.assertIn("45", prompt)

    def test_prompt_sem_metricas_lichess(self):
        dados = _dados_partida(metricas=None)
        prompt = build_prompt_resumo(dados)
        self.assertIn("não disponíveis", prompt)

    def test_prompt_contem_pressao_de_tempo(self):
        dados = _dados_partida(apuro=2, com_tempo=5)
        prompt = build_prompt_resumo(dados)
        self.assertIn("2 de 5", prompt)
        self.assertIn("apuro de tempo", prompt)

    def test_prompt_contem_schema_json(self):
        dados = _dados_partida()
        prompt = build_prompt_resumo(dados)
        self.assertIn("narrativa", prompt)
        self.assertIn("pontos_criticos", prompt)
        self.assertIn("momento_chave_estrategico", prompt)

    def test_prompt_lances_permitidos(self):
        dados = _dados_partida()
        prompt = build_prompt_resumo(dados)
        self.assertIn("Bxf7+", prompt)
        self.assertIn("Lances permitidos", prompt)


# ---------------------------------------------------------------------------
# Testes: validar_narrativa (anti-alucinação)
# ---------------------------------------------------------------------------

class TestValidarNarrativa(unittest.TestCase):
    """Testes para a validação anti-alucinação da narrativa."""

    def test_sem_alucinacao(self):
        lances = [_lance_pico(notacao="Bxf7+")]
        narrativa = "O lance Bxf7+ foi o momento decisivo da partida."
        inventados = validar_narrativa(narrativa, lances)
        self.assertEqual(inventados, [])

    def test_com_alucinacao_detectada(self):
        lances = [_lance_pico(notacao="Bxf7+")]
        narrativa = "O lance Nxe5 transformou a posição."
        inventados = validar_narrativa(narrativa, lances)
        self.assertIn("Nxe5", inventados)

    def test_texto_sem_lances_retorna_vazio(self):
        lances = [_lance_pico()]
        narrativa = "A partida foi equilibrada do início ao fim."
        inventados = validar_narrativa(narrativa, lances)
        self.assertEqual(inventados, [])

    def test_multiplos_lances_inventados(self):
        lances = [_lance_pico(notacao="Bxf7+")]
        narrativa = "Os lances Qd7, Rxe1 e Bxf7+ marcaram a partida."
        inventados = validar_narrativa(narrativa, lances)
        self.assertIn("Qd7", inventados)
        self.assertIn("Rxe1", inventados)
        self.assertNotIn("Bxf7+", inventados)

    def test_lance_sem_notacao_nao_afeta(self):
        lances = [_lance_erosao()]  # sem lance_notacao
        narrativa = "A erosão foi gradual e consistente."
        inventados = validar_narrativa(narrativa, lances)
        self.assertEqual(inventados, [])


# ---------------------------------------------------------------------------
# Testes: fallback_resumo
# ---------------------------------------------------------------------------

class TestFallbackResumo(unittest.TestCase):
    """Testes para a geração de resumo literal (sem LLM)."""

    def test_fallback_contem_dados_basicos(self):
        dados = _dados_partida()
        resumo = fallback_resumo(dados)
        self.assertIn("BRANCAS", resumo.narrativa)
        self.assertIn("B90", resumo.narrativa)
        self.assertIn("0-1", resumo.narrativa)

    def test_fallback_contem_picos(self):
        dados = _dados_partida(lances=[_lance_pico()])
        resumo = fallback_resumo(dados)
        self.assertIn("Bxf7+", resumo.narrativa)
        self.assertIn("perda_de_material", resumo.narrativa)

    def test_fallback_contem_erosoes(self):
        dados = _dados_partida(lances=[_lance_erosao()])
        resumo = fallback_resumo(dados)
        self.assertIn("Erosões", resumo.narrativa)
        self.assertIn("20", resumo.narrativa)

    def test_fallback_momento_chave_erosao_preferencial(self):
        dados = _dados_partida()
        resumo = fallback_resumo(dados)
        self.assertIn("Erosão", resumo.momento_chave_estrategico)

    def test_fallback_momento_chave_pico_quando_sem_erosao(self):
        dados = _dados_partida(lances=[_lance_pico()])
        resumo = fallback_resumo(dados)
        self.assertIn("Ponto crítico", resumo.momento_chave_estrategico)

    def test_fallback_pontos_criticos_populados(self):
        dados = _dados_partida()
        resumo = fallback_resumo(dados)
        self.assertEqual(len(resumo.pontos_criticos), 2)

    def test_fallback_com_apuro_de_tempo(self):
        dados = _dados_partida(apuro=3, com_tempo=5)
        resumo = fallback_resumo(dados)
        self.assertIn("apuro de tempo", resumo.narrativa)


# ---------------------------------------------------------------------------
# Testes: parse e utilitários
# ---------------------------------------------------------------------------

class TestParseResumo(unittest.TestCase):
    """Testes para o parsing da resposta JSON do Gemini."""

    def test_json_valido(self):
        json_str = json.dumps({
            "narrativa": "Resumo da partida.",
            "pontos_criticos": [
                {"numero_lance": 15, "tipo_evento": "PICO", "tags_falha": ["perda_de_material"]}
            ],
            "momento_chave_estrategico": "O lance 15 foi decisivo.",
        })
        resumo = parse_resumo(json_str)
        self.assertEqual(resumo.narrativa, "Resumo da partida.")
        self.assertEqual(len(resumo.pontos_criticos), 1)

    def test_json_com_fences_markdown(self):
        json_str = '```json\n{"narrativa": "Test", "pontos_criticos": [], "momento_chave_estrategico": "X"}\n```'
        resumo = parse_resumo(json_str)
        self.assertEqual(resumo.narrativa, "Test")

    def test_strip_json_fences(self):
        self.assertEqual(strip_json_fences('```json\n{"a":1}\n```'), '{"a":1}')
        self.assertEqual(strip_json_fences('{"a":1}'), '{"a":1}')


# ---------------------------------------------------------------------------
# Testes: correction_prompt_narrativa
# ---------------------------------------------------------------------------

class TestCorrectionPrompt(unittest.TestCase):
    """Testes para o prompt de correção anti-alucinação."""

    def test_prompt_contem_lances_inventados(self):
        prompt = correction_prompt_narrativa(
            "prompt original", ["Qd7", "Rxe1"], ["Bxf7+"]
        )
        self.assertIn("Qd7", prompt)
        self.assertIn("Rxe1", prompt)
        self.assertIn("INVENTADOS", prompt)
        self.assertIn("Bxf7+", prompt)


# ---------------------------------------------------------------------------
# Testes: gerar_resumo_gemini (com mocks)
# ---------------------------------------------------------------------------

class TestGerarResumoGemini(unittest.TestCase):
    """Testes para o fluxo completo de geração via Gemini."""

    def _mock_gemini_response(self, text: str) -> MagicMock:
        """Cria um mock de resposta do Gemini."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = text
        mock_client.models.generate_content.return_value = mock_response
        return mock_client

    def test_json_valido_sem_alucinacao(self):
        json_resposta = json.dumps({
            "narrativa": "O lance Bxf7+ foi o momento decisivo.",
            "pontos_criticos": [
                {"numero_lance": 15, "tipo_evento": "PICO", "tags_falha": ["perda_de_material"]}
            ],
            "momento_chave_estrategico": "O lance 15 foi decisivo.",
        })
        mock_client = self._mock_gemini_response(json_resposta)
        dados = _dados_partida(lances=[_lance_pico()])
        logger = MagicMock()

        resumo = gerar_resumo_gemini(mock_client, "prompt", dados, logger)

        self.assertIn("Bxf7+", resumo.narrativa)
        self.assertEqual(len(resumo.pontos_criticos), 1)

    def test_fallback_quando_parse_falha(self):
        mock_client = self._mock_gemini_response("resposta inválida sem JSON")
        dados = _dados_partida()
        logger = MagicMock()

        resumo = gerar_resumo_gemini(mock_client, "prompt", dados, logger)

        # Deve retornar fallback (contém dados reais literais)
        self.assertIn("BRANCAS", resumo.narrativa)

    def test_retry_alucinacao_e_corrige(self):
        # Primeira resposta tem alucinação, segunda corrige
        json_alucinado = json.dumps({
            "narrativa": "O lance Nxe5 foi decisivo na partida.",
            "pontos_criticos": [],
            "momento_chave_estrategico": "Momento X.",
        })
        json_corrigido = json.dumps({
            "narrativa": "O lance Bxf7+ foi o momento decisivo.",
            "pontos_criticos": [
                {"numero_lance": 15, "tipo_evento": "PICO", "tags_falha": ["perda_de_material"]}
            ],
            "momento_chave_estrategico": "Lance 15 decisivo.",
        })

        mock_client = MagicMock()
        response_1 = MagicMock()
        response_1.text = json_alucinado
        response_2 = MagicMock()
        response_2.text = json_corrigido
        mock_client.models.generate_content.side_effect = [response_1, response_2]

        dados = _dados_partida(lances=[_lance_pico()])
        logger = MagicMock()

        resumo = gerar_resumo_gemini(mock_client, "prompt", dados, logger)

        self.assertIn("Bxf7+", resumo.narrativa)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)

    def test_fallback_apos_alucinacao_persistente(self):
        # Ambas respostas têm alucinação
        json_alucinado = json.dumps({
            "narrativa": "O lance Nxe5 foi decisivo.",
            "pontos_criticos": [],
            "momento_chave_estrategico": "Momento.",
        })

        mock_client = MagicMock()
        response_mock = MagicMock()
        response_mock.text = json_alucinado
        mock_client.models.generate_content.return_value = response_mock

        dados = _dados_partida(lances=[_lance_pico()])
        logger = MagicMock()

        resumo = gerar_resumo_gemini(mock_client, "prompt", dados, logger)

        # Fallback literal
        self.assertIn("BRANCAS", resumo.narrativa)
        self.assertIn("Bxf7+", resumo.narrativa)


# ---------------------------------------------------------------------------
# Testes: coletar_dados_partida (mock Supabase)
# ---------------------------------------------------------------------------

class TestColetarDadosPartida(unittest.TestCase):
    """Testes para a coleta de dados do Supabase."""

    def _mock_supabase(
        self,
        partida_data: list,
        lances_data: list,
        metricas_data: list,
        tempos_data: list,
    ) -> MagicMock:
        """Cria um mock do client Supabase com respostas configuradas."""
        client = MagicMock()

        def table_handler(table_name: str) -> MagicMock:
            mock_table = MagicMock()
            if table_name == "partidas":
                resp = MagicMock()
                resp.data = partida_data
                mock_table.select.return_value.eq.return_value.execute.return_value = resp
            elif table_name == "lances_criticos":
                resp = MagicMock()
                resp.data = lances_data
                mock_table.select.return_value.eq.return_value.execute.return_value = resp
            elif table_name == "metricas_lichess_partida":
                resp = MagicMock()
                resp.data = metricas_data
                mock_table.select.return_value.eq.return_value.execute.return_value = resp
            elif table_name == "tempos_lance":
                resp = MagicMock()
                resp.data = tempos_data
                mock_table.select.return_value.eq.return_value.execute.return_value = resp
            return mock_table

        client.table.side_effect = table_handler
        return client

    def test_coleta_completa(self):
        from backend.agentes.gerar_resumo_partida import coletar_dados_partida

        client = self._mock_supabase(
            partida_data=[{
                "id": "abc",
                "cor_jogada": "BRANCAS",
                "eco_abertura": "B90",
                "resultado": "1-0",
            }],
            lances_data=[{
                "numero_lance": 15,
                "numero_lance_fim": None,
                "tipo_evento": "PICO",
                "lance_notacao": "Bxf7+",
                "queda_win_percent": 25.0,
                "avaliacao_antes_cp": 50,
                "avaliacao_depois_cp": -200,
                "diagnosticos": {
                    "tags_falha": ["perda_de_material"],
                    "diagnostico_mecanico": "Captura errada",
                    "tipo_erro": "CONTEUDO",
                },
            }],
            metricas_data=[{"precisao_propria": 78, "acpl": 45}],
            tempos_data=[{
                "numero_lance": 15,
                "cor": "BRANCAS",
                "tempo_restante_seg": 10.0,
                "tempo_gasto_seg": 1.5,
            }],
        )
        logger = MagicMock()

        dados = coletar_dados_partida(client, "abc", logger)

        self.assertEqual(dados.partida_id, "abc")
        self.assertEqual(dados.cor_jogada, "BRANCAS")
        self.assertEqual(len(dados.lances_criticos), 1)
        self.assertEqual(dados.lances_criticos[0].lance_notacao, "Bxf7+")
        self.assertIsNotNone(dados.metricas_lichess)
        self.assertEqual(dados.lances_em_apuro_de_tempo, 1)

    def test_sem_metricas_lichess(self):
        from backend.agentes.gerar_resumo_partida import coletar_dados_partida

        client = self._mock_supabase(
            partida_data=[{"id": "abc", "cor_jogada": "PRETAS", "eco_abertura": None, "resultado": None}],
            lances_data=[],
            metricas_data=[],
            tempos_data=[],
        )
        logger = MagicMock()

        dados = coletar_dados_partida(client, "abc", logger)

        self.assertIsNone(dados.metricas_lichess)
        self.assertEqual(len(dados.lances_criticos), 0)

    def test_lance_sem_diagnostico_ignorado(self):
        from backend.agentes.gerar_resumo_partida import coletar_dados_partida

        client = self._mock_supabase(
            partida_data=[{"id": "abc", "cor_jogada": "BRANCAS", "eco_abertura": "C50", "resultado": "1/2-1/2"}],
            lances_data=[{
                "numero_lance": 10,
                "numero_lance_fim": None,
                "tipo_evento": "PICO",
                "lance_notacao": "e4",
                "queda_win_percent": 5.0,
                "avaliacao_antes_cp": 0,
                "avaliacao_depois_cp": -50,
                "diagnosticos": None,  # Sem diagnóstico
            }],
            metricas_data=[],
            tempos_data=[],
        )
        logger = MagicMock()

        dados = coletar_dados_partida(client, "abc", logger)
        self.assertEqual(len(dados.lances_criticos), 0)


# ---------------------------------------------------------------------------
# Testes: reconstruir_posicao_antes
# ---------------------------------------------------------------------------

class TestReconstruirPosicaoAntes(unittest.TestCase):
    """Testes para a reconstrução de posições a partir do PGN da partida."""

    PGN_SIMPLES = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"

    def test_reconstroi_posicao_antes_do_lance_branco(self):
        board = reconstruir_posicao_antes(self.PGN_SIMPLES, 2, "BRANCAS")
        self.assertIsNotNone(board)
        self.assertEqual(board.fullmove_number, 2)
        self.assertTrue(board.turn)

    def test_reconstroi_posicao_antes_do_lance_preto(self):
        board = reconstruir_posicao_antes(self.PGN_SIMPLES, 2, "PRETAS")
        self.assertIsNotNone(board)
        self.assertEqual(board.fullmove_number, 2)
        self.assertFalse(board.turn)

    def test_lance_inexistente_retorna_none(self):
        board = reconstruir_posicao_antes(self.PGN_SIMPLES, 99, "BRANCAS")
        self.assertIsNone(board)

    def test_pgn_invalido_retorna_none(self):
        board = reconstruir_posicao_antes("", 1, "BRANCAS")
        self.assertIsNone(board)


# ---------------------------------------------------------------------------
# Testes: selecionar_evento_chave
# ---------------------------------------------------------------------------

class TestSelecionarEventoChave(unittest.TestCase):
    """Testes para a escolha do evento usado como momento_chave_estrategico."""

    def test_prefere_erosao_sobre_pico(self):
        pico = _lance_pico()
        erosao = _lance_erosao()
        self.assertIs(selecionar_evento_chave([pico, erosao]), erosao)

    def test_usa_pico_quando_sem_erosao(self):
        pico = _lance_pico()
        self.assertIs(selecionar_evento_chave([pico]), pico)

    def test_lista_vazia_retorna_none(self):
        self.assertIsNone(selecionar_evento_chave([]))


# ---------------------------------------------------------------------------
# Testes: enriquecer_com_dados_motor
# ---------------------------------------------------------------------------

class TestEnriquecerComDadosMotor(unittest.TestCase):
    """Testes para o enriquecimento dos eventos com dados reais do motor."""

    # Lance 8 é 8...Bxc3+ (PRETAS), coerente com a partida real uBgykEFk.
    PGN_PARTIDA = (
        "1. d4 d5 2. c4 e6 3. Nc3 Bb4 4. cxd5 exd5 5. Bf4 Nf6 6. e3 Bf5 "
        "7. Nf3 Ne4 8. Qb3 Bxc3+ 9. bxc3 b6"
    )

    def _dados_com_pgn(
        self, lances: list[LanceCriticoComDiagnostico], cor: str = "PRETAS"
    ) -> DadosPartida:
        return DadosPartida(
            partida_id="p1", cor_jogada=cor, eco_abertura="D31", resultado="0-1",
            lances_criticos=lances, metricas_lichess=None,
            lances_em_apuro_de_tempo=0, total_lances_criticos_com_tempo=0,
            pgn=self.PGN_PARTIDA,
        )

    @patch("backend.agentes.gerar_resumo_partida.obter_linha_principal")
    def test_preenche_linha_principal_do_evento_chave(self, mock_linha):
        mock_linha.return_value = ["Nxc3", "dxc3", "Nc6"]
        erosao = _lance_erosao(inicio=8, fim=10)
        dados = self._dados_com_pgn([erosao])

        enriquecer_com_dados_motor(dados, MagicMock(), MagicMock())

        self.assertEqual(erosao.linha_principal_motor, ["Nxc3", "dxc3", "Nc6"])
        mock_linha.assert_called_once()

    @patch("backend.agentes.gerar_resumo_partida.obter_top_candidatos")
    def test_preenche_top_candidatos_de_pico_tatico(self, mock_candidatos):
        mock_candidatos.return_value = [{"lance": "Nxc3", "avaliacao": "+50"}]
        pico_tatico = _lance_pico(
            numero=8, notacao="Bxc3+", tags=["calculo_tatico_deficiente"]
        )
        dados = self._dados_com_pgn([pico_tatico])

        enriquecer_com_dados_motor(dados, MagicMock(), MagicMock())

        self.assertEqual(
            pico_tatico.top_candidatos_motor, [{"lance": "Nxc3", "avaliacao": "+50"}]
        )

    @patch("backend.agentes.gerar_resumo_partida.obter_top_candidatos")
    def test_pico_nao_tatico_nao_recebe_candidatos(self, mock_candidatos):
        pico_estrategico = _lance_pico(
            numero=8, notacao="Bxc3+", tags=["avaliacao_posicional_incorreta"]
        )
        dados = self._dados_com_pgn([pico_estrategico])

        enriquecer_com_dados_motor(dados, MagicMock(), MagicMock())

        self.assertEqual(pico_estrategico.top_candidatos_motor, [])
        mock_candidatos.assert_not_called()

    def test_sem_pgn_nao_faz_nada(self):
        erosao = _lance_erosao()
        dados = DadosPartida(
            partida_id="p1", cor_jogada="PRETAS", eco_abertura=None, resultado=None,
            lances_criticos=[erosao], metricas_lichess=None,
            lances_em_apuro_de_tempo=0, total_lances_criticos_com_tempo=0, pgn=None,
        )

        enriquecer_com_dados_motor(dados, MagicMock(), MagicMock())

        self.assertEqual(erosao.linha_principal_motor, [])


# ---------------------------------------------------------------------------
# Testes: build_prompt_resumo com dados reais do motor
# ---------------------------------------------------------------------------

class TestBuildPromptResumoComDadosMotor(unittest.TestCase):
    """Testes para a inclusão de linha_principal/top_candidatos reais no prompt."""

    def test_prompt_inclui_linha_principal_do_motor(self):
        erosao = _lance_erosao()
        erosao.linha_principal_motor = ["Nxc3", "dxc3", "Nc6"]
        dados = _dados_partida(lances=[erosao])

        prompt = build_prompt_resumo(dados)

        self.assertIn("linha_principal_do_motor", prompt)
        self.assertIn("Nxc3 dxc3 Nc6", prompt)

    def test_prompt_inclui_top_candidatos_do_motor(self):
        pico = _lance_pico()
        pico.top_candidatos_motor = [{"lance": "Nc3", "avaliacao": "+30"}]
        dados = _dados_partida(lances=[pico])

        prompt = build_prompt_resumo(dados)

        self.assertIn("top_candidatos_do_motor", prompt)
        self.assertIn("Nc3 (+30)", prompt)

    def test_prompt_contem_regra_de_plano_concreto(self):
        dados = _dados_partida()
        prompt = build_prompt_resumo(dados)
        self.assertIn("NÃO invente lances ou planos além dos fornecidos", prompt)

    def test_lances_permitidos_inclui_dados_do_motor(self):
        erosao = _lance_erosao()
        erosao.linha_principal_motor = ["Nxc3"]
        dados = _dados_partida(lances=[erosao])

        prompt = build_prompt_resumo(dados)

        self.assertIn("Nxc3", prompt)


# ---------------------------------------------------------------------------
# Testes: validar_narrativa com fontes adicionais (dados reais do motor)
# ---------------------------------------------------------------------------

class TestValidarNarrativaComDadosMotor(unittest.TestCase):
    """Testes para a validação anti-alucinação generalizada às fontes do motor."""

    def test_aceita_lance_da_linha_principal_do_motor(self):
        erosao = _lance_erosao()
        erosao.linha_principal_motor = ["Nxc3", "dxc3"]
        narrativa = "O plano correto era Nxc3 seguido de dxc3."

        inventados = validar_narrativa(narrativa, [erosao])

        self.assertEqual(inventados, [])

    def test_aceita_lance_de_top_candidatos_do_motor(self):
        pico = _lance_pico()
        pico.top_candidatos_motor = [{"lance": "Nc3", "avaliacao": "+30"}]
        narrativa = "O motor recomendava Nc3 nesse ponto."

        inventados = validar_narrativa(narrativa, [pico])

        self.assertEqual(inventados, [])

    def test_ainda_rejeita_lance_fora_de_qualquer_fonte(self):
        pico = _lance_pico(notacao="Bxf7+")
        pico.top_candidatos_motor = [{"lance": "Nc3", "avaliacao": "+30"}]
        narrativa = "O lance Qh5 foi decisivo."

        inventados = validar_narrativa(narrativa, [pico])

        self.assertIn("Qh5", inventados)

    def test_coletar_lances_permitidos_agrega_todas_as_fontes(self):
        pico = _lance_pico(notacao="Bxf7+")
        pico.top_candidatos_motor = [{"lance": "Nc3", "avaliacao": "+30"}]
        erosao = _lance_erosao()
        erosao.linha_principal_motor = ["Nxc3", "dxc3"]

        permitidos = coletar_lances_permitidos([pico, erosao])

        self.assertEqual(permitidos, {"Bxf7+", "Nc3", "Nxc3", "dxc3"})


# ---------------------------------------------------------------------------
# Testes: fallback_resumo com dados reais do motor
# ---------------------------------------------------------------------------

class TestFallbackResumoComDadosMotor(unittest.TestCase):
    """Testes para o fallback literal incluindo dados reais do motor."""

    def test_momento_chave_inclui_plano_do_motor(self):
        erosao = _lance_erosao()
        erosao.linha_principal_motor = ["Nxc3", "dxc3", "Nc6"]
        dados = _dados_partida(lances=[erosao])

        resumo = fallback_resumo(dados)

        self.assertIn("plano correto segundo o motor", resumo.momento_chave_estrategico)
        self.assertIn("Nxc3 dxc3 Nc6", resumo.momento_chave_estrategico)

    def test_picos_com_candidatos_do_motor_no_texto(self):
        pico = _lance_pico()
        pico.top_candidatos_motor = [{"lance": "Nc3", "avaliacao": "+30"}]
        dados = _dados_partida(lances=[pico])

        resumo = fallback_resumo(dados)

        self.assertIn("motor recomendava: Nc3", resumo.narrativa)


if __name__ == "__main__":
    unittest.main()

