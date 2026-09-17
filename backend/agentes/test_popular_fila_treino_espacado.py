import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from backend.agentes.popular_fila_treino_espacado import (
    TREINO_NOVOS_POR_DIA,
    _CACHE_CITACAO,
    buscar_diagnosticos_elegiveis,
    distribuir_por_dia,
    lances_ja_na_fila,
    listar_usuarios_com_diagnostico,
    montar_linhas_novas,
    popular_para_usuario,
    primeiro_dia_livre,
    resolver_citacao,
)


class ListarUsuariosComDiagnosticoTest(unittest.TestCase):
    """Deduplica e ignora linhas sem user_id resolvido (join partido/ausente)."""

    def test_deduplica_e_ignora_user_id_nulo(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.execute.return_value.data = [
            {"lances_criticos": {"partidas": {"user_id": "user-b"}}},
            {"lances_criticos": {"partidas": {"user_id": "user-a"}}},
            {"lances_criticos": {"partidas": {"user_id": "user-a"}}},
            {"lances_criticos": {"partidas": {"user_id": None}}},
            {"lances_criticos": {}},
        ]

        usuarios = listar_usuarios_com_diagnostico(client)

        self.assertEqual(usuarios, ["user-a", "user-b"])


class BuscarDiagnosticosElegiveisTest(unittest.TestCase):
    """O filtro precisa restringir a fen_antes_lance preenchido e ao dono."""

    def test_filtros_aplicados_na_query(self) -> None:
        client = MagicMock()
        cadeia = (
            client.table.return_value.select.return_value.eq
            .return_value.not_.is_.return_value.range.return_value.execute
        )
        cadeia.return_value.data = []

        buscar_diagnosticos_elegiveis(client, MagicMock(), "user-a")

        select_arg = client.table.return_value.select.call_args[0][0]
        self.assertIn("lances_criticos!inner", select_arg)
        self.assertIn("partidas!inner", select_arg)
        # O tipo_evento precisa VIR, para a cota de trechos do D-66 saber
        # separar os candidatos.
        self.assertIn("tipo_evento", select_arg)

        primeira_eq = client.table.return_value.select.return_value.eq
        primeira_eq.assert_called_once_with("lances_criticos.partidas.user_id", "user-a")
        # Desde o D-66 não há mais filtro por tipo_evento: EROSAO também é
        # elegível, e o que a separa de PICO é a cota diária, não a consulta.
        primeira_eq.return_value.eq.assert_not_called()
        primeira_eq.return_value.not_.is_.assert_called_once_with(
            "lances_criticos.fen_antes_lance", "null"
        )


class LancesJaNaFilaTest(unittest.TestCase):
    def test_devolve_conjunto_de_ids_ja_enfileirados(self) -> None:
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"lance_id": "lance-1"},
            {"lance_id": "lance-2"},
            {"lance_id": None},
        ]

        resultado = lances_ja_na_fila(client, "user-a")

        self.assertEqual(resultado, {"lance-1", "lance-2"})


class ResolverCitacaoTest(unittest.TestCase):
    def setUp(self) -> None:
        _CACHE_CITACAO.clear()

    def test_sem_categoria_devolve_none_sem_consultar(self) -> None:
        client = MagicMock()
        self.assertIsNone(resolver_citacao(client, None))
        client.table.assert_not_called()

    @patch("backend.agentes.popular_fila_treino_espacado.buscar_conceitos")
    def test_usa_primeiro_conceito_encontrado(self, buscar_conceitos_mock: MagicMock) -> None:
        buscar_conceitos_mock.return_value = [
            {"livro": "Meu Sistema", "capitulo": "4", "pagina_aprox": 88},
            {"livro": "Outro Livro", "capitulo": "1", "pagina_aprox": 1},
        ]
        client = MagicMock()

        citacao = resolver_citacao(client, "TATICA")

        self.assertEqual(citacao["livro"], "Meu Sistema")
        buscar_conceitos_mock.assert_called_once_with(client, "TATICA")

    @patch("backend.agentes.popular_fila_treino_espacado.buscar_conceitos")
    def test_categoria_sem_conceito_cacheia_none(self, buscar_conceitos_mock: MagicMock) -> None:
        buscar_conceitos_mock.return_value = []
        client = MagicMock()

        primeira = resolver_citacao(client, "GESTAO_DE_TEMPO")
        segunda = resolver_citacao(client, "GESTAO_DE_TEMPO")

        self.assertIsNone(primeira)
        self.assertIsNone(segunda)
        buscar_conceitos_mock.assert_called_once()  # 2ª chamada veio do cache


