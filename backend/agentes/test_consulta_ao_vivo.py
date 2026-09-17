"""Testes da consulta ao vivo (D-67): ajuda para pensar numa partida em andamento."""

from __future__ import annotations

import json
import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import chess

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.agentes import consulta_ao_vivo as modulo  # noqa: E402
from backend.agentes.consulta_ao_vivo import (  # noqa: E402
    IdeiaCandidata,
    PlanoConsulta,
    RespostaConsulta,
    consultar_posicao,
    gerar_resposta,
    limite_por_partida,
    problemas_da_resposta,
    reconstruir_partida,
    usuarios_com_acesso,
)

LOGGER = logging.getLogger("teste_consulta_ao_vivo")
LOGGER.addHandler(logging.NullHandler())
LOGGER.propagate = False

ELEMENTOS = {
    "material": {"descricao": "Material rigorosamente igual (39 pontos para cada lado)"},
    "pecas_indefesas": {"BRANCAS": [], "PRETAS": ["Cavalo em c6 (sem defensores)"]},
    "pecas_cravadas": {"BRANCAS": [], "PRETAS": []},
    "seguranca_rei": {
        "BRANCAS": {"resumo": "Rei em g1 com segurança razoável"},
        "PRETAS": {"resumo": "Rei em e8 no centro sem roque"},
    },
    "ameacas_imediatas": {"cheques": [], "capturas": []},
}


def resposta_valida(**extras) -> RespostaConsulta:
    base = {
        "leitura_da_posicao": "O centro está aberto e o rei preto ainda está na casa e8.",
        "sobre_o_seu_raciocinio": None,
        "perguntas_guia": ["Qual peça sua está sem função?"],
        "planos": [PlanoConsulta(titulo="Abrir a coluna e", explicacao="O rei preto não rocou.")],
        "ideias_candidatas": [IdeiaCandidata(lance="Nc3", ideia="Desenvolve e controla d5.")],
    }
    base.update(extras)
    return RespostaConsulta(**base)


