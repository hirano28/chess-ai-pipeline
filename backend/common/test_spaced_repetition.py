import unittest
from datetime import date

from backend.common.spaced_repetition import (
    FATOR_FACILIDADE_MINIMO,
    atualizar_agendamento,
    nota_sm2_da_qualidade_lance,
)


class NotaSm2DaQualidadeLanceTest(unittest.TestCase):
    def test_mapeia_os_tres_niveis_conhecidos(self) -> None:
        self.assertEqual(nota_sm2_da_qualidade_lance("BOM"), 5)
        self.assertEqual(nota_sm2_da_qualidade_lance("SUBOTIMO"), 3)
        self.assertEqual(nota_sm2_da_qualidade_lance("RUIM"), 1)

    def test_valor_desconhecido_cai_para_ruim_por_seguranca(self) -> None:
        self.assertEqual(nota_sm2_da_qualidade_lance("ALGO_NOVO"), 1)


class AtualizarAgendamentoTest(unittest.TestCase):
    HOJE = date(2026, 9, 16)

    def test_primeira_revisao_boa_agenda_para_amanha(self) -> None:
        resultado = atualizar_agendamento(
            intervalo_dias=0,
            fator_facilidade=2.5,
            repeticoes=0,
            qualidade=5,
            hoje=self.HOJE,
        )
        self.assertEqual(resultado.intervalo_dias, 1)
        self.assertEqual(resultado.repeticoes, 1)
        self.assertEqual(resultado.proxima_revisao_data, date(2026, 9, 17))

    def test_segunda_revisao_boa_agenda_para_6_dias(self) -> None:
        resultado = atualizar_agendamento(
            intervalo_dias=1,
            fator_facilidade=2.6,
            repeticoes=1,
            qualidade=5,
            hoje=self.HOJE,
        )
        self.assertEqual(resultado.intervalo_dias, 6)
        self.assertEqual(resultado.repeticoes, 2)
        self.assertEqual(resultado.proxima_revisao_data, date(2026, 9, 22))

    def test_terceira_revisao_boa_multiplica_intervalo_pelo_fator(self) -> None:
        resultado = atualizar_agendamento(
            intervalo_dias=6,
            fator_facilidade=2.5,
            repeticoes=2,
            qualidade=5,
            hoje=self.HOJE,
        )
        self.assertEqual(resultado.intervalo_dias, 15)  # round(6 * 2.5)
        self.assertEqual(resultado.repeticoes, 3)

    def test_qualidade_ruim_reseta_a_serie_mesmo_com_historico_longo(self) -> None:
        resultado = atualizar_agendamento(
            intervalo_dias=30,
            fator_facilidade=2.8,
            repeticoes=5,
            qualidade=1,
            hoje=self.HOJE,
        )
        self.assertEqual(resultado.intervalo_dias, 1)
        self.assertEqual(resultado.repeticoes, 0)
        self.assertEqual(resultado.proxima_revisao_data, date(2026, 9, 17))

    def test_qualidade_mediana_tambem_reseta_por_ser_abaixo_do_minimo(self) -> None:
        # qualidade=2 (abaixo de NOTA_MINIMA_PARA_ACERTO=3) ainda conta como erro.
        resultado = atualizar_agendamento(
            intervalo_dias=6,
            fator_facilidade=2.5,
            repeticoes=2,
            qualidade=2,
            hoje=self.HOJE,
        )
        self.assertEqual(resultado.intervalo_dias, 1)
        self.assertEqual(resultado.repeticoes, 0)

    def test_fator_facilidade_nunca_cai_abaixo_do_minimo(self) -> None:
        resultado = atualizar_agendamento(
            intervalo_dias=1,
            fator_facilidade=1.35,
            repeticoes=1,
            qualidade=1,
            hoje=self.HOJE,
        )
        self.assertGreaterEqual(resultado.fator_facilidade, FATOR_FACILIDADE_MINIMO)

    def test_fator_facilidade_cresce_com_qualidade_maxima(self) -> None:
        resultado = atualizar_agendamento(
            intervalo_dias=1,
            fator_facilidade=2.5,
            repeticoes=1,
            qualidade=5,
            hoje=self.HOJE,
        )
        self.assertGreater(resultado.fator_facilidade, 2.5)


if __name__ == "__main__":
    unittest.main()