class MontarLinhasNovasTest(unittest.TestCase):
    def setUp(self) -> None:
        _CACHE_CITACAO.clear()

    @patch("backend.agentes.popular_fila_treino_espacado.buscar_conceitos")
    def test_ignora_lances_ja_na_fila(self, buscar_conceitos_mock: MagicMock) -> None:
        buscar_conceitos_mock.return_value = []
        diagnosticos = [
            {"tags_falha": ["calculo_tatico_deficiente"], "lances_criticos": {"id": "ja-existe"}},
        ]

        linhas = montar_linhas_novas(
            diagnosticos, {"ja-existe"}, MagicMock(), "user-a", date(2026, 9, 16)
        )

        self.assertEqual(linhas, [])

    @patch("backend.agentes.popular_fila_treino_espacado.buscar_conceitos")
    def test_escalona_novos_cards_alem_do_teto_diario(self, buscar_conceitos_mock: MagicMock) -> None:
        buscar_conceitos_mock.return_value = []
        total = TREINO_NOVOS_POR_DIA + 3
        diagnosticos = [
            {"tags_falha": [], "lances_criticos": {"id": f"lance-{i}"}} for i in range(total)
        ]

        linhas = montar_linhas_novas(
            diagnosticos, set(), MagicMock(), "user-a", date(2026, 9, 16)
        )

        self.assertEqual(len(linhas), total)
        # Os primeiros TREINO_NOVOS_POR_DIA entram hoje...
        for linha in linhas[:TREINO_NOVOS_POR_DIA]:
            self.assertEqual(linha["proxima_revisao_data"], "2026-09-16")
        # ...o resto escorrega para o dia seguinte.
        for linha in linhas[TREINO_NOVOS_POR_DIA:]:
            self.assertEqual(linha["proxima_revisao_data"], "2026-09-17")

    @patch("backend.agentes.popular_fila_treino_espacado.buscar_conceitos")
    def test_preenche_citacao_quando_disponivel(self, buscar_conceitos_mock: MagicMock) -> None:
        buscar_conceitos_mock.return_value = [
            {"livro": "Meu Sistema", "capitulo": "4", "pagina_aprox": 88}
        ]
        diagnosticos = [
            {"tags_falha": ["calculo_tatico_deficiente"], "lances_criticos": {"id": "lance-1"}},
        ]

        linhas = montar_linhas_novas(
            diagnosticos, set(), MagicMock(), "user-a", date(2026, 9, 16)
        )

        self.assertEqual(linhas[0]["livro_citado"], "Meu Sistema")
        self.assertEqual(linhas[0]["pagina_citada"], 88)

    @patch("backend.agentes.popular_fila_treino_espacado.buscar_conceitos")
    def test_sem_tags_falha_nao_busca_citacao(self, buscar_conceitos_mock: MagicMock) -> None:
        diagnosticos = [{"tags_falha": [], "lances_criticos": {"id": "lance-1"}}]

        linhas = montar_linhas_novas(
            diagnosticos, set(), MagicMock(), "user-a", date(2026, 9, 16)
        )

        self.assertIsNone(linhas[0]["livro_citado"])
        buscar_conceitos_mock.assert_not_called()


