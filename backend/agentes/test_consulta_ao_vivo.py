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
    PassoDoRoteiro,
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
        "tipo_de_posicao": "O centro está aberto e o rei preto ainda está na casa e8.",
        "sobre_o_seu_raciocinio": None,
        "roteiro": [
            PassoDoRoteiro(o_que_avaliar="O que o último lance preto ameaça.", por_que="Segurança primeiro."),
            PassoDoRoteiro(o_que_avaliar="Se o cavalo em c6 está defendido.", por_que="Peça solta vira alvo."),
            PassoDoRoteiro(o_que_avaliar="Qual peça sua está sem função.", por_que="Posição calma pede manobra."),
        ],
        "principio": "Com o rei adversário no centro, abrir linhas vale mais que ganhar material.",
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
        self.assertEqual(problemas_da_resposta(resposta_valida()), [])

    def test_lance_em_ingles_e_problema(self) -> None:
        resposta = resposta_valida(tipo_de_posicao="Jogue Nf3 e depois roque.")
        self.assertTrue(any("Nf3" in p for p in problemas_da_resposta(resposta)))

    def test_lance_em_portugues_e_problema(self) -> None:
        """O detector herdado só conhecia notação inglesa: 'Cf3' passava."""
        resposta = resposta_valida(principio="Na dúvida, Cf3 resolve.")
        self.assertTrue(any("Cf3" in p for p in problemas_da_resposta(resposta)))

    def test_lance_escondido_no_por_que_do_roteiro_e_problema(self) -> None:
        roteiro = [
            *resposta_valida().roteiro[:2],
            PassoDoRoteiro(o_que_avaliar="O centro.", por_que="Porque depois de exd5 a coluna abre."),
        ]
        self.assertTrue(problemas_da_resposta(resposta_valida(roteiro=roteiro)))

    def test_lance_descrito_em_palavras_e_problema(self) -> None:
        """'Leve o cavalo para f5' é dar o lance sem escrever a notação."""
        for frase in (
            "Leve o cavalo para f5 e veja o que acontece.",
            "Vale avançar o peão até h5.",
            "Pense em reposicionar a torre para a casa d1.",
        ):
            with self.subTest(frase=frase):
                problemas = problemas_da_resposta(resposta_valida(principio=frase))
                self.assertTrue(any("em palavras" in p for p in problemas))

    def test_casas_e_pecas_que_existem_podem_aparecer(self) -> None:
        resposta = resposta_valida(
            tipo_de_posicao=(
                "O bispo em c4 mira f7 e a casa d5 está fraca. O jogador que olhar para f7 "
                "entende o movimento das peças para a ala do rei."
            )
        )
        self.assertEqual(problemas_da_resposta(resposta), [])

    def test_roteiro_curto_ou_campos_vazios_sao_problema(self) -> None:
        resposta = resposta_valida(roteiro=resposta_valida().roteiro[:1], principio=" ")
        problemas = problemas_da_resposta(resposta)
        self.assertTrue(any("roteiro" in p for p in problemas))
        self.assertTrue(any("principio" in p for p in problemas))