class AcessoTest(unittest.TestCase):
    def test_sem_variavel_ninguem_tem_acesso(self) -> None:
        """Fecha por padrão: um esquecimento de configuração não pode abrir a
        feature exclusiva para todo mundo."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(usuarios_com_acesso(), frozenset())

    def test_variavel_vazia_ninguem_tem_acesso(self) -> None:
        with patch.dict(os.environ, {"CONSULTA_AO_VIVO_USUARIOS": " , "}):
            self.assertEqual(usuarios_com_acesso(), frozenset())

    def test_le_lista_separada_por_virgula(self) -> None:
        with patch.dict(os.environ, {"CONSULTA_AO_VIVO_USUARIOS": "abc, def"}):
            self.assertEqual(usuarios_com_acesso(), frozenset({"abc", "def"}))

    def test_limite_por_partida_padrao_e_invalido(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(limite_por_partida(), 3)
        with patch.dict(os.environ, {"CONSULTA_MAX_POR_PARTIDA": "x"}):
            self.assertEqual(limite_por_partida(), 3)
        with patch.dict(os.environ, {"CONSULTA_MAX_POR_PARTIDA": "0"}):
            self.assertEqual(limite_por_partida(), 1)


class ReconstruirPartidaTest(unittest.TestCase):
    def test_aplica_lances_em_san(self) -> None:
        board = reconstruir_partida(None, ["e4", "e5", "Nf3"])
        self.assertEqual(board.turn, chess.BLACK)
        self.assertEqual(board.fullmove_number, 2)

    def test_aceita_uci_como_segunda_chance(self) -> None:
        board = reconstruir_partida(None, ["e2e4", "e7e5"])
        self.assertEqual(board.fullmove_number, 2)

    def test_lance_ilegal_diz_qual_foi(self) -> None:
        with self.assertRaises(ValueError) as contexto:
            reconstruir_partida(None, ["e4", "e5", "Qxf7"])
        self.assertIn("Lance 3", str(contexto.exception))

    def test_parte_de_posicao_propria(self) -> None:
        """Bots permitem começar de uma posição; o espelho precisa também."""
        fen = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
        board = reconstruir_partida(fen, ["e4"])
        self.assertIsNotNone(board.piece_at(chess.E4))

    def test_fen_ilegal_e_recusada(self) -> None:
        with self.assertRaises(ValueError):
            reconstruir_partida("8/8/8/8/8/8/8/8 w - - 0 1", [])


class ProblemasDaRespostaTest(unittest.TestCase):
    def test_resposta_limpa_nao_tem_problema(self) -> None:
        self.assertEqual(problemas_da_resposta(resposta_valida(), ["Nc3"], {"Nc3"}), [])

    def test_lance_em_ingles_na_camada_pensar_e_problema(self) -> None:
        resposta = resposta_valida(leitura_da_posicao="Jogue Nf3 e depois roque.")
        problemas = problemas_da_resposta(resposta, ["Nc3"], {"Nc3", "Nf3"})
        self.assertTrue(any("Nf3" in p for p in problemas))

    def test_lance_em_portugues_na_camada_pensar_e_problema(self) -> None:
        """O detector herdado só conhecia notação inglesa: 'Cf3' passava."""
        resposta = resposta_valida(
            planos=[PlanoConsulta(titulo="Cavalo", explicacao="Leve o cavalo com Cf3.")]
        )
        problemas = problemas_da_resposta(resposta, ["Nc3"], {"Nc3"})
        self.assertTrue(any("Cf3" in p for p in problemas))

    def test_lance_legal_ainda_e_proibido_na_camada_pensar(self) -> None:
        resposta = resposta_valida(perguntas_guia=["E se você jogar Nc3?"])
        problemas = problemas_da_resposta(resposta, ["Nc3"], {"Nc3"})
        self.assertTrue(problemas)

    def test_casas_e_pecas_podem_aparecer(self) -> None:
        resposta = resposta_valida(
            leitura_da_posicao="O bispo em c4 mira f7 e a casa d5 está fraca."
        )
        self.assertEqual(problemas_da_resposta(resposta, ["Nc3"], {"Nc3"}), [])

    def test_ideia_de_lance_que_nao_e_candidato_e_problema(self) -> None:
        resposta = resposta_valida(ideias_candidatas=[IdeiaCandidata(lance="h4", ideia="Avança.")])
        problemas = problemas_da_resposta(resposta, ["Nc3"], {"Nc3", "h4"})
        self.assertTrue(any("h4" in p for p in problemas))


class GerarRespostaTest(unittest.TestCase):
    def _json(self, resposta: RespostaConsulta) -> str:
        return resposta.model_dump_json()

    def test_resposta_boa_na_primeira_chamada(self) -> None:
        with patch.object(modulo, "call_gemini", return_value=self._json(resposta_valida())) as gemini:
            resposta, origem = gerar_resposta(
                object(), "prompt", ELEMENTOS, "BRANCAS", ["Nc3"], {"Nc3"}, LOGGER
            )
        self.assertEqual(origem, "gemini")
        self.assertEqual(gemini.call_count, 1)
        self.assertIn("rei preto", resposta.leitura_da_posicao)

    def test_uma_correcao_e_so(self) -> None:
        ruim = self._json(resposta_valida(leitura_da_posicao="Jogue Nc3 agora."))
        bom = self._json(resposta_valida())
        with patch.object(modulo, "call_gemini", side_effect=[ruim, bom]) as gemini:
            _, origem = gerar_resposta(
                object(), "prompt", ELEMENTOS, "BRANCAS", ["Nc3"], {"Nc3"}, LOGGER
            )
        self.assertEqual(origem, "gemini")
        self.assertEqual(gemini.call_count, 2)
        # A segunda chamada leva o motivo da rejeição.
        self.assertIn("proibido", gemini.call_args_list[1].args[1])

    def test_duas_violacoes_caem_no_fallback_sem_terceira_chamada(self) -> None:
        ruim = self._json(resposta_valida(leitura_da_posicao="Jogue Nc3 agora."))
        with patch.object(modulo, "call_gemini", side_effect=[ruim, ruim, ruim]) as gemini:
            resposta, origem = gerar_resposta(
                object(), "prompt", ELEMENTOS, "BRANCAS", ["Nc3"], {"Nc3"}, LOGGER
            )
        self.assertEqual(origem, "fallback")
        self.assertEqual(gemini.call_count, 2)
        self.assertNotIn("Nc3", resposta.leitura_da_posicao)

    def test_json_invalido_conta_como_violacao(self) -> None:
        with patch.object(modulo, "call_gemini", side_effect=["não é json", self._json(resposta_valida())]):
            _, origem = gerar_resposta(
                object(), "prompt", ELEMENTOS, "BRANCAS", ["Nc3"], {"Nc3"}, LOGGER
            )
        self.assertEqual(origem, "gemini")

    def test_falha_de_rede_nao_insiste(self) -> None:
        with patch.object(modulo, "call_gemini", side_effect=RuntimeError("429")) as gemini:
            _, origem = gerar_resposta(
                object(), "prompt", ELEMENTOS, "BRANCAS", ["Nc3"], {"Nc3"}, LOGGER
            )
        self.assertEqual(origem, "fallback")
        self.assertEqual(gemini.call_count, 1)

    def test_fallback_deterministico_nao_cita_lance_na_camada_pensar(self) -> None:
        resposta, origem = gerar_resposta(
            None, "prompt", ELEMENTOS, "BRANCAS", ["Nc3", "d4"], {"Nc3", "d4"}, LOGGER
        )
        self.assertEqual(origem, "fallback")
        self.assertEqual(problemas_da_resposta(resposta, ["Nc3", "d4"], {"Nc3", "d4"}), [])
        self.assertIn("c6", resposta.leitura_da_posicao)  # o alvo real do adversário


class ConsultarPosicaoTest(unittest.TestCase):
    ANALISE = {
        "score_cp": 45,
        "mate": None,
        "win_percent": 50.0,
        "win_percent_brancas": 54.1,
        "win_percent_pretas": 45.9,
        "lado_vencedor": "EQUILIBRADO",
        "descricao": "+0.45 centipawns (posição equilibrada para Brancas)",
        "linhas_taticas": [
            {"lance": "d4", "avaliacao": "+45", "pv_san": ["d4", "exd4"]},
            {"lance": "Nc3", "avaliacao": "+30", "pv_san": ["Nc3"]},
            {"lance": "c3", "avaliacao": "+20", "pv_san": ["c3"]},
        ],
        "refutacao_defesa": None,
    }

    def _consultar(self, lances, cor, resposta_gemini=None, **extras):
        gemini = json.dumps(
            resposta_gemini
            or {
                "leitura_da_posicao": "Centro em tensão.",
                "sobre_o_seu_raciocinio": None,
                "perguntas_guia": ["O que o adversário ameaça?"],
                "planos": [{"titulo": "Centro", "explicacao": "Ganhar espaço."}],
                "ideias_candidatas": [
                    {"lance": "d4", "ideia": "Abre o centro."},
                    {"lance": "Nc3", "ideia": "Desenvolve."},
                    {"lance": "c3", "ideia": "Prepara d4."},
                ],
            }
        )
        with patch.object(modulo, "analisar_posicao_com_engine", return_value=self.ANALISE), \
                patch.object(modulo, "call_gemini", return_value=gemini) as chamada:
            resultado = consultar_posicao(
                MagicMock(), object(), LOGGER, lances, cor, **extras
            )
        return resultado, chamada

    def test_vez_do_adversario_e_recusada_antes_de_gastar_motor(self) -> None:
        with patch.object(modulo, "analisar_posicao_com_engine") as motor:
            with self.assertRaises(ValueError) as contexto:
                consultar_posicao(MagicMock(), object(), LOGGER, ["e4"], "BRANCAS")
        self.assertIn("adversário", str(contexto.exception))
        motor.assert_not_called()

    def test_partida_terminada_e_recusada(self) -> None:
        mate_do_louco = ["f3", "e5", "g4", "Qh4#"]
        with self.assertRaises(ValueError):
            consultar_posicao(MagicMock(), object(), LOGGER, mate_do_louco, "BRANCAS")

    def test_ideias_em_ordem_alfabetica_escondem_o_ranking(self) -> None:
        resultado, _ = self._consultar(["e4", "e5", "Nf3", "Nc6"], "BRANCAS")
        lances = [ideia["lance"] for ideia in resultado["camada_ideias"]["ideias"]]
        self.assertEqual(lances, ["c3", "d4", "Nc3"])
        self.assertEqual(resultado["camada_motor"]["melhor_lance"], "d4")

    def test_camadas_e_perspectiva_do_jogador(self) -> None:
        resultado, _ = self._consultar(["e4", "e5", "Nf3", "Nc6"], "brancas")
        self.assertEqual(resultado["cor_jogador"], "BRANCAS")
        self.assertEqual(resultado["numero_lance"], 3)
        self.assertEqual(resultado["camada_motor"]["win_percent_jogador"], 54.1)
        self.assertEqual(resultado["gerado_por"], "gemini")
        self.assertEqual(resultado["lances_san"], ["e4", "e5", "Nf3", "Nc6"])

    def test_pensamento_do_usuario_chega_ao_prompt(self) -> None:
        _, chamada = self._consultar(
            ["e4", "e5", "Nf3", "Nc6"],
            "BRANCAS",
            pensamento={"situacao": "Acho que o centro está travado", "trava": None},
        )
        prompt = chamada.call_args.args[1]
        self.assertIn("Acho que o centro está travado", prompt)
        self.assertNotIn("não descreveu", prompt)

    def test_sem_pensamento_o_prompt_diz_isso(self) -> None:
        _, chamada = self._consultar(["e4", "e5", "Nf3", "Nc6"], "BRANCAS")
        self.assertIn("não descreveu", chamada.call_args.args[1])

    def test_uci_vira_san_canonico_no_registro(self) -> None:
        resultado, _ = self._consultar(["e2e4", "e7e5", "g1f3", "b8c6"], "BRANCAS")
        self.assertEqual(resultado["lances_san"], ["e4", "e5", "Nf3", "Nc6"])


if __name__ == "__main__":
    unittest.main()