class CotaDeTrechosTest(unittest.TestCase):
    """D-66: um card de erosão são 8 lances, não 1 — ele tem cota própria.

    Sem isso, dez erosões em sequência na ordem de chegada virariam um dia com
    oito vezes o trabalho de outro: o mesmo erro do D-64 (medir a fila em
    linhas em vez de em esforço), só que numa escala diferente.
    """

    def _candidatos(self, quantos_trechos: int, quantos_picos: int):
        trechos = [(f"erosao-{i}", {}, True) for i in range(quantos_trechos)]
        picos = [(f"pico-{i}", {}, False) for i in range(quantos_picos)]
        return trechos + picos

    def test_dia_leva_no_maximo_a_cota_de_trechos(self) -> None:
        distribuicao = distribuir_por_dia(self._candidatos(6, 20), por_dia=10, trechos_por_dia=2)

        do_dia_zero = [item for item in distribuicao if item[0] == 0]
        self.assertEqual(len(do_dia_zero), 10)
        trechos_no_dia_zero = [item for item in do_dia_zero if item[1].startswith("erosao")]
        self.assertEqual(len(trechos_no_dia_zero), 2)

    def test_trechos_em_sequencia_sao_espalhados_por_varios_dias(self) -> None:
        distribuicao = distribuir_por_dia(self._candidatos(6, 0), por_dia=10, trechos_por_dia=2)

        dias = sorted({item[0] for item in distribuicao})
        self.assertEqual(dias, [0, 1, 2])
        self.assertEqual(len(distribuicao), 6)

    def test_sem_trecho_nenhum_o_escalonamento_e_o_de_sempre(self) -> None:
        distribuicao = distribuir_por_dia(self._candidatos(0, 23), por_dia=10, trechos_por_dia=2)

        self.assertEqual(len(distribuicao), 23)
        self.assertEqual([item[0] for item in distribuicao[:10]], [0] * 10)
        self.assertEqual(distribuicao[-1][0], 2)

    def test_cota_zero_desliga_os_trechos_sem_travar(self) -> None:
        """O desligador do recurso: os picos continuam entrando, os trechos não."""
        distribuicao = distribuir_por_dia(self._candidatos(5, 3), por_dia=10, trechos_por_dia=0)

        self.assertEqual(len(distribuicao), 3)
        self.assertTrue(all(item[1].startswith("pico") for item in distribuicao))

    def test_cota_maior_que_o_dia_nao_estoura_o_teto_diario(self) -> None:
        distribuicao = distribuir_por_dia(self._candidatos(8, 0), por_dia=3, trechos_por_dia=10)

        do_dia_zero = [item for item in distribuicao if item[0] == 0]
        self.assertEqual(len(do_dia_zero), 3)

    @patch("backend.agentes.popular_fila_treino_espacado.buscar_conceitos")
    def test_montar_linhas_respeita_a_cota(self, buscar_mock: MagicMock) -> None:
        buscar_mock.return_value = []
        diagnosticos = [
            {
                "tags_falha": [],
                "lances_criticos": {"id": f"erosao-{i}", "tipo_evento": "EROSAO"},
            }
            for i in range(5)
        ]

        linhas = montar_linhas_novas(
            diagnosticos, set(), MagicMock(), "user-a", date(2026, 9, 17)
        )

        # 5 erosões, cota de 2/dia (default) -> três dias.
        datas = [linha["proxima_revisao_data"] for linha in linhas]
        self.assertEqual(
            datas, ["2026-09-17", "2026-09-17", "2026-09-18", "2026-09-18", "2026-09-19"]
        )


class ValvulaDaFilaTest(unittest.TestCase):
    """D-64: material novo vai para o FIM da fila e respeita um horizonte.

    Antes disso todo card novo entrava a partir de `hoje`, então cada execução
    empilhava mais 10 vencidos sobre os que já estavam atrasados — a fila
    crescia no ritmo da ingestão, não no do consumo.
    """

    def setUp(self) -> None:
        _CACHE_CITACAO.clear()
        self.hoje = date(2026, 9, 17)

    def _client_com_ultima_data(self, valor: str | None) -> MagicMock:
        client = MagicMock()
        dados = [{"proxima_revisao_data": valor}] if valor else []
        cadeia = client.table.return_value.select.return_value.eq.return_value
        cadeia = cadeia.eq.return_value.order.return_value.limit.return_value
        cadeia.execute.return_value = MagicMock(data=dados)
        return client

    def test_fila_vazia_comeca_hoje(self) -> None:
        primeiro = primeiro_dia_livre(
            self._client_com_ultima_data(None), "user-a", self.hoje
        )
        self.assertEqual(primeiro, self.hoje)

    def test_com_fila_agendada_comeca_no_dia_seguinte_ao_ultimo(self) -> None:
        primeiro = primeiro_dia_livre(
            self._client_com_ultima_data("2026-11-17"), "user-a", self.hoje
        )
        self.assertEqual(primeiro, date(2026, 11, 18))

    def test_fila_toda_vencida_nao_agenda_no_passado(self) -> None:
        """Se o último agendado já venceu, o novo entra hoje — nunca atrás."""
        primeiro = primeiro_dia_livre(
            self._client_com_ultima_data("2026-09-01"), "user-a", self.hoje
        )
        self.assertEqual(primeiro, self.hoje)

    @patch("backend.agentes.popular_fila_treino_espacado.buscar_conceitos")
    def test_material_novo_nao_cai_em_cima_dos_vencidos(self, buscar_mock: MagicMock) -> None:
        """O defeito que a válvula corrige, dito como teste."""
        buscar_mock.return_value = []
        diagnosticos = [
            {"tags_falha": [], "lances_criticos": {"id": f"lance-{i}"}} for i in range(3)
        ]

        linhas = montar_linhas_novas(
            diagnosticos,
            set(),
            MagicMock(),
            "user-a",
            self.hoje,
            primeiro_dia=date(2026, 9, 30),
        )

        self.assertEqual(len(linhas), 3)
        for linha in linhas:
            self.assertEqual(linha["proxima_revisao_data"], "2026-09-30")

    @patch("backend.agentes.popular_fila_treino_espacado.buscar_conceitos")
    def test_horizonte_corta_o_que_nao_cabe(self, buscar_mock: MagicMock) -> None:
        buscar_mock.return_value = []
        # Com 3 dias de horizonte e 10 por dia, cabem 4 dias (0,1,2,3) = 40.
        diagnosticos = [
            {"tags_falha": [], "lances_criticos": {"id": f"lance-{i}"}} for i in range(100)
        ]

        linhas = montar_linhas_novas(
            diagnosticos, set(), MagicMock(), "user-a", self.hoje, horizonte_dias=3
        )

        self.assertEqual(len(linhas), 4 * TREINO_NOVOS_POR_DIA)
        self.assertEqual(linhas[-1]["proxima_revisao_data"], "2026-09-20")

    @patch("backend.agentes.popular_fila_treino_espacado.buscar_conceitos")
    def test_fila_cheia_ate_o_horizonte_nao_agenda_nada(self, buscar_mock: MagicMock) -> None:
        """Nada se perde: os diagnósticos continuam elegíveis na próxima
        execução, quando a fila tiver drenado."""
        buscar_mock.return_value = []
        diagnosticos = [{"tags_falha": [], "lances_criticos": {"id": "lance-1"}}]

        linhas = montar_linhas_novas(
            diagnosticos,
            set(),
            MagicMock(),
            "user-a",
            self.hoje,
            primeiro_dia=self.hoje + timedelta(days=61),
            horizonte_dias=60,
        )

        self.assertEqual(linhas, [])