class GerarRespostaTest(unittest.TestCase):
    def _json(self, resposta: RespostaConsulta) -> str:
        return resposta.model_dump_json()

    def test_resposta_boa_na_primeira_chamada(self) -> None:
        with patch.object(modulo, "call_gemini", return_value=self._json(resposta_valida())) as gemini:
            resposta, origem = gerar_resposta(object(), "prompt", ELEMENTOS, "BRANCAS", LOGGER)
        self.assertEqual(origem, "gemini")
        self.assertEqual(gemini.call_count, 1)
        self.assertIn("rei preto", resposta.tipo_de_posicao)

    def test_uma_correcao_e_so(self) -> None:
        ruim = self._json(resposta_valida(tipo_de_posicao="Jogue Nc3 agora."))
        bom = self._json(resposta_valida())
        with patch.object(modulo, "call_gemini", side_effect=[ruim, bom]) as gemini:
            _, origem = gerar_resposta(object(), "prompt", ELEMENTOS, "BRANCAS", LOGGER)
        self.assertEqual(origem, "gemini")
        self.assertEqual(gemini.call_count, 2)
        # A segunda chamada leva o motivo da rejeição.
        self.assertIn("proibido", gemini.call_args_list[1].args[1])

    def test_duas_violacoes_caem_no_fallback_sem_terceira_chamada(self) -> None:
        ruim = self._json(resposta_valida(tipo_de_posicao="Jogue Nc3 agora."))
        with patch.object(modulo, "call_gemini", side_effect=[ruim, ruim, ruim]) as gemini:
            resposta, origem = gerar_resposta(object(), "prompt", ELEMENTOS, "BRANCAS", LOGGER)
        self.assertEqual(origem, "fallback")
        self.assertEqual(gemini.call_count, 2)
        self.assertNotIn("Nc3", resposta.tipo_de_posicao)

    def test_json_invalido_conta_como_violacao(self) -> None:
        with patch.object(modulo, "call_gemini", side_effect=["não é json", self._json(resposta_valida())]):
            _, origem = gerar_resposta(object(), "prompt", ELEMENTOS, "BRANCAS", LOGGER)
        self.assertEqual(origem, "gemini")

    def test_falha_de_rede_nao_insiste(self) -> None:
        with patch.object(modulo, "call_gemini", side_effect=RuntimeError("429")) as gemini:
            _, origem = gerar_resposta(object(), "prompt", ELEMENTOS, "BRANCAS", LOGGER)
        self.assertEqual(origem, "fallback")
        self.assertEqual(gemini.call_count, 1)

    def test_fallback_deterministico_passa_nas_proprias_regras(self) -> None:
        resposta, origem = gerar_resposta(None, "prompt", ELEMENTOS, "BRANCAS", LOGGER)
        self.assertEqual(origem, "fallback")
        self.assertEqual(problemas_da_resposta(resposta), [])
        texto = " ".join(passo.o_que_avaliar for passo in resposta.roteiro)
        self.assertIn("c6", texto)  # o alvo real do adversário
        self.assertIn("tática", resposta.tipo_de_posicao)

    def test_fallback_nunca_repassa_os_lances_do_inspetor(self) -> None:
        """A lista de xeques e capturas do inspetor é feita de lances."""
        elementos = {
            **ELEMENTOS,
            "pecas_indefesas": {"BRANCAS": [], "PRETAS": []},
            "seguranca_rei": {},
            "ameacas_imediatas": {"cheques": ["Bxf7+"], "capturas": ["Nxe5"]},
        }
        resposta, _ = gerar_resposta(None, "prompt", elementos, "BRANCAS", LOGGER)
        self.assertEqual(problemas_da_resposta(resposta), [])
        self.assertNotIn("Bxf7", resposta.model_dump_json())
        self.assertIn("manobra", resposta.tipo_de_posicao)


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
            or resposta_valida(tipo_de_posicao="Centro em tensão.").model_dump()
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

    def test_como_pensar_nao_tem_lance_e_o_motor_fica_separado(self) -> None:
        """O que o jogador vê não tem lance; o motor fica numa chave interna,
        que o servidor grava para o desfecho e não devolve."""
        resultado, _ = self._consultar(["e4", "e5", "Nf3", "Nc6"], "BRANCAS")
        self.assertEqual(set(resultado["como_pensar"]), {"tipo_de_posicao", "sobre_o_seu_raciocinio", "roteiro", "principio"})
        for lance in ("d4", "Nc3", "c3"):
            self.assertNotIn(lance, json.dumps(resultado["como_pensar"]))
        self.assertEqual(resultado["motor"]["candidatos"], ["d4", "Nc3", "c3"])
        self.assertEqual(resultado["motor"]["melhor_lance"], "d4")

    def test_perspectiva_do_jogador(self) -> None:
        resultado, _ = self._consultar(["e4", "e5", "Nf3", "Nc6"], "brancas")
        self.assertEqual(resultado["cor_jogador"], "BRANCAS")
        self.assertEqual(resultado["numero_lance"], 3)
        self.assertEqual(resultado["motor"]["win_percent_jogador"], 54.1)
        self.assertEqual(resultado["gerado_por"], "gemini")
        self.assertEqual(resultado["lances_san"], ["e4", "e5", "Nf3", "Nc6"])

    def test_prompt_pede_metodo_e_proibe_dar_o_lance(self) -> None:
        _, chamada = self._consultar(["e4", "e5", "Nf3", "Nc6"], "BRANCAS")
        prompt = chamada.call_args.args[1]
        self.assertIn("COMO AVALIAR", prompt)
        self.assertIn("descrever lances em palavras", prompt)
        self.assertNotIn("ideias_candidatas", prompt)

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