class PopularParaUsuarioTest(unittest.TestCase):
    """Isolamento por usuário: sem diagnóstico ou sem novidade, não toca a fila."""

    @patch("backend.agentes.popular_fila_treino_espacado.buscar_diagnosticos_elegiveis")
    def test_sem_diagnosticos_nao_grava_nada(self, buscar_mock: MagicMock) -> None:
        buscar_mock.return_value = []
        client = MagicMock()

        total = popular_para_usuario(client, MagicMock(), "user-a", date(2026, 9, 16))

        self.assertEqual(total, 0)
        client.table.return_value.upsert.assert_not_called()

    @patch("backend.agentes.popular_fila_treino_espacado.lances_ja_na_fila")
    @patch("backend.agentes.popular_fila_treino_espacado.buscar_diagnosticos_elegiveis")
    def test_tudo_ja_na_fila_nao_grava_nada(
        self, buscar_mock: MagicMock, ja_na_fila_mock: MagicMock
    ) -> None:
        buscar_mock.return_value = [
            {"tags_falha": [], "lances_criticos": {"id": "lance-1"}}
        ]
        ja_na_fila_mock.return_value = {"lance-1"}
        client = MagicMock()

        total = popular_para_usuario(client, MagicMock(), "user-a", date(2026, 9, 16))

        self.assertEqual(total, 0)
        client.table.return_value.upsert.assert_not_called()

    @patch("backend.agentes.popular_fila_treino_espacado.buscar_conceitos")
    @patch("backend.agentes.popular_fila_treino_espacado.lances_ja_na_fila")
    @patch("backend.agentes.popular_fila_treino_espacado.buscar_diagnosticos_elegiveis")
    def test_insere_com_on_conflict_por_usuario_e_lance(
        self,
        buscar_mock: MagicMock,
        ja_na_fila_mock: MagicMock,
        buscar_conceitos_mock: MagicMock,
    ) -> None:
        _CACHE_CITACAO.clear()
        buscar_mock.return_value = [
            {"tags_falha": [], "lances_criticos": {"id": "lance-1"}}
        ]
        ja_na_fila_mock.return_value = set()
        buscar_conceitos_mock.return_value = []
        client = MagicMock()

        total = popular_para_usuario(client, MagicMock(), "user-a", date(2026, 9, 16))

        self.assertEqual(total, 1)
        client.table.return_value.upsert.assert_called_once()
        _, kwargs = client.table.return_value.upsert.call_args
        self.assertEqual(kwargs["on_conflict"], "user_id,lance_id")


if __name__ == "__main__":
    unittest.main()
