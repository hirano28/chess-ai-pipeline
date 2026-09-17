"""Servidor HTTP local (FastAPI) que expõe a revisão de exercícios avulsos.

Reaproveita processar_revisao_avulsa, resolver_posicao e salvar_exercicio de
backend/agentes/revisar_exercicio_avulso.py - a mesma lógica usada pelo
script interativo de linha de comando. Nenhum comportamento do script
interativo foi alterado; ele continua funcionando standalone.
"""

from __future__ import annotations

import base64
import hashlib
import os
import random
import re
import secrets
import sys
import threading
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import chess
import google.genai as genai
import requests
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from google.genai import types
from pydantic import BaseModel, Field
from stockfish import Stockfish


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from backend.agentes.agente1_linter import (  # noqa: E402
    load_settings as load_linter_settings,
)
from backend.agentes.agente2_analista import (  # noqa: E402
    HEXAGON_CATEGORIES,
    analisar_usuario as analisar_usuario_hexagono,
)
from backend.agentes.analisar_pgn_avulso import (  # noqa: E402
    executar_pipeline_partida,
    gerar_external_id,
    inserir_partida,
    parse_pgn,
    resolver_cor,
)
from backend.agentes.explicador_posicao import (  # noqa: E402
    ExplicacaoPosicao,
    explicar_posicao,
    salvar_explicacao_posicao,
)
from backend.agentes.insights_puzzles import (  # noqa: E402
    calcular_insights_puzzles,
)
from backend.agentes.insights_repertorio import (  # noqa: E402
    calcular_insights_repertorio,
)
from backend.agentes.popular_fila_treino_espacado import (  # noqa: E402
    resolver_citacao,
)
from backend.agentes.refazer_trecho import jogar_passo_do_trecho  # noqa: E402
from backend.agentes.revisar_exercicio_avulso import (  # noqa: E402
    EngineIndisponivelError,
    avaliar_lance_avulso,
    configure_console_logger,
    normalizar_lances,
    processar_revisao_sequencia,
    resolver_lance_usuario,
    resolver_posicao,
    salvar_exercicio,
)
from backend.agentes.revisar_pensamento import (  # noqa: E402
    carregar_passos_guia,
    classificar_qualidade_lance,
    load_settings,
)
from backend.analise_engine.analisar_partidas import (  # noqa: E402
    load_erosao_settings,
    load_settings as load_analysis_settings,
    update_status,
)
from backend.common.lichess_explorer import (  # noqa: E402
    detectar_saida_teoria,
)
from backend.common.lichess_oauth import (  # noqa: E402
    obter_access_token_lichess,
)
from backend.common.cadencia import CADENCIAS  # noqa: E402
from backend.common.progress import log_and_print  # noqa: E402
from backend.common.spaced_repetition import (  # noqa: E402
    atualizar_agendamento,
    nota_sm2_da_qualidade_lance,
)
from backend.common.treino_trecho import (  # noqa: E402
    ProgressoCorrompidoError,
    classificar_trecho,
    curva_do_trecho,
    elo_do_oponente,
    normalizar_progresso,
    progresso_inicial,
    queda_liquida_do_trecho,
    reconstruir_tabuleiro,
    resumo_do_veredito,
    total_lances_do_trecho,
)
from backend.common.syzygy_tablebase import (  # noqa: E402
    avaliar_lance_final_syzygy,
    consultar_syzygy,
)
from backend.ingestao.common_ingestao import create_supabase_client  # noqa: E402
from backend.ingestao.coletar_partidas import (  # noqa: E402
    Settings as SettingsLichess,
    coletar_para_perfil as coletar_lichess_para_perfil,
)
from backend.ingestao.coletar_partidas_chesscom import (  # noqa: E402
    coletar_para_perfil as coletar_chesscom_para_perfil,
    load_settings as carregar_settings_chesscom,
)

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:4200",
    "https://chess-ai-pipeline.vercel.app",
)

RECONHECER_POSICAO_MODEL = "gemini-flash-latest"
RECONHECER_POSICAO_MAX_BYTES = 10 * 1024 * 1024  # 10MB
RECONHECER_POSICAO_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}
RECONHECER_POSICAO_PROMPT = (
    "Esta é uma foto de um diagrama de posição de xadrez, possivelmente de um "
    "livro impresso. Identifique a posição exata das peças e retorne APENAS o "
    "FEN correspondente (Forsyth-Edwards Notation), sem nenhum texto adicional. "
    "Se não conseguir identificar quem joga (brancas ou pretas), assuma que é o "
    "lado indicado por qualquer seta ou anotação visual no diagrama; se não "
    "houver indicação, assuma brancas a jogar."
)
RECONHECER_POSICAO_ERRO_FEN_INVALIDO = (
    "Não foi possível reconhecer uma posição válida nesta imagem. Tente uma "
    "foto mais nítida, bem enquadrada, ou digite o FEN manualmente."
)

# D-32: limite diário por usuário nas rotas caras (Stockfish/Gemini). Nome da
# rota -> (variável de ambiente, default). Default usado quando a env var não
# está definida; "análise de partida inteira" é a mais cara, por isso o menor
# limite.
LIMITES_DIARIOS_ENV: dict[str, tuple[str, int]] = {
    "analisar-pgn": ("LIMITE_DIARIO_ANALISAR_PGN", 20),
    "explicar-posicao": ("LIMITE_DIARIO_EXPLICAR_POSICAO", 50),
    "revisar-avulso": ("LIMITE_DIARIO_REVISAR_AVULSO", 50),
    "reconhecer-posicao": ("LIMITE_DIARIO_RECONHECER_POSICAO", 30),
    # Auditoria pós-D-49: /reprocessar dispara o mesmo pipeline Stockfish+Gemini
    # de /analisar-pgn, mas não tinha teto — mesmo limite, mesmo motivo.
    "reprocessar": ("LIMITE_DIARIO_REPROCESSAR", 20),
    # /treino/{id}/responder só usa Stockfish (sem custo de API paga), mas
    # ainda serializa no engine_lock global (R3) — teto bem mais alto que as
    # rotas caras acima, só pra conter abuso/loop, não pra frear o uso normal
    # (o propósito do D-48 é permitir muitas repetições por dia).
    "treino-responder": ("LIMITE_DIARIO_TREINO_RESPONDER", 200),
    # D-66: um card de trecho gasta 8 requisições (uma por lance da janela),
    # cada uma com 3 interações com o motor. Contar na mesma cota de
    # /responder faria um único trecho parecer 8 revisões e esgotaria o dia
    # cedo demais; o teto próprio é maior pelo mesmo motivo, e continua sendo
    # um freio de abuso contra o engine_lock (R3), não do uso normal.
    "treino-trecho": ("LIMITE_DIARIO_TREINO_TRECHO", 400),
    # D-65: a importação sob demanda dispara coleta + Stockfish + Agente 1 de
    # várias partidas de uma vez. É a rota mais cara que existe, por isso o
    # menor teto — ela serve ao onboarding ("quero ver meu Hexágono agora"),
    # não ao uso repetido; para o dia a dia existe o pipeline diário.
    "importar-partidas": ("LIMITE_DIARIO_IMPORTAR_PARTIDAS", 3),
}
MENSAGEM_LIMITE_DIARIO = "Limite diário atingido, tente novamente amanhã."

# D-49: quantos exercícios do catálogo tático entram na fila de uma vez
# quando o usuário clica "Focar" numa categoria (mesmo padrão de
# configuração por env var de TREINO_NOVOS_POR_DIA, D-48).
TREINO_FOCO_QTD_EXERCICIOS = int(os.getenv("TREINO_FOCO_QTD_EXERCICIOS", "8"))

# D-54: quantos exercícios entram no bloco de prática ao INICIAR uma sessão de
# treino focado. Maior que o "Focar" avulso acima de propósito: a sessão é o
# formato longo com objetivo fechado, o "Focar" é o incremento rápido na fila
# do dia.
SESSAO_QTD_EXERCICIOS = int(os.getenv("SESSAO_QTD_EXERCICIOS", "12"))

# D-56: teto de cards mostrados de uma vez em GET /treino/fila. A população
# acrescenta 10 novos por dia (D-48) independentemente do consumo, então o que
# não é respondido vira atraso acumulado — sem teto, a tela um dia abre com
# centenas de cards, que é a forma mais eficiente de fazer alguém desistir.
# O contador `vencidos_total` continua dizendo a verdade sobre o tamanho real.
TREINO_TETO_FILA = int(os.getenv("TREINO_TETO_FILA", "20"))

# Rótulos legíveis das chaves de HEXAGON_CATEGORIES. O frontend tem a mesma
# tabela (ROTULOS_CATEGORIA_HEXAGONO em treino.service.ts) para os seus
# próprios textos; aqui ela serve ao nome do bloco de prática (D-54), que é
# montado no backend e chega pronto na tela.
ROTULOS_CATEGORIA: dict[str, str] = {
    "TATICA": "Tática",
    "ESTRATEGIA": "Estratégia",
    "FINAIS": "Finais",
    "ESTRUTURA_DE_PEOES": "Estrutura de Peões",
    "GESTAO_DE_TEMPO": "Gestão de Tempo",
    "CALCULO": "Cálculo",
}

# D-33: OAuth do Lichess (Authorization Code + PKCE). Endpoints confirmados na
# doc oficial: o Lichess aceita cliente público NÃO registrado (client_id é uma
# string livre, sem client_secret), exige PKCE e só aceita o método S256.
LICHESS_OAUTH_AUTHORIZE_URL = "https://lichess.org/oauth"
LICHESS_OAUTH_TOKEN_URL = "https://lichess.org/api/token"
LICHESS_OAUTH_CLIENT_ID_PADRAO = "chess-ai-pipeline"
LICHESS_OAUTH_REDIRECT_URI_PADRAO = "http://localhost:8000/lichess/oauth/callback"
# `puzzle:read` é o escopo exigido por GET /api/puzzle/activity, o primeiro
# consumidor previsto (Estágio 2). Ampliar aqui exige reconectar as contas:
# um token já emitido carrega só os escopos pedidos na hora da autorização.
LICHESS_OAUTH_SCOPES_PADRAO = "puzzle:read"
LICHESS_OAUTH_PKCE_TTL_MINUTOS = 10
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS)).split(",")
    if origin.strip()
]

app = FastAPI(title="Chess AI Pipeline - API de revisão avulsa")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Recursos inicializados uma única vez na subida do servidor (ver startup/shutdown).
_state: dict[str, Any] = {}


class RevisarAvulsoRequest(BaseModel):
    """Payload de entrada: posição (FEN ou PGN), lance(s) e pensamento do jogador.

    Aceita 'lance' (string única, compat) OU 'lances' (lista SAN na ordem em que
    ocorrem a partir da posição). Quando ambos vêm, 'lances' tem prioridade.
    """

    posicao: str
    lance: str | None = None
    lances: list[str] | None = None
    pensamento: str


class AvaliacaoSequenciaItem(BaseModel):
    """Avaliação de um único lance DO JOGADOR dentro da sequência."""

    indice_na_sequencia: int
    lance_jogado: str
    # Mesmo lance em notação portuguesa (C/T/D/R/B), como foi efetivamente
    # entendido — deixa visível ao usuário como lemos 'R' (Rei) vs 'T' (Torre).
    lance_interpretado: str = ""
    melhor_lance: str | None
    queda_win_percent: float
    qualidade_lance: str
    qualidade_raciocinio: str
    feedback_texto: str
    analise_mestre: str
    top_candidatos: list[dict] = Field(default_factory=list)
    checklist_rotina: dict[str, str] = Field(default_factory=dict)


class RevisarAvulsoResponse(BaseModel):
    """Resultado da revisão de uma sequência, pronto para exibição no dashboard.

    'avaliacoes' tem um item por lance DO JOGADOR (para um lance único, 1 item).
    'lances' lista todos os lances aplicados (jogador + adversário), em SAN.
    'lance_interpretado' é o 1º lance do jogador em português, como foi entendido.
    """

    fen: str
    lances: list[str]
    lance_interpretado: str = ""
    avaliacoes: list[AvaliacaoSequenciaItem]
    resumo_geral: str | None = None


class SalvarAvulsoRequest(BaseModel):
    """Payload de um exercício (um lance do jogador) a persistir, mais fen/pensamento."""

    lance_jogado: str
    melhor_lance: str | None
    queda_win_percent: float
    qualidade_lance: str
    qualidade_raciocinio: str
    feedback_texto: str
    analise_mestre: str
    top_candidatos: list[dict] = Field(default_factory=list)
    fen: str
    texto_pensamento: str


class SalvarAvulsoResponse(BaseModel):
    """Confirmação de que o exercício foi salvo, com o id da linha criada."""

    status: str
    id: str | None = None


class RevisaoAvulsaRecenteItem(BaseModel):
    """Item do histórico de exercícios avulsos já salvos manualmente pelo usuário.

    Espelha 1:1 as colunas persistidas por salvar_exercicio() em
    revisao_exercicio_avulso - não há campos além destes porque o schema não
    guarda top_candidatos/analise_mestre/checklist_rotina/lance_interpretado.
    """

    id: str
    fen: str
    lance_jogado: str
    melhor_lance: str | None = None
    queda_win_percent: float | None = None
    texto_pensamento: str | None = None
    qualidade_lance: str | None = None
    qualidade_raciocinio: str | None = None
    feedback_texto: str | None = None
    created_at: str | None = None


class ResolverFenResponse(BaseModel):
    """Resposta com o FEN final resolvido a partir de uma FEN ou PGN."""

    fen: str


class TrechoEmAndamento(BaseModel):
    """Estado do "Refazer o trecho" de um card de EROSAO (D-66).

    Vai junto do card porque o trecho sobrevive a fechar o navegador: quem
    voltar no meio precisa ver a posição onde parou e os lances que já jogou.

    O que NÃO vem aqui é a avaliação de cada lance. Erosão é justamente o que
    se perde sem perceber — um "-4%" a cada lance transformaria a janela em
    oito exercícios táticos com placar, e o drill deixaria de medir o que
    nomeia. A curva inteira aparece de uma vez no fim.
    """

    total_lances: int
    lances_feitos: int
    historico: list[str] = Field(default_factory=list)


class ItemFilaTreino(BaseModel):
    """Um card pendente de revisão hoje (D-48; D-49 acrescentou a origem
    'exercicio_tatico', do catálogo importado do Lichess).

    Deliberadamente NÃO inclui tags_falha/raiz_conceitual_violada nem a
    citação do livro: revelar a causa do erro antes do usuário tentar o
    lance transformaria o treino numa consulta, não num teste.
    """

    fila_id: int
    fen: str
    origem: str
    # D-66: 'PICO' (um lance) ou 'EROSAO' (a janela inteira, refeita contra o
    # motor). Só vem em card de lance próprio; o que muda o formato é este
    # campo, não `origem` - um card de erosão continua sendo um lance crítico
    # do usuário.
    tipo_evento: str | None = None
    numero_lance_fim: int | None = None
    trecho: TrechoEmAndamento | None = None
    numero_lance: int | None = None
    cor_jogada: str | None = None
    data_partida: str | None = None
    plataforma: str | None = None
    categoria: str | None = None
    # Único dado do exercício posicional que vem ANTES da resposta (D-55): nos
    # cards de GESTAO_DE_TEMPO o relógio é o exercício, não um detalhe - o
    # usuário decide com o mesmo tempo que o jogador original tinha.
    segundos_sugeridos: int | None = None
    repeticoes: int
    total_revisoes: int


class FilaTreinoResponse(BaseModel):
    """Fila de hoje + contadores para o indicador de progresso do frontend."""

    itens: list[ItemFilaTreino]
    feitas_hoje: int
    total_hoje: int
    # D-56: `itens` é limitado por TREINO_TETO_FILA; `vencidos_total` é quantos
    # de fato venceram. Sem os dois números a tela mentiria por omissão — ou
    # despejaria centenas de cards, ou esconderia o tamanho do atraso.
    vencidos_total: int = 0
    # Preenchido quando a fila veio filtrada por uma sessão de treino (D-56).
    sessao_id: str | None = None


class ResponderTreinoRequest(BaseModel):
    """Payload da resposta a um card: só o lance (ver D-48 - sem raciocínio).

    `segundos_gastos` existe apenas para os cards de GESTAO_DE_TEMPO (D-55),
    onde o relógio É o exercício. Vem do cliente, e num app de um usuário só
    isso basta: quem burlaria estaria burlando a si mesmo.
    """

    lance: str
    segundos_gastos: int | None = None


class ResponderTreinoResponse(BaseModel):
    """Revelação completa após responder: qualidade, causa raiz e citação.

    raiz_conceitual_violada/tags_falha só vêm preenchidos pra cards de
    lance próprio (D-48) - exercícios de catálogo (D-49) não têm um
    `diagnosticos` associado, a explicação do "porquê" já vem da avaliação
    do Stockfish + melhor lance.
    """

    qualidade_lance: str
    lance_interpretado: str = ""
    melhor_lance: str | None
    queda_win_percent: float
    raiz_conceitual_violada: str | None = None
    tags_falha: list[str] = Field(default_factory=list)
    livro_citado: str | None = None
    capitulo_citado: str | None = None
    pagina_citada: int | None = None
    # D-55: só para exercícios posicionais. A procedência é revelada DEPOIS de
    # responder - antes seria contexto que o exercício não dá ao jogador
    # original, e depois é o que transforma a posição em partida de verdade
    # ("isto foi GM Moranda x CM Klepek"). Também é a atribuição que a licença
    # CC BY-SA dos broadcasts exige.
    partida_referencia: str | None = None
    partida_url: str | None = None
    # D-55: o lance pode ter sido bom E ter estourado o relógio. Os dois fatos
    # convivem, e por isso são dois campos: `qualidade_lance` continua dizendo
    # a verdade sobre o lance, e isto diz a verdade sobre o tempo — que é o que
    # estava sendo treinado naquele card.
    fora_do_tempo: bool = False
    proxima_revisao_data: str
    repeticoes: int


class TrechoRequest(BaseModel):
    """Um lance do jogador dentro do trecho sendo refeito (D-66).

    Não carrega posição: a do servidor vem do replay do histórico gravado, e é
    a única que vale. O cliente só diz o que jogaria.
    """

    lance: str


class LanceDaCurvaResponse(BaseModel):
    """Quanto cada lance do jogador custou, na revelação do fim do trecho."""

    numero: int
    lance: str
    win_antes: float
    win_depois: float
    queda: float


class TrechoResponse(BaseModel):
    """Resposta de POST /treino/{fila_id}/trecho (D-66).

    Enquanto o trecho corre, só os campos de andamento vêm preenchidos - o
    jogador vê a resposta do motor e a posição nova, e nada sobre quanto
    perdeu. Os campos de veredito só aparecem com `concluido = true`, e aí de
    uma vez: a queda líquida, a curva lance a lance, a comparação com a
    partida e o reagendamento do SM-2.
    """

    lance_interpretado: str
    lance_oponente: str | None = None
    fen: str
    lances_feitos: int
    total_lances: int
    historico: list[str] = Field(default_factory=list)
    concluido: bool
    # A partida acabou dentro do trecho (mate ou empate). O veredito sai da
    # posição real onde parou, e não é erro: é o desfecho mais informativo que
    # o drill pode dar.
    fim_de_partida: bool = False

    qualidade_lance: str | None = None
    queda_liquida: float | None = None
    queda_original: float | None = None
    resumo: str | None = None
    curva: list[LanceDaCurvaResponse] = Field(default_factory=list)
    raiz_conceitual_violada: str | None = None
    tags_falha: list[str] = Field(default_factory=list)
    livro_citado: str | None = None
    capitulo_citado: str | None = None
    pagina_citada: int | None = None
    proxima_revisao_data: str | None = None
    repeticoes: int | None = None


class FocoTreinoResponse(BaseModel):
    """Resposta de POST /treino/foco/{categoria} (D-49).

    `motivo` só é preenchido quando `adicionados == 0`, para o frontend poder
    explicar QUAL dos dois zeros aconteceu em vez de mandar o usuário para uma
    fila que não mudou (D-52):

    - `sem_catalogo`: a categoria não tem nenhum exercício importado. Hoje é o
      caso real de ESTRATEGIA e GESTAO_DE_TEMPO — ver o achado honesto no D-49
      sobre o Lichess não ter tema equivalente a relógio.
    - `ja_na_fila`: existe catálogo, mas o usuário já tem todos na fila dele.
    """

    adicionados: int
    motivo: str | None = None


class DisponibilidadeFocoResponse(BaseModel):
    """Quantos exercícios de catálogo existem por categoria do Hexágono (D-53).

    Sempre traz as 6 chaves de `HEXAGON_CATEGORIES`, com 0 nas que não têm
    nenhum exercício importado. Existe para a tela não oferecer um botão
    "Focar" que ela já sabe que não vai levar a lugar nenhum: avisar depois do
    clique (D-52) foi o remendo, não oferecer o beco é a correção.
    """

    por_categoria: dict[str, int]


class ImportacaoResponse(BaseModel):
    """Retorno do disparo da importação sob demanda (D-65)."""

    iniciada: bool
    fontes: list[str]
    detalhe: str


class StatusImportacaoResponse(BaseModel):
    """Progresso da importação, para a tela poder acompanhar (D-65).

    Não existe tabela de "job": o progresso é lido do próprio dado que está
    sendo produzido (`partidas.status_processamento`, diagnósticos, hexágono).
    Uma tabela de controle poderia divergir do que de fato aconteceu; estas
    contagens não têm como.
    """

    partidas: int
    pendentes: int
    processando: int
    concluidas: int
    diagnosticos: int
    tem_hexagono: bool
    em_andamento: bool
    pronto: bool


class ComposicaoCadenciaResponse(BaseModel):
    """Distribuição das partidas analisadas por cadência (D-57).

    Existe para tornar VISÍVEL a maior ressalva do diagnóstico do produto: se
    a esmagadora maioria do corpus é blitz, "seu gargalo é tática" carrega
    junto o efeito do relógio, e o usuário merece saber disso na mesma tela em
    que lê o gargalo — não numa nota de rodapé da documentação.
    """

    por_cadencia: dict[str, int]
    total: int
    dominante: str | None = None
    percentual_dominante: float = 0.0


class BlocoSessaoResponse(BaseModel):
    """Um passo executável da sessão de treino focado (D-54).

    Dois tipos, com origens deliberadamente diferentes:

    - `estudo`: vem de um módulo prescrito pelo Agente 3 (livro/capítulo/
      página). Conclui-se marcando como lido — é leitura, não dá para o
      sistema verificar sozinho.
    - `pratica`: NÃO vem do LLM. É montado pelo backend a partir da categoria
      do gargalo, com exercícios reais do catálogo. Conclui-se sozinho quando
      os exercícios são respondidos, e é isso que dá à sessão um fim objetivo
      em vez de um botão de "eu acho que terminei".
    """

    indice: int
    tipo: str
    nome: str
    conteudo: str | None = None
    duracao_min: int | None = None
    livro: str | None = None
    capitulo: str | None = None
    pagina_aprox: int | None = None
    concluido: bool
    # Só preenchidos quando tipo == 'pratica'.
    categoria: str | None = None
    exercicios_feitos: int | None = None
    exercicios_total: int | None = None


class ExecucaoSessaoResponse(BaseModel):
    """Estado de execução de uma sessão de treino focado (D-54)."""

    sessao_id: str
    titulo: str
    categoria_foco: str | None
    data_prescrita: str
    data_iniciada: str | None
    data_concluida: str | None
    duracao_total_min: int
    blocos: list[BlocoSessaoResponse]
    concluida: bool


class ExplicarPosicaoRequest(BaseModel):
    """Payload para requisição de explicação didática da posição."""

    posicao: str
    lado: str | None = None


class IniciarOauthLichessResponse(BaseModel):
    """URL de autorização do Lichess para o frontend redirecionar (D-33).

    Só a URL sai daqui: o `code_verifier` do PKCE fica exclusivamente no banco,
    do lado do servidor — se ele trafegasse até o navegador, o PKCE deixaria de
    proteger contra a interceptação do código de autorização.
    """

    url_autorizacao: str
    expira_em: str


class LichessOauthStatusResponse(BaseModel):
    """Status da conexão OAuth com o Lichess do usuário (D-35)."""

    conectado: bool
    expires_at: str | None = None


class AvaliacaoObjetiva(BaseModel):
    """Avaliação quantitativa do Stockfish e probabilidades de vitória."""

    score_cp: int
    mate: int | None = None
    win_percent: float
    lado_vencedor: str
    descricao: str


class LinhaTaticaItem(BaseModel):
    """Uma linha candidata do motor com avaliação e sequência em SAN."""

    lance: str
    avaliacao: str
    pv_san: list[str] = Field(default_factory=list)


class RefutacaoDefesaItem(BaseModel):
    """A melhor defesa adversária e a respectiva linha de refutação."""

    defesa: str
    refutacao_linha: list[str] = Field(default_factory=list)
    detalhes: str


class ExplicarPosicaoResponse(BaseModel):
    """Resposta estruturada do explicador de posição."""

    # id da linha criada em explicacoes_posicao (None se a persistência falhar -
    # a explicação em si ainda é devolvida normalmente, ver explicar_posicao_endpoint).
    id: str | None = None
    fen: str
    lado_a_jogar: str
    lado_analisado: str
    avaliacao: AvaliacaoObjetiva
    linhas_taticas: list[LinhaTaticaItem] = Field(default_factory=list)
    refutacao_defesa: RefutacaoDefesaItem | None = None
    elementos_posicionais: dict[str, Any]
    explicacao: ExplicacaoPosicao


class ExplicacaoPosicaoRecenteItem(BaseModel):
    """Item do histórico de explicações de posição já geradas.

    'resultado' embute a resposta completa (mesmo shape de
    ExplicarPosicaoResponse), então restaurar um item do histórico no
    frontend não precisa de uma segunda chamada "buscar por id" - a linha já
    tem tudo o que a tela de resultado precisa para renderizar de novo.
    """

    id: str
    fen: str
    lado_analisado: str | None = None
    created_at: str | None = None
    resultado: dict[str, Any]


class AnalisarPgnRequest(BaseModel):
    """Payload para requisição de análise completa de uma partida PGN avulsa."""

    pgn: str
    cor: str | None = None


class AnalisarPgnResponse(BaseModel):
    """Resposta imediata com status 202 aceito para processamento em segundo plano."""

    partida_id: str
    external_id: str


class ResumoPartidaResponse(BaseModel):
    """Resposta com o status do processamento e os dados da narrativa se concluído."""

    partida_id: str
    external_id: str | None = None
    status: str
    resumo: dict[str, Any] | None = None


class ReconhecerPosicaoResponse(BaseModel):
    """Resposta com o FEN reconhecido a partir da foto de um diagrama."""

    fen: str


class PartidaRecenteItem(BaseModel):
    """Item resumido do histórico de análises de partidas."""

    partida_id: str
    external_id: str | None = None
    status: str
    cor_jogada: str | None = None
    resultado: str | None = None
    eco_abertura: str | None = None
    data_partida: str | None = None
    created_at: str | None = None
    jogadores: str | None = None
    fen_final: str | None = None


def extrair_jogadores_pgn(pgn_text: str | None) -> str:
    """Extrai nomes dos jogadores do cabeçalho PGN (ex: 'White vs Black')."""
    if not pgn_text:
        return "Partida Manual"
    w_match = re.search(r'\[White\s+"([^"]+)"\]', pgn_text)
    b_match = re.search(r'\[Black\s+"([^"]+)"\]', pgn_text)
    w_name = w_match.group(1).strip() if w_match else "Brancas"
    b_name = b_match.group(1).strip() if b_match else "Pretas"
    return f"{w_name} vs {b_name}"


def extrair_fen_final_pgn(pgn_text: str | None) -> str | None:
    """Reconstrói a posição final do PGN, para a miniatura do histórico.

    Parsing puro e local (python-chess), sem Stockfish nem Gemini: é só o
    "retrato" que permite bater o olho e reconhecer de qual partida a linha
    do histórico está falando. PGN ausente, truncado ou inválido devolve
    None e a lista simplesmente não mostra miniatura naquela linha — nunca
    derruba o histórico inteiro por causa de uma partida malformada.
    """
    if not pgn_text:
        return None
    try:
        return parse_pgn(pgn_text).end().board().fen()
    except Exception:
        return None


def _limpar_fen_bruto(texto: str) -> str:
    """Remove fences markdown e rótulos residuais que o Gemini possa incluir
    apesar da instrução de responder só com o FEN."""

    limpo = texto.strip()
    limpo = re.sub(r"^```(?:\w+)?\s*", "", limpo)
    limpo = re.sub(r"\s*```$", "", limpo)
    limpo = re.sub(r"(?i)^fen\s*[:=]\s*", "", limpo.strip())
    return limpo.strip()


@app.on_event("startup")
def iniciar_recursos() -> None:
    """Inicializa Stockfish, Gemini e Supabase uma única vez para todo o servidor."""

    settings = load_settings()
    _state["settings"] = settings
    _state["logger"] = configure_console_logger()
    _state["gemini_client"] = genai.Client(api_key=settings.gemini_api_key)
    _state["supabase_client"] = create_supabase_client(
        settings.supabase_url, settings.supabase_service_role_key
    )
    _state["engine"] = Stockfish(
        path=settings.stockfish_path,
        depth=settings.stockfish_depth,
        turn_perspective=False,
    )
    # Serializa o acesso ao engine compartilhado entre requisições concorrentes.
    _state["engine_lock"] = threading.Lock()

    _state["limites_diarios"] = _resolver_limites_diarios()
    _state["lichess_oauth"] = _resolver_config_lichess_oauth()


@app.on_event("shutdown")
def encerrar_recursos() -> None:
    """Fecha o Stockfish corretamente ao desligar o servidor."""

    engine = _state.get("engine")
    if engine is not None:
        try:
            engine.send_quit_command()
        except Exception:
            pass


def resolver_user_id_da_sessao(token: str) -> str | None:
    """Valida um token de sessão do Supabase Auth via `auth.get_user()`.

    Devolve o `user.id` real quando o token é válido; `None` em qualquer
    outro caso (token expirado/malformado, banco indisponível) — nunca
    levanta exceção, porque isto é só o primeiro passo de uma resolução com
    fallback (ver `verificar_sessao`, que transforma o `None` em 401).
    """

    client = _state.get("supabase_client")
    if not client:
        return None
    try:
        resposta = client.auth.get_user(token)
    except Exception:
        return None
    user = getattr(resposta, "user", None) if resposta else None
    return user.id if user else None


def resolver_usernames_do_perfil(client: Any, user_id: str) -> list[str]:
    """Busca o(s) username(s) de Lichess/Chess.com de `user_id` em perfis_usuario.

    Alimenta a inferência de cor de `/analisar-pgn` (D-28): sem isso, o
    auto-detect só reconheceria o username fixo do `.env` (sempre o mesmo
    dono), então colar o PGN de outra pessoa logada nunca acertaria a cor
    sozinho. Retorna lista vazia (nunca lança) se o perfil não existir ainda
    ou a consulta falhar - o pior caso é cair no fallback de pedir a cor
    explicitamente, não um erro.
    """

    try:
        resposta = (
            client.table("perfis_usuario")
            .select("lichess_username, chesscom_username")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception:
        return []
    perfil = resposta.data if resposta else None
    if not perfil:
        return []
    return [
        perfil[coluna]
        for coluna in ("lichess_username", "chesscom_username")
        if perfil.get(coluna)
    ]


def verificar_sessao(request: Request) -> str:
    """Exige sessão real do Supabase Auth ANTES de qualquer rota executar.

    Gate único de acesso da API desde D-25, no lugar do antigo esquema de
    header `X-API-Key` (removido de vez na auditoria pós-D-49 — nenhuma rota
    dependia mais dele). Rodando antes do corpo da rota, um token ausente ou
    inválido nunca chega a consumir Stockfish, cota do Gemini ou banco.

    Devolve o `user.id` real — as rotas que precisam do dono (escrita nas
    tabelas raiz, leitura filtrada) recebem esse valor por injeção, sem
    revalidar o token. Não existe mais fallback pro `DEFAULT_USER_ID` neste
    caminho: quem chega aqui tem dono garantido e real.
    """

    auth_header = request.headers.get("Authorization")
    token = ""
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Sessão ausente. Faça login para usar esta funcionalidade.",
        )

    user_id = resolver_user_id_da_sessao(token)
    if not user_id:
        raise HTTPException(
            status_code=401, detail="Sessão inválida ou expirada. Faça login de novo."
        )

    request.state.user_id = user_id
    timestamp = datetime.now(timezone.utc).isoformat()
    mensagem = f"Requisição autorizada para o usuário {user_id} em {timestamp}"
    logger = _state.get("logger")
    if logger is not None:
        log_and_print(logger, mensagem)
    else:
        print(mensagem)

    return user_id


def _resolver_config_lichess_oauth() -> dict[str, str]:
    """Lê a configuração do OAuth do Lichess do ambiente (D-33).

    Nada aqui é segredo: o Lichess não usa `client_secret` (cliente público,
    sem registro prévio), então essas variáveis são só configuração de
    ambiente — o `redirect_uri` precisa bater exatamente entre a autorização e
    a troca do código, e é o que muda entre rodar local e rodar no Cloud Run.
    """

    return {
        "client_id": os.getenv("LICHESS_OAUTH_CLIENT_ID", LICHESS_OAUTH_CLIENT_ID_PADRAO),
        "redirect_uri": os.getenv(
            "LICHESS_OAUTH_REDIRECT_URI", LICHESS_OAUTH_REDIRECT_URI_PADRAO
        ),
        "scopes": os.getenv("LICHESS_OAUTH_SCOPES", LICHESS_OAUTH_SCOPES_PADRAO),
        "frontend_url": os.getenv(
            "FRONTEND_URL", ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else ""
        ).rstrip("/"),
    }


def _gerar_par_pkce() -> tuple[str, str]:
    """Gera (code_verifier, code_challenge) do PKCE no método S256.

    `token_urlsafe(64)` produz ~86 caracteres do alfabeto que a RFC 7636 exige
    (A-Z a-z 0-9 - _), dentro da faixa obrigatória de 43 a 128.
    """

    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def _redirecionar_para_frontend(parametro: str) -> RedirectResponse:
    """Devolve o usuário ao `/perfil` do frontend com um marcador do resultado.

    Nenhum token, código ou `state` vai na URL: o navegador guarda histórico,
    e o `Referer` de qualquer recurso carregado depois vazaria o que estivesse
    aqui. O frontend só recebe "deu certo" ou "deu errado, por quê".
    """

    base = _state.get("lichess_oauth", {}).get("frontend_url", "")
    return RedirectResponse(url=f"{base}/perfil?{parametro}", status_code=303)


def _resolver_limites_diarios() -> dict[str, int]:
    """Lê os limites diários por rota do ambiente (D-32), com os defaults do código."""

    limites: dict[str, int] = {}
    for rota, (env_var, default) in LIMITES_DIARIOS_ENV.items():
        raw = os.getenv(env_var, str(default))
        try:
            limites[rota] = int(raw)
        except ValueError as error:
            raise RuntimeError(
                f"Variável de ambiente {env_var} deve ser um inteiro (recebeu {raw!r})."
            ) from error
    return limites


def limite_diario(rota: str):
    """Cria uma dependency que verifica e incrementa o uso diário de `rota` (D-32).

    Roda ANTES do corpo da rota, mesmo princípio de "falhar rápido" de
    `verificar_sessao`: conta a chamada atomicamente via RPC
    (`incrementar_uso_diario`, que reseta à meia-noite de America/Sao_Paulo) e
    barra com 429 antes de qualquer trabalho caro (Stockfish/Gemini) se o
    limite do dia já foi atingido. Reaproveita `verificar_sessao` como
    sub-dependency - o FastAPI cacheia por requisição, então a sessão não é
    validada duas vezes.
    """

    def _verificar_limite(user_id: str = Depends(verificar_sessao)) -> str:
        client = _state.get("supabase_client")
        if client is None:
            raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

        try:
            resposta = client.rpc(
                "incrementar_uso_diario", {"p_user_id": user_id, "p_rota": rota}
            ).execute()
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"Falha ao registrar uso diário: {error}",
            ) from error

        contagem = resposta.data
        limite = _state.get("limites_diarios", {}).get(rota)
        if limite is not None and contagem is not None and contagem > limite:
            raise HTTPException(status_code=429, detail=MENSAGEM_LIMITE_DIARIO)

        return user_id

    return _verificar_limite


# Instâncias nomeadas (não criadas inline no decorator) para que os testes
# possam sobrescrever cada limite individualmente via
# `app.dependency_overrides`, do mesmo jeito que já fazem com `verificar_sessao`.
verificar_limite_analisar_pgn = limite_diario("analisar-pgn")
verificar_limite_explicar_posicao = limite_diario("explicar-posicao")
verificar_limite_revisar_avulso = limite_diario("revisar-avulso")
verificar_limite_reconhecer_posicao = limite_diario("reconhecer-posicao")
verificar_limite_reprocessar = limite_diario("reprocessar")
verificar_limite_treino_responder = limite_diario("treino-responder")
verificar_limite_treino_trecho = limite_diario("treino-trecho")
verificar_limite_importar = limite_diario("importar-partidas")


@app.post(
    "/revisar-avulso",
    response_model=RevisarAvulsoResponse,
)
def revisar_avulso(
    payload: RevisarAvulsoRequest,
    user_id: str = Depends(verificar_limite_revisar_avulso),
) -> RevisarAvulsoResponse:
    """Avalia um exercício avulso (lance único ou sequência) e retorna o feedback."""

    try:
        lances_san = normalizar_lances(payload.lances, payload.lance)
        board = resolver_posicao(payload.posicao)
        fen = board.fen()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        resultado = processar_revisao_sequencia(
            _state["engine"],
            _state["gemini_client"],
            _state["settings"],
            _state["logger"],
            fen,
            lances_san,
            payload.pensamento,
            _state["engine_lock"],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except EngineIndisponivelError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao processar a revisão: {error}"
        ) from error

    return RevisarAvulsoResponse(**resultado)


@app.get(
    "/resolver-fen",
    response_model=ResolverFenResponse,
    dependencies=[Depends(verificar_sessao)],
)
def resolver_fen_endpoint(posicao: str) -> ResolverFenResponse:
    """Converte uma FEN ou PGN em FEN final - só parsing local (sem Gemini/Stockfish).

    Reaproveita resolver_posicao (mesma usada por /revisar-avulso) para que o
    frontend possa pré-visualizar o tabuleiro enquanto o usuário digita, sem
    o custo/latência de uma chamada real ao motor ou ao LLM.
    """

    try:
        board = resolver_posicao(posicao)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return ResolverFenResponse(fen=board.fen())


@app.post("/revisar-avulso/salvar", response_model=SalvarAvulsoResponse)
def revisar_avulso_salvar(
    payload: SalvarAvulsoRequest, user_id: str = Depends(verificar_sessao)
) -> SalvarAvulsoResponse:
    """Persiste um exercício já revisado em revisao_exercicio_avulso.

    O dono vem da sessão, garantido e real — `verificar_sessao` já barrou com
    401 quem não tinha token válido (D-25).
    """

    resultado = {
        "lance_jogado": payload.lance_jogado,
        "melhor_lance": payload.melhor_lance,
        "queda_win_percent": payload.queda_win_percent,
        "qualidade_lance": payload.qualidade_lance,
        "qualidade_raciocinio": payload.qualidade_raciocinio,
        "feedback_texto": payload.feedback_texto,
    }
    try:
        novo_id = salvar_exercicio(
            _state["supabase_client"],
            payload.fen,
            payload.texto_pensamento,
            resultado,
            user_id=user_id,
        )
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao salvar o exercício: {error}"
        ) from error

    return SalvarAvulsoResponse(status="salvo", id=novo_id)


@app.get("/revisoes-avulsas/recentes", response_model=list[RevisaoAvulsaRecenteItem])
def listar_revisoes_avulsas_recentes(
    limite: int = 20, user_id: str = Depends(verificar_sessao)
) -> list[RevisaoAvulsaRecenteItem]:
    """Retorna o histórico de exercícios avulsos já salvos manualmente (revisao_exercicio_avulso).

    Filtrado pelo dono da sessão (D-18). O `service role` usado pelo backend
    ignora RLS, então este filtro é o único isolamento entre contas nesta rota.
    """
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    try:
        resp = (
            client.table("revisao_exercicio_avulso")
            .select(
                "id, fen, lance_jogado, melhor_lance, queda_win_percent, "
                "texto_pensamento, qualidade_lance, qualidade_raciocinio, "
                "feedback_texto, created_at"
            )
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(min(limite, 50))
            .execute()
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao consultar histórico de exercícios avulsos: {error}",
        ) from error

    return [RevisaoAvulsaRecenteItem(**row) for row in resp.data or []]


def _hoje_america_sao_paulo() -> date:
    """Mesmo fuso de `incrementar_uso_diario` (D-32): a virada é à meia-noite
    local do usuário, não em UTC (America/Sao_Paulo é UTC-3)."""

    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


@app.get("/treino/fila", response_model=FilaTreinoResponse)
def obter_fila_treino(
    sessao_id: str | None = None, user_id: str = Depends(verificar_sessao)
) -> FilaTreinoResponse:
    """Lista os cards de repetição espaçada vencidos hoje (D-48).

    Não revela tags_falha, causa raiz nem citação de livro - isso só aparece
    na resposta de POST /treino/{fila_id}/responder, depois de tentar o lance.

    Com `sessao_id` (D-56), devolve SÓ os exercícios do bloco de prática
    daquela sessão que ainda não foram respondidos. Sem isso, o botão "Ir para
    os exercícios" da sessão levava a uma fila onde os 12 cards dela ficavam
    atrás de dezenas de outros vencidos: a sessão tinha começo e fim, mas
    nenhum caminho reto entre os dois.
    """
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    hoje = _hoje_america_sao_paulo()
    inicio_do_dia = datetime.combine(hoje, time.min, tzinfo=ZoneInfo("America/Sao_Paulo"))

    ids_da_sessao: list[int] | None = None
    if sessao_id:
        sessao = _buscar_sessao(client, sessao_id, user_id)
        bruto = sessao.get("progresso")
        progresso = bruto if isinstance(bruto, dict) else {}
        ids_da_sessao = [
            item for item in progresso.get("fila_ids") or [] if isinstance(item, int)
        ]
        if not ids_da_sessao:
            # Sessão ainda não iniciada, ou categoria sem catálogo: fila vazia
            # é a resposta honesta - devolver a fila inteira seria ignorar o
            # filtro que o usuário pediu.
            return FilaTreinoResponse(
                itens=[],
                feitas_hoje=0,
                total_hoje=0,
                vencidos_total=0,
                sessao_id=sessao_id,
            )

    try:
        consulta = (
            client.table("fila_treino_espacado")
            .select(
                "id, origem, repeticoes, total_revisoes, progresso_trecho, "
                "lances_criticos(numero_lance, numero_lance_fim, tipo_evento, "
                "fen_antes_lance, "
                "partidas(cor_jogada, data_partida, plataforma)), "
                "exercicios_taticos(fen, categoria_hexagono), "
                "exercicios_posicionais(fen, categoria_hexagono, segundos_restantes)"
            )
            .eq("user_id", user_id)
        )
        if ids_da_sessao is not None:
            # Dentro de uma sessão o critério não é "venceu hoje" e sim "ainda
            # não foi respondido": um card respondido agora é reagendado para
            # amanhã e sumiria da sessão no meio dela.
            consulta = consulta.in_("id", ids_da_sessao).eq("total_revisoes", 0)
        else:
            consulta = consulta.lte("proxima_revisao_data", hoje.isoformat())
        resp_pendentes = consulta.order("proxima_revisao_data").execute()
        resp_feitas = (
            client.table("fila_treino_espacado")
            .select("id")
            .eq("user_id", user_id)
            .gt("total_revisoes", 0)
            .gte("atualizado_em", inicio_do_dia.isoformat())
            .execute()
        )
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao consultar a fila de treino: {error}"
        ) from error

    itens: list[ItemFilaTreino] = []
    for row in resp_pendentes.data or []:
        origem = row.get("origem") or "lance_critico"

        if origem in ("exercicio_tatico", "exercicio_posicional"):
            chave = (
                "exercicios_taticos"
                if origem == "exercicio_tatico"
                else "exercicios_posicionais"
            )
            exercicio = row.get(chave) or {}
            if isinstance(exercicio, list):
                exercicio = exercicio[0] if exercicio else {}
            fen = exercicio.get("fen")
            if not fen:
                # Mesmo cuidado defensivo do branch de lance próprio: uma
                # inconsistência pontual não pode quebrar a fila inteira.
                continue
            itens.append(
                ItemFilaTreino(
                    fila_id=row["id"],
                    fen=fen,
                    origem=origem,
                    categoria=exercicio.get("categoria_hexagono"),
                    # O relógio vem ANTES de responder porque nesses cards ele
                    # É o exercício: a pressão de tempo é o que está sendo
                    # treinado (D-55). A procedência da partida, essa sim, só
                    # aparece depois - ver ResponderTreinoResponse.
                    segundos_sugeridos=exercicio.get("segundos_restantes"),
                    repeticoes=row.get("repeticoes") or 0,
                    total_revisoes=row.get("total_revisoes") or 0,
                )
            )
            continue

        lance = row.get("lances_criticos") or {}
        if isinstance(lance, list):
            lance = lance[0] if lance else {}
        partida = lance.get("partidas") or {}
        if isinstance(partida, list):
            partida = partida[0] if partida else {}
        fen = lance.get("fen_antes_lance")
        if not fen:
            # Defensivo: a população já filtra por fen_antes_lance preenchido,
            # mas um reprocessamento entre a população e esta consulta poderia
            # deixar a linha temporariamente inconsistente.
            continue

        tipo_evento = str(lance.get("tipo_evento") or "PICO").upper()
        trecho: TrechoEmAndamento | None = None
        if tipo_evento == "EROSAO":
            # Num card de trecho o que a tela mostra é onde o jogador PAROU, e
            # essa posição não está guardada em lugar nenhum: ela é recalculada
            # pelo replay dos SAN já jogados. É só python-chess, sem motor e
            # sem consulta a mais - o custo de manter a única fonte da posição
            # do lado do servidor.
            progresso = normalizar_progresso(
                row.get("progresso_trecho"),
                fen,
                total_lances_do_trecho(
                    lance.get("numero_lance"), lance.get("numero_lance_fim")
                ),
            )
            try:
                fen = reconstruir_tabuleiro(fen, progresso["lances"]).fen()
            except ProgressoCorrompidoError:
                # Histórico ilegível: o card volta a aparecer do começo da
                # janela, que é o pior caso aceitável (refazer o trecho
                # inteiro), em vez de sumir da fila.
                progresso = progresso_inicial(fen, progresso["total_lances"])
            trecho = TrechoEmAndamento(
                total_lances=progresso["total_lances"],
                lances_feitos=len(progresso["win_depois"]),
                historico=progresso["lances"],
            )

        itens.append(
            ItemFilaTreino(
                fila_id=row["id"],
                fen=fen,
                origem=origem,
                tipo_evento=tipo_evento,
                numero_lance=lance.get("numero_lance") or 0,
                numero_lance_fim=lance.get("numero_lance_fim"),
                trecho=trecho,
                cor_jogada=partida.get("cor_jogada"),
                data_partida=partida.get("data_partida"),
                plataforma=partida.get("plataforma"),
                repeticoes=row.get("repeticoes") or 0,
                total_revisoes=row.get("total_revisoes") or 0,
            )
        )

    vencidos_total = len(itens)
    if ids_da_sessao is not None:
        # Dentro de uma sessão os dois contadores são DELA, não do dia: somar
        # os pendentes da sessão com tudo o que foi feito hoje produzia um
        # "6 nesta sessão" que não era o tamanho de sessão nenhuma.
        total_hoje = len(ids_da_sessao)
        feitas_hoje = total_hoje - vencidos_total
    else:
        feitas_hoje = len(resp_feitas.data or [])
        total_hoje = vencidos_total + feitas_hoje

    # O teto corta o que a tela MOSTRA, nunca o que o SM-2 agendou: os cards
    # cortados continuam vencidos e aparecem assim que estes forem respondidos.
    # `vencidos_total` preserva a verdade sobre o tamanho do atraso (D-56).
    if TREINO_TETO_FILA > 0:
        itens = itens[:TREINO_TETO_FILA]
    return FilaTreinoResponse(
        itens=itens,
        feitas_hoje=feitas_hoje,
        total_hoje=total_hoje,
        vencidos_total=vencidos_total,
        sessao_id=sessao_id,
    )


def _limite_de_tempo_do_card(origem: str, posicional: dict[str, Any]) -> int | None:
    """Segundos que o card concede, ou None quando ele não é cronometrado.

    Só exercício posicional tem limite, e só quando o import guardou o relógio
    - o que ele faz apenas na categoria GESTAO_DE_TEMPO (ver D-55).
    """

    if origem != "exercicio_posicional":
        return None
    limite = posicional.get("segundos_restantes")
    return int(limite) if isinstance(limite, (int, float)) else None


def _referencia_da_partida(posicional: dict[str, Any]) -> str | None:
    """"GM Moranda, Wojciech × CM Klepek, Witold — Granada Open 2026 (2026)".

    Montada com o que existir: broadcast costuma vir sem data ("????.??.??") e
    às vezes sem um dos nomes. Devolve None quando não há nada a creditar, e aí
    a tela simplesmente não mostra o bloco.
    """

    if not posicional:
        return None
    brancas = (posicional.get("brancas") or "").strip()
    pretas = (posicional.get("pretas") or "").strip()
    jogadores = " × ".join(parte for parte in (brancas, pretas) if parte)
    evento = (posicional.get("evento") or "").strip()
    data_partida = (str(posicional.get("data_partida") or "")).strip()
    ano = data_partida[:4] if len(data_partida) >= 4 else ""

    partes = [parte for parte in (jogadores, evento) if parte]
    if not partes:
        return None
    referencia = " — ".join(partes)
    return f"{referencia} ({ano})" if ano and ano not in referencia else referencia


@app.post("/treino/{fila_id}/responder", response_model=ResponderTreinoResponse)
def responder_treino(
    fila_id: int,
    payload: ResponderTreinoRequest,
    user_id: str = Depends(verificar_limite_treino_responder),
) -> ResponderTreinoResponse:
    """Avalia a resposta de um card via Stockfish e reagenda via SM-2 (D-48).

    Sem chamada ao Gemini: classificar_qualidade_lance (threshold sobre
    queda_win_percent) já basta pra derivar a nota do SM-2, e manter o Gemini
    fora do caminho quente é o que permite muitas repetições por dia sem
    custo nem latência extra (decisão de escopo do D-48). Limite diário
    (auditoria pós-D-49) bem mais alto que as rotas caras — só pra conter
    abuso/loop contra o `engine_lock` global (R3), não pra frear o uso normal.
    """
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    try:
        resp_fila = (
            client.table("fila_treino_espacado")
            .select(
                "id, lance_id, origem, intervalo_dias, fator_facilidade, repeticoes, "
                "total_revisoes, livro_citado, capitulo_citado, pagina_citada, "
                "lances_criticos(fen_antes_lance, tipo_evento), "
                "exercicios_taticos(fen), "
                "exercicios_posicionais(fen, brancas, pretas, evento, data_partida, "
                "jogo_url, segundos_restantes)"
            )
            .eq("id", fila_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao consultar o card de treino: {error}"
        ) from error

    linhas_fila = resp_fila.data or []
    if not linhas_fila:
        # 404, nunca 403 (mesmo padrão IDOR-safe de D-29/D-30): não revela se
        # o card existe e pertence a outra conta.
        raise HTTPException(status_code=404, detail="Card de treino não encontrado.")
    fila_row = linhas_fila[0]
    origem = fila_row.get("origem") or "lance_critico"

    posicional: dict[str, Any] = {}
    if origem == "exercicio_posicional":
        posicional = fila_row.get("exercicios_posicionais") or {}
        if isinstance(posicional, list):
            posicional = posicional[0] if posicional else {}
        fen = posicional.get("fen")
    elif origem == "exercicio_tatico":
        exercicio = fila_row.get("exercicios_taticos") or {}
        if isinstance(exercicio, list):
            exercicio = exercicio[0] if exercicio else {}
        fen = exercicio.get("fen")
    else:
        lance_critico = fila_row.get("lances_criticos") or {}
        if isinstance(lance_critico, list):
            lance_critico = lance_critico[0] if lance_critico else {}
        if str(lance_critico.get("tipo_evento") or "PICO").upper() == "EROSAO":
            # D-66: card de erosão não se resolve num lance. Responder "o
            # lance certo" aqui produziria um veredito sobre uma decisão que
            # não é a que o evento mede — a janela inteira é o exercício.
            raise HTTPException(
                status_code=400,
                detail=(
                    "Este card é um trecho a refazer, não um lance único. "
                    "Use POST /treino/{fila_id}/trecho."
                ),
            )
        fen = lance_critico.get("fen_antes_lance")
    if not fen:
        raise HTTPException(
            status_code=500, detail="Card de treino sem posição registrada."
        )

    try:
        board = chess.Board(fen)
        resolvido = resolver_lance_usuario(board, payload.lance)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        avaliacao = avaliar_lance_avulso(
            _state["engine"], board, resolvido.move, _state.get("engine_lock")
        )
    except EngineIndisponivelError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao avaliar o lance: {error}"
        ) from error

    settings = _state["settings"]
    qualidade_lance = classificar_qualidade_lance(
        avaliacao.queda_win_percent, settings.limiar_lance_bom, settings.limiar_lance_ruim
    )

    diagnostico: dict[str, Any] = {}
    if origem == "lance_critico":
        try:
            resp_diagnostico = (
                client.table("diagnosticos")
                .select("raiz_conceitual_violada, tags_falha")
                .eq("lance_id", fila_row["lance_id"])
                .execute()
            )
            diagnostico_rows = resp_diagnostico.data or []
        except Exception:
            # O diagnóstico é só um complemento explicativo aqui - se a consulta
            # falhar, a avaliação do lance (o que importa de verdade) já está
            # pronta; melhor devolver sem a causa raiz do que falhar a revisão
            # inteira.
            diagnostico_rows = []
        diagnostico = diagnostico_rows[0] if diagnostico_rows else {}
    # Exercício de catálogo (D-49) não tem diagnosticos associado - raiz e
    # tags ficam vazias de propósito, a explicação já vem do Stockfish.

    hoje = _hoje_america_sao_paulo()
    nota = nota_sm2_da_qualidade_lance(qualidade_lance)

    # D-55: num card de gestão de tempo, decidir fora do prazo é a falha que o
    # exercício mede. Sem isto o cronômetro seria enfeite - o SM-2 agendaria
    # como se o tempo não existisse. A nota é rebaixada para a de uma resposta
    # "difícil" (nunca elevada): o fator de facilidade cai e aperta todos os
    # intervalos seguintes. A próxima data em si não muda, porque o SM-2 a
    # calcula com o fator anterior. `qualidade_lance` continua intacto, porque
    # o lance em si pode ter sido ótimo - são duas verdades diferentes.
    limite_segundos = _limite_de_tempo_do_card(origem, posicional)
    fora_do_tempo = (
        limite_segundos is not None
        and payload.segundos_gastos is not None
        and payload.segundos_gastos > limite_segundos
    )
    if fora_do_tempo:
        nota = min(nota, nota_sm2_da_qualidade_lance("SUBOTIMO"))

    agendamento = atualizar_agendamento(
        intervalo_dias=fila_row.get("intervalo_dias") or 0,
        fator_facilidade=fila_row.get("fator_facilidade") or 2.5,
        repeticoes=fila_row.get("repeticoes") or 0,
        qualidade=nota,
        hoje=hoje,
    )

    try:
        client.table("fila_treino_espacado").update(
            {
                "intervalo_dias": agendamento.intervalo_dias,
                "fator_facilidade": agendamento.fator_facilidade,
                "repeticoes": agendamento.repeticoes,
                "total_revisoes": (fila_row.get("total_revisoes") or 0) + 1,
                "ultima_qualidade": nota,
                "proxima_revisao_data": agendamento.proxima_revisao_data.isoformat(),
                "atualizado_em": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", fila_id).execute()
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao reagendar o card de treino: {error}"
        ) from error

    return ResponderTreinoResponse(
        qualidade_lance=qualidade_lance,
        lance_interpretado=resolvido.lance_interpretado,
        melhor_lance=avaliacao.melhor_lance,
        queda_win_percent=avaliacao.queda_win_percent,
        raiz_conceitual_violada=diagnostico.get("raiz_conceitual_violada"),
        tags_falha=diagnostico.get("tags_falha") or [],
        livro_citado=fila_row.get("livro_citado"),
        capitulo_citado=fila_row.get("capitulo_citado"),
        pagina_citada=fila_row.get("pagina_citada"),
        partida_referencia=_referencia_da_partida(posicional),
        partida_url=posicional.get("jogo_url"),
        fora_do_tempo=fora_do_tempo,
        proxima_revisao_data=agendamento.proxima_revisao_data.isoformat(),
        repeticoes=agendamento.repeticoes,
    )


def _diagnostico_do_lance(client: Any, lance_id: str) -> dict[str, Any]:
    """Causa raiz e tags do lance, para a revelação que vem depois da tentativa.

    Falha de consulta devolve vazio de propósito (mesmo critério de
    `responder_treino`): a explicação é complemento, e perdê-la é melhor do que
    derrubar uma revisão já avaliada.
    """

    try:
        resposta = (
            client.table("diagnosticos")
            .select("raiz_conceitual_violada, tags_falha")
            .eq("lance_id", lance_id)
            .execute()
        )
        linhas = resposta.data or []
    except Exception:
        return {}
    return linhas[0] if linhas else {}


@app.post("/treino/{fila_id}/trecho", response_model=TrechoResponse)
def jogar_trecho(
    fila_id: int,
    payload: TrechoRequest,
    user_id: str = Depends(verificar_limite_treino_trecho),
) -> TrechoResponse:
    """Avança um lance do "Refazer o trecho" de um card de EROSAO (D-66).

    Um PICO pergunta "qual era o lance?"; uma EROSAO não tem essa pergunta - é
    uma janela de 8 lances em que a posição escorregou sem nenhum erro isolado
    grande o bastante para virar pico. O formato que cabe nela é jogar a janela
    de novo, contra um motor limitado ao rating do adversário real, e medir no
    fim a MESMA coisa que detectou o evento: a queda líquida de win% entre o
    começo e o fim do trecho.

    Cada chamada vale um lance do jogador mais a resposta do motor. A posição
    corrente nunca vem do cliente: é reconstruída aqui pelo replay dos SAN já
    gravados. O veredito, a curva e o reagendamento do SM-2 só saem na chamada
    que fecha a janela; até lá o jogador não vê quanto está perdendo, porque
    ver isso lance a lance é exatamente o que não acontece numa partida.
    """
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    try:
        resp_fila = (
            client.table("fila_treino_espacado")
            .select(
                "id, lance_id, origem, progresso_trecho, intervalo_dias, "
                "fator_facilidade, repeticoes, total_revisoes, livro_citado, "
                "capitulo_citado, pagina_citada, "
                "lances_criticos(numero_lance, numero_lance_fim, tipo_evento, "
                "fen_antes_lance, queda_win_percent, "
                "partidas(rating_oponente, rating_proprio))"
            )
            .eq("id", fila_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao consultar o card de treino: {error}"
        ) from error

    linhas_fila = resp_fila.data or []
    if not linhas_fila:
        # 404, nunca 403 (padrão IDOR-safe de D-29/D-30).
        raise HTTPException(status_code=404, detail="Card de treino não encontrado.")
    fila_row = linhas_fila[0]

    lance_critico = fila_row.get("lances_criticos") or {}
    if isinstance(lance_critico, list):
        lance_critico = lance_critico[0] if lance_critico else {}
    if str(lance_critico.get("tipo_evento") or "PICO").upper() != "EROSAO":
        raise HTTPException(
            status_code=400,
            detail=(
                "Este card é um lance único, não um trecho. "
                "Use POST /treino/{fila_id}/responder."
            ),
        )

    fen_inicial = lance_critico.get("fen_antes_lance")
    if not fen_inicial:
        raise HTTPException(
            status_code=500, detail="Card de treino sem posição registrada."
        )

    partida = lance_critico.get("partidas") or {}
    if isinstance(partida, list):
        partida = partida[0] if partida else {}

    total_lances = total_lances_do_trecho(
        lance_critico.get("numero_lance"), lance_critico.get("numero_lance_fim")
    )
    progresso = normalizar_progresso(
        fila_row.get("progresso_trecho"), fen_inicial, total_lances
    )

    try:
        passo = jogar_passo_do_trecho(
            _state["engine"],
            _state.get("engine_lock"),
            progresso,
            payload.lance,
            elo_do_oponente(
                partida.get("rating_oponente"), partida.get("rating_proprio")
            ),
        )
    except EngineIndisponivelError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ProgressoCorrompidoError:
        # Estado ilegível não é culpa de quem respondeu: zera o trecho e pede
        # pra recomeçar, em vez de devolver um 400 acusando o lance.
        try:
            client.table("fila_treino_espacado").update(
                {"progresso_trecho": None}
            ).eq("id", fila_id).execute()
        except Exception:
            pass
        raise HTTPException(
            status_code=409,
            detail=(
                "O progresso deste trecho ficou inconsistente e foi reiniciado. "
                "Recarregue a fila e comece o trecho de novo."
            ),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao avaliar o trecho: {error}"
        ) from error

    lances_feitos = len(passo.progresso["win_depois"])
    resposta = TrechoResponse(
        lance_interpretado=passo.lance_interpretado,
        lance_oponente=passo.lance_oponente,
        fen=passo.fen,
        lances_feitos=lances_feitos,
        total_lances=total_lances,
        historico=passo.progresso["lances"],
        concluido=passo.concluido,
        fim_de_partida=passo.fim_por_fim_de_jogo,
    )

    if not passo.concluido:
        try:
            client.table("fila_treino_espacado").update(
                {
                    "progresso_trecho": passo.progresso,
                    "atualizado_em": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", fila_id).execute()
        except Exception as error:
            raise HTTPException(
                status_code=500, detail=f"Falha ao salvar o trecho: {error}"
            ) from error
        return resposta

    # Fechou a janela: agora sim o veredito, medido pelo mesmo instrumento que
    # criou o evento.
    _, limiar_erosao = load_erosao_settings()
    queda_liquida = queda_liquida_do_trecho(passo.progresso)
    # `queda_win_percent` é numeric no Postgres e chega ora como número, ora
    # como string. Sem ela o card não perde o veredito: `classificar_trecho`
    # ainda tem o limiar absoluto, que é o critério principal.
    try:
        queda_original: float | None = round(
            float(lance_critico["queda_win_percent"]), 2
        )
    except (KeyError, TypeError, ValueError):
        queda_original = None
    qualidade = classificar_trecho(queda_liquida, queda_original, limiar_erosao)

    hoje = _hoje_america_sao_paulo()
    agendamento = atualizar_agendamento(
        intervalo_dias=fila_row.get("intervalo_dias") or 0,
        fator_facilidade=fila_row.get("fator_facilidade") or 2.5,
        repeticoes=fila_row.get("repeticoes") or 0,
        qualidade=nota_sm2_da_qualidade_lance(qualidade),
        hoje=hoje,
    )

    try:
        client.table("fila_treino_espacado").update(
            {
                "intervalo_dias": agendamento.intervalo_dias,
                "fator_facilidade": agendamento.fator_facilidade,
                "repeticoes": agendamento.repeticoes,
                "total_revisoes": (fila_row.get("total_revisoes") or 0) + 1,
                "ultima_qualidade": nota_sm2_da_qualidade_lance(qualidade),
                "proxima_revisao_data": agendamento.proxima_revisao_data.isoformat(),
                # O trecho é apagado ao fechar: na próxima repetição o card
                # começa da posição original de novo. Guardar a linha jogada
                # faria a revisão seguinte virar leitura do próprio gabarito.
                "progresso_trecho": None,
                "atualizado_em": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", fila_id).execute()
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao reagendar o card de treino: {error}"
        ) from error

    diagnostico = _diagnostico_do_lance(client, fila_row["lance_id"])
    resposta.qualidade_lance = qualidade
    resposta.queda_liquida = queda_liquida
    resposta.queda_original = queda_original
    resposta.resumo = resumo_do_veredito(qualidade, queda_liquida, queda_original)
    resposta.curva = [
        LanceDaCurvaResponse(
            numero=item.numero,
            lance=item.lance,
            win_antes=item.win_antes,
            win_depois=item.win_depois,
            queda=item.queda,
        )
        for item in curva_do_trecho(passo.progresso)
    ]
    resposta.raiz_conceitual_violada = diagnostico.get("raiz_conceitual_violada")
    resposta.tags_falha = diagnostico.get("tags_falha") or []
    resposta.livro_citado = fila_row.get("livro_citado")
    resposta.capitulo_citado = fila_row.get("capitulo_citado")
    resposta.pagina_citada = fila_row.get("pagina_citada")
    resposta.proxima_revisao_data = agendamento.proxima_revisao_data.isoformat()
    resposta.repeticoes = agendamento.repeticoes
    return resposta


@app.get("/treino/foco/disponibilidade", response_model=DisponibilidadeFocoResponse)
def disponibilidade_foco_treino(
    user_id: str = Depends(verificar_sessao),
) -> DisponibilidadeFocoResponse:
    """Contagem de exercícios de catálogo por categoria do Hexágono (D-53).

    Catálogo é global (sem `user_id`, mesmo padrão de `indice_conceitual`), então
    a contagem é a mesma para todo mundo — a sessão aqui só protege o acesso.

    Declarada ANTES de `POST /treino/foco/{categoria}` por clareza de leitura;
    não há conflito de rota porque os métodos HTTP são diferentes.

    Uma contagem `exact` por categoria, e não um select de todas as linhas:
    o PostgREST corta a resposta em 1000 linhas por padrão, e com 1200
    exercícios no catálogo essa versão anterior devolvia 300/300/120/280 para
    quatro categorias que tinham 300 cada — errado em silêncio, sem erro
    nenhum, e cada exercício novo importado piorava a distorção. Só apareceu
    ao chamar o endpoint contra o banco real (D-54).
    """
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    # Começa em 0 para as 6: uma categoria ausente no banco precisa aparecer
    # como 0 explícito, não sumir do mapa e virar `undefined` no frontend.
    por_categoria = {categoria: 0 for categoria in HEXAGON_CATEGORIES}
    for categoria in por_categoria:
        for tabela, _coluna_fk, _origem in CATALOGOS_DE_EXERCICIO:
            try:
                resp = (
                    client.table(tabela)
                    .select("id", count="exact")
                    .eq("categoria_hexagono", categoria)
                    .limit(1)
                    .execute()
                )
            except Exception as error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Falha ao consultar o catálogo de exercícios: {error}",
                ) from error
            por_categoria[categoria] += resp.count or 0

    return DisponibilidadeFocoResponse(por_categoria=por_categoria)


# Os dois catálogos que alimentam o treino focado, e como cada um se liga à
# fila. D-49 trouxe o primeiro (puzzles do Lichess, sempre táticos); D-55
# trouxe o segundo (posições NÃO táticas de partidas OTB reais), que é o que
# finalmente dá material a ESTRATEGIA e GESTAO_DE_TEMPO.
CATALOGOS_DE_EXERCICIO: tuple[tuple[str, str, str], ...] = (
    # (tabela, coluna de FK na fila, valor de `origem`)
    ("exercicios_taticos", "exercicio_id", "exercicio_tatico"),
    ("exercicios_posicionais", "posicional_id", "exercicio_posicional"),
)


def _selecionar_exercicios_para_fila(
    client: Any, user_id: str, categoria: str, quantidade: int
) -> tuple[list[dict[str, Any]], int]:
    """Sorteia exercícios dos catálogos que o usuário ainda não tem na fila.

    Devolve (linhas prontas para insert, total de exercícios da categoria nos
    catálogos). O segundo valor existe para o chamador distinguir os dois zeros
    de significado oposto (D-52): catálogo vazio vs. usuário já tem todos.

    Extraído do endpoint de foco no D-54 para a sessão de treino usar
    exatamente o mesmo caminho - uma sessão é um "Focar" maior e com começo,
    meio e fim, não um mecanismo paralelo. O D-55 fez o sorteio olhar os dois
    catálogos de uma vez, num único `random.sample` sobre a lista combinada:
    numa categoria com material dos dois tipos, o lote sai naturalmente
    misturado em vez de esgotar um antes de tocar no outro.
    """

    candidatos: list[tuple[str, str]] = []
    total_no_catalogo = 0

    for tabela, coluna_fk, origem in CATALOGOS_DE_EXERCICIO:
        try:
            resp_ja_na_fila = (
                client.table("fila_treino_espacado")
                .select(coluna_fk)
                .eq("user_id", user_id)
                .eq("origem", origem)
                .execute()
            )
            ja_na_fila = {
                row[coluna_fk] for row in resp_ja_na_fila.data or [] if row.get(coluna_fk)
            }

            resp_candidatos = (
                client.table(tabela)
                .select("id")
                .eq("categoria_hexagono", categoria)
                .execute()
            )
        except Exception as error:
            raise HTTPException(
                status_code=500, detail=f"Falha ao buscar exercícios da categoria: {error}"
            ) from error

        linhas_catalogo = resp_candidatos.data or []
        total_no_catalogo += len(linhas_catalogo)
        candidatos.extend(
            (coluna_fk, row["id"]) for row in linhas_catalogo if row["id"] not in ja_na_fila
        )

    if not candidatos:
        return [], total_no_catalogo

    escolhidos = random.sample(candidatos, k=min(quantidade, len(candidatos)))

    # Mesma citação pra todos os exercícios desta categoria neste lote - um
    # único resolver_citacao (buscar_conceitos, sem custo de LLM), reaproveitado
    # de popular_fila_treino_espacado.py (D-48).
    citacao = resolver_citacao(client, categoria)
    hoje = _hoje_america_sao_paulo()
    origem_por_coluna = {coluna: origem for _, coluna, origem in CATALOGOS_DE_EXERCICIO}
    linhas = [
        {
            "user_id": user_id,
            coluna_fk: exercicio_id,
            "origem": origem_por_coluna[coluna_fk],
            "proxima_revisao_data": hoje.isoformat(),
            "livro_citado": citacao.get("livro") if citacao else None,
            "capitulo_citado": citacao.get("capitulo") if citacao else None,
            "pagina_citada": citacao.get("pagina_aprox") if citacao else None,
        }
        for coluna_fk, exercicio_id in escolhidos
    ]
    return linhas, total_no_catalogo


def _inserir_na_fila(client: Any, linhas: list[dict[str, Any]]) -> list[int]:
    """Insere as linhas na fila e devolve os ids criados.

    Um upsert por catálogo: cada um tem a sua unique (user_id, exercicio_id) ou
    (user_id, posicional_id), e `on_conflict` só aceita uma.

    `ignore_duplicates`: um duplo clique antes do botão desabilitar vira no-op,
    não um 500 por violar a unique.
    """

    ids: list[int] = []
    for _, coluna_fk, _origem in CATALOGOS_DE_EXERCICIO:
        do_catalogo = [linha for linha in linhas if coluna_fk in linha]
        if not do_catalogo:
            continue
        try:
            resp = (
                client.table("fila_treino_espacado")
                .upsert(
                    do_catalogo,
                    on_conflict=f"user_id,{coluna_fk}",
                    ignore_duplicates=True,
                )
                .execute()
            )
        except Exception as error:
            raise HTTPException(
                status_code=500, detail=f"Falha ao adicionar exercícios à fila: {error}"
            ) from error
        ids.extend(
            row["id"] for row in (resp.data or []) if isinstance(row.get("id"), int)
        )
    return ids


@app.post("/treino/foco/{categoria}", response_model=FocoTreinoResponse)
def focar_categoria_treino(
    categoria: str,
    user_id: str = Depends(verificar_sessao),
) -> FocoTreinoResponse:
    """Insere exercícios do catálogo tático (D-49) na fila de hoje, focados
    numa categoria fraca do Hexágono - a "opção de treino focado" pedida
    quando o usuário ainda não tem lances críticos próprios suficientes
    naquela categoria. Usa a mesma fila/motor SM-2 do D-48.
    """
    if categoria not in HEXAGON_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Categoria inválida: {categoria}")

    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    linhas, total_no_catalogo = _selecionar_exercicios_para_fila(
        client, user_id, categoria, TREINO_FOCO_QTD_EXERCICIOS
    )
    if not linhas:
        return FocoTreinoResponse(
            adicionados=0,
            motivo="ja_na_fila" if total_no_catalogo else "sem_catalogo",
        )

    _inserir_na_fila(client, linhas)
    return FocoTreinoResponse(adicionados=len(linhas))


# ---------------------------------------------------------------------------
# Sessão de treino focado (D-54) - execução do que o Agente 3 prescreve
# ---------------------------------------------------------------------------


def _categoria_do_gargalo(diagnostico_gargalo: str | None) -> str | None:
    """Extrai a categoria do formato "CATEGORIA: título" que
    `agente3_prescritor.salvar_sessao` grava em `diagnostico_gargalo`.

    Versão tolerante de `medir_eficacia.categoria_do_diagnostico`, que levanta
    ValueError: aqui um formato inesperado não pode derrubar a tela da sessão,
    só desligar o bloco de prática. Derivar em vez de gravar uma coluna nova
    faz as sessões antigas funcionarem sem backfill (ver sessoes_treino_execucao.sql).
    """

    categoria, separador, _ = (diagnostico_gargalo or "").partition(":")
    categoria = categoria.strip().upper()
    if not separador or categoria not in HEXAGON_CATEGORIES:
        return None
    return categoria


def _modulos_da_sessao(modulos: Any) -> list[dict[str, Any]]:
    """Normaliza o jsonb `modulos`, que é o model_dump de SprintTreino
    ({titulo, duracao_total_min, modulos: [...]}). Aceitar também uma lista
    crua espelha o que o frontend já tolerava e evita quebrar linhas gravadas
    por versões diferentes do Agente 3."""

    if isinstance(modulos, list):
        return [modulo for modulo in modulos if isinstance(modulo, dict)]
    if isinstance(modulos, dict):
        internos = modulos.get("modulos")
        if isinstance(internos, list):
            return [modulo for modulo in internos if isinstance(modulo, dict)]
    return []


def _titulo_da_sessao(row: dict[str, Any]) -> str:
    """Título da sprint; cai no `diagnostico_gargalo` inteiro se o jsonb não
    tiver um (é ele que o dashboard já mostrava antes do D-54)."""

    modulos = row.get("modulos")
    if isinstance(modulos, dict) and isinstance(modulos.get("titulo"), str):
        titulo = modulos["titulo"].strip()
        if titulo:
            return titulo
    return str(row.get("diagnostico_gargalo") or "Sessão de treino")


def _buscar_sessao(client: Any, sessao_id: str, user_id: str) -> dict[str, Any]:
    """Carrega a sessão do próprio usuário ou levanta 404.

    404 e nunca 403 (mesmo padrão IDOR-safe de D-29/D-30): não revela que a
    sessão existe e pertence a outra conta.
    """

    try:
        resp = (
            client.table("sessoes_treino")
            .select(
                "id, diagnostico_gargalo, modulos, data_prescrita, data_iniciada, "
                "data_concluida, progresso"
            )
            .eq("id", sessao_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao consultar a sessão de treino: {error}"
        ) from error

    linhas = resp.data or []
    if not linhas:
        raise HTTPException(status_code=404, detail="Sessão de treino não encontrada.")
    return linhas[0]


def _contar_pratica_feita(client: Any, user_id: str, fila_ids: list[int]) -> int:
    """Quantos exercícios do bloco de prática já foram respondidos.

    Contado em tempo de leitura a partir de `total_revisoes`, em vez de
    duplicado no `progresso`: quem responde é POST /treino/{id}/responder, que
    não sabe (nem deveria saber) que aquele card pertence a uma sessão.
    """

    if not fila_ids:
        return 0
    try:
        resp = (
            client.table("fila_treino_espacado")
            .select("id, total_revisoes")
            .in_("id", fila_ids)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        # Degradação silenciosa: sem a contagem a sessão ainda abre e os blocos
        # de estudo continuam utilizáveis - melhor que 500 na tela inteira.
        return 0
    return sum(1 for row in resp.data or [] if (row.get("total_revisoes") or 0) > 0)


def _montar_execucao(
    client: Any, row: dict[str, Any], user_id: str
) -> ExecucaoSessaoResponse:
    """Monta o estado da sessão e a CONCLUI quando todos os blocos terminaram.

    A conclusão automática mora aqui, num GET, de propósito: o último bloco a
    fechar costuma ser o de prática, e quem o fecha é POST /treino/{id}/
    responder, que nada sabe de sessões. Descobrir no próximo carregamento é o
    que faz a sessão terminar sozinha - e é essa `data_concluida` que
    `medir_eficacia.py` espera para medir o impacto do treino (antes do D-54
    ela dependia de um botão manual, e por isso nunca foi preenchida).
    """

    progresso = row.get("progresso")
    if not isinstance(progresso, dict):
        progresso = {}
    concluidos = {
        indice
        for indice in progresso.get("blocos_concluidos") or []
        if isinstance(indice, int)
    }
    fila_ids = [item for item in progresso.get("fila_ids") or [] if isinstance(item, int)]

    modulos = _modulos_da_sessao(row.get("modulos"))
    blocos: list[BlocoSessaoResponse] = [
        BlocoSessaoResponse(
            indice=indice,
            tipo="estudo",
            nome=str(modulo.get("nome") or f"Módulo {indice + 1}"),
            conteudo=modulo.get("conteudo"),
            duracao_min=modulo.get("duracao_min"),
            livro=modulo.get("livro"),
            capitulo=modulo.get("capitulo"),
            pagina_aprox=modulo.get("pagina_aprox"),
            concluido=indice in concluidos,
        )
        for indice, modulo in enumerate(modulos)
    ]

    categoria = _categoria_do_gargalo(row.get("diagnostico_gargalo"))
    iniciada = row.get("data_iniciada")
    if categoria:
        rotulo = ROTULOS_CATEGORIA.get(categoria, categoria)
        feitos = _contar_pratica_feita(client, user_id, fila_ids) if iniciada else 0
        total = len(fila_ids)
        if not iniciada:
            # Antes de iniciar ainda não existe lote sorteado: dizer "nenhum
            # exercício" aqui seria falso (o catálogo tem material, a sessão é
            # que não foi aberta).
            nome_pratica = f"Prática: exercícios de {rotulo}"
        elif total == 0:
            nome_pratica = f"Prática: sem exercícios de catálogo em {rotulo}"
        else:
            nome_pratica = (
                f"Prática: {total} "
                f"{'exercício' if total == 1 else 'exercícios'} de {rotulo}"
            )
        blocos.append(
            BlocoSessaoResponse(
                indice=len(modulos),
                tipo="pratica",
                nome=nome_pratica,
                # Sem material de catálogo o bloco nasce concluído em vez de
                # travar a sessão para sempre - a honestidade fica no texto da
                # tela, não num bloqueio (ver P-15). Mas só depois de iniciada:
                # uma sessão fechada não tem bloco nenhum já cumprido.
                concluido=bool(iniciada) and (total == 0 or feitos >= total),
                categoria=categoria,
                exercicios_feitos=feitos,
                exercicios_total=total,
            )
        )

    duracao = sum(bloco.duracao_min or 0 for bloco in blocos)
    data_concluida = row.get("data_concluida")

    tudo_feito = bool(blocos) and all(bloco.concluido for bloco in blocos)
    if tudo_feito and iniciada and not data_concluida:
        data_concluida = datetime.now(timezone.utc).isoformat()
        try:
            client.table("sessoes_treino").update(
                {"data_concluida": data_concluida}
            ).eq("id", row["id"]).eq("user_id", user_id).execute()
        except Exception:
            # Não falha a leitura: a tela mostra a sessão completa e a próxima
            # abertura tenta gravar de novo.
            data_concluida = row.get("data_concluida")

    return ExecucaoSessaoResponse(
        sessao_id=str(row["id"]),
        titulo=_titulo_da_sessao(row),
        categoria_foco=categoria,
        data_prescrita=str(row.get("data_prescrita") or ""),
        data_iniciada=str(iniciada) if iniciada else None,
        data_concluida=str(data_concluida) if data_concluida else None,
        duracao_total_min=duracao,
        blocos=blocos,
        concluida=bool(data_concluida),
    )


@app.get("/sessoes/{sessao_id}/execucao", response_model=ExecucaoSessaoResponse)
def obter_execucao_sessao(
    sessao_id: str, user_id: str = Depends(verificar_sessao)
) -> ExecucaoSessaoResponse:
    """Estado atual de uma sessão de treino focado (D-54)."""

    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    return _montar_execucao(client, _buscar_sessao(client, sessao_id, user_id), user_id)


@app.post("/sessoes/{sessao_id}/iniciar", response_model=ExecucaoSessaoResponse)
def iniciar_sessao_treino(
    sessao_id: str, user_id: str = Depends(verificar_sessao)
) -> ExecucaoSessaoResponse:
    """Abre a sessão e monta o bloco de prática com exercícios reais (D-54).

    Idempotente: reabrir uma sessão já iniciada devolve o estado atual sem
    enfileirar mais nada. Sem isso, cada visita à tela empilharia mais uma
    dúzia de exercícios na fila do dia.
    """

    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    row = _buscar_sessao(client, sessao_id, user_id)
    if row.get("data_iniciada"):
        return _montar_execucao(client, row, user_id)

    progresso = row.get("progresso") if isinstance(row.get("progresso"), dict) else {}
    fila_ids: list[int] = []

    categoria = _categoria_do_gargalo(row.get("diagnostico_gargalo"))
    if categoria:
        linhas, _ = _selecionar_exercicios_para_fila(
            client, user_id, categoria, SESSAO_QTD_EXERCICIOS
        )
        if linhas:
            fila_ids = _inserir_na_fila(client, linhas)

    iniciada = datetime.now(timezone.utc).isoformat()
    novo_progresso = {**progresso, "fila_ids": fila_ids}
    novo_progresso.setdefault("blocos_concluidos", [])
    try:
        client.table("sessoes_treino").update(
            {"data_iniciada": iniciada, "progresso": novo_progresso}
        ).eq("id", sessao_id).eq("user_id", user_id).execute()
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao iniciar a sessão de treino: {error}"
        ) from error

    row = {**row, "data_iniciada": iniciada, "progresso": novo_progresso}
    return _montar_execucao(client, row, user_id)


@app.post(
    "/sessoes/{sessao_id}/blocos/{indice}/concluir",
    response_model=ExecucaoSessaoResponse,
)
def concluir_bloco_sessao(
    sessao_id: str, indice: int, user_id: str = Depends(verificar_sessao)
) -> ExecucaoSessaoResponse:
    """Marca um bloco de estudo como lido (D-54).

    Só blocos de estudo: o de prática fecha sozinho quando os exercícios são
    respondidos, e deixá-lo marcável à mão devolveria à sessão exatamente o
    "eu acho que terminei" que o D-54 veio remover.
    """

    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    row = _buscar_sessao(client, sessao_id, user_id)
    modulos = _modulos_da_sessao(row.get("modulos"))
    if indice < 0 or indice >= len(modulos):
        raise HTTPException(
            status_code=400, detail="Este bloco não existe ou não é de estudo."
        )

    progresso = row.get("progresso") if isinstance(row.get("progresso"), dict) else {}
    concluidos = sorted(
        {
            valor
            for valor in (progresso.get("blocos_concluidos") or [])
            if isinstance(valor, int)
        }
        | {indice}
    )
    novo_progresso = {**progresso, "blocos_concluidos": concluidos}

    try:
        client.table("sessoes_treino").update({"progresso": novo_progresso}).eq(
            "id", sessao_id
        ).eq("user_id", user_id).execute()
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao salvar o progresso da sessão: {error}"
        ) from error

    return _montar_execucao(client, {**row, "progresso": novo_progresso}, user_id)


@app.post("/explicar-posicao", response_model=ExplicarPosicaoResponse)
def explicar_posicao_endpoint(
    payload: ExplicarPosicaoRequest,
    user_id: str = Depends(verificar_limite_explicar_posicao),
) -> ExplicarPosicaoResponse:
    """Analisa uma posição (FEN ou PGN) e explica didaticamente o porquê de ser vencedora/perdida."""
    try:
        resultado = explicar_posicao(
            _state["engine"],
            _state["gemini_client"],
            _state["settings"],
            _state["logger"],
            payload.posicao,
            lado=payload.lado,
            engine_lock=_state.get("engine_lock"),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except EngineIndisponivelError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao processar explicação da posição: {error}",
        ) from error

    # Persistência é um efeito colateral, não o contrato principal do endpoint:
    # se salvar falhar, o usuário ainda recebe a explicação que pediu (só sem
    # id, então o frontend não marca este resultado como "ativo" no histórico).
    try:
        resultado["id"] = salvar_explicacao_posicao(
            _state["supabase_client"],
            resultado,
            user_id=user_id,
        )
    except Exception as error:
        logger = _state.get("logger")
        if logger:
            logger.warning("Falha ao salvar explicação de posição; seguindo sem persistir. %s", error)
        resultado["id"] = None

    return ExplicarPosicaoResponse(**resultado)


@app.get("/explicacoes-posicao/recentes", response_model=list[ExplicacaoPosicaoRecenteItem])
def listar_explicacoes_recentes(
    limite: int = 20, user_id: str = Depends(verificar_sessao)
) -> list[ExplicacaoPosicaoRecenteItem]:
    """Retorna o histórico de explicações de posição já geradas (explicacoes_posicao).

    Filtrado pelo dono da sessão (D-18); ver `listar_revisoes_avulsas_recentes`.
    """
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    try:
        resp = (
            client.table("explicacoes_posicao")
            .select("id, fen, lado_analisado, resultado, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(min(limite, 50))
            .execute()
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao consultar histórico de explicações: {error}",
        ) from error

    return [ExplicacaoPosicaoRecenteItem(**row) for row in resp.data or []]


@app.post(
    "/reconhecer-posicao",
    response_model=ReconhecerPosicaoResponse,
)
def reconhecer_posicao_endpoint(
    imagem: UploadFile = File(...),
    user_id: str = Depends(verificar_limite_reconhecer_posicao),
) -> ReconhecerPosicaoResponse:
    """Reconhece uma posição de xadrez a partir de uma foto de diagrama (Gemini visão)."""

    content_type = (imagem.content_type or "").lower()
    if content_type not in RECONHECER_POSICAO_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Envie um arquivo de imagem em JPG ou PNG.",
        )

    dados = imagem.file.read()
    if not dados:
        raise HTTPException(status_code=400, detail="Arquivo de imagem vazio.")
    if len(dados) > RECONHECER_POSICAO_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Imagem excede o tamanho máximo permitido de "
                f"{RECONHECER_POSICAO_MAX_BYTES // (1024 * 1024)}MB."
            ),
        )

    try:
        imagem_part = types.Part.from_bytes(data=dados, mime_type=content_type)
        response = _state["gemini_client"].models.generate_content(
            model=RECONHECER_POSICAO_MODEL,
            contents=[RECONHECER_POSICAO_PROMPT, imagem_part],
        )
        fen_bruto = response.text or ""
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao consultar o Gemini: {error}"
        ) from error

    fen = _limpar_fen_bruto(fen_bruto)
    try:
        chess.Board(fen)
    except Exception:
        raise HTTPException(
            status_code=422, detail=RECONHECER_POSICAO_ERRO_FEN_INVALIDO
        )

    return ReconhecerPosicaoResponse(fen=fen)


def _executar_analise_pgn_background(partida_id: str) -> None:
    """Executa o pipeline completo (Stockfish -> Diagnóstico -> Resumo) em segundo plano."""
    client = _state.get("supabase_client")
    logger = _state.get("logger")
    try:
        gemini_client = _state.get("gemini_client")
        analysis_settings = load_analysis_settings()
        linter_settings = load_linter_settings()
        engine_lock = _state.get("engine_lock")

        executar_pipeline_partida(
            client=client,
            partida_id=partida_id,
            gemini_client=gemini_client,
            analysis_settings=analysis_settings,
            linter_settings=linter_settings,
            logger=logger,
            engine_lock=engine_lock,
        )
    except Exception as error:
        if logger:
            logger.error(
                "Falha na tarefa em segundo plano para partida %s: %s",
                partida_id,
                error,
            )
        if client:
            try:
                update_status(client, partida_id, "falhou")
            except Exception:
                pass


@app.post(
    "/analisar-pgn",
    status_code=202,
    response_model=AnalisarPgnResponse,
)
def analisar_pgn_endpoint(
    payload: AnalisarPgnRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verificar_limite_analisar_pgn),
) -> AnalisarPgnResponse:
    """Recebe um PGN, insere a partida e agenda a análise completa em segundo plano.

    Retorna 202 imediatamente com partida_id e external_id.
    Se a cor for nula e não puder ser inferida pelos headers do PGN, retorna 422.
    """
    pgn_text = payload.pgn.strip() if payload.pgn else ""
    if not pgn_text:
        raise HTTPException(status_code=400, detail="PGN não fornecido.")

    try:
        game = parse_pgn(pgn_text)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    client = _state["supabase_client"]
    try:
        usernames = (
            resolver_usernames_do_perfil(client, user_id) if payload.cor is None else None
        )
        cor = resolver_cor(game, payload.cor, usernames=usernames)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    external_id = gerar_external_id(pgn_text)
    try:
        partida_id = inserir_partida(
            client, pgn_text, game, cor, user_id=user_id
        )
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao registrar partida: {error}"
        ) from error

    background_tasks.add_task(_executar_analise_pgn_background, partida_id)

    return AnalisarPgnResponse(partida_id=partida_id, external_id=external_id)


def _anexar_fen_aos_pontos_criticos(
    client: Any, partida_id: str, resumo: dict[str, Any]
) -> None:
    """Anexa `fen` a cada ponto crítico do resumo, casando por `numero_lance`.

    A posição mora em `lances_criticos.fen_antes_lance` (D-27), não no JSON
    de `resumo_partida` — fazer a junção aqui, na leitura, faz a miniatura
    aparecer também nas partidas analisadas antes desta mudança, sem
    reprocessar nada. Falha silenciosa de propósito: o resumo é o conteúdo,
    a miniatura é enfeite; se a consulta cair, a tela renderiza sem ela.
    """
    pontos = resumo.get("pontos_criticos")
    if not isinstance(pontos, list) or not pontos:
        return

    try:
        resp = (
            client.table("lances_criticos")
            .select("numero_lance, fen_antes_lance")
            .eq("partida_id", partida_id)
            .execute()
        )
    except Exception:
        return

    fen_por_lance = {
        row["numero_lance"]: row["fen_antes_lance"]
        for row in resp.data or []
        if row.get("numero_lance") is not None and row.get("fen_antes_lance")
    }
    if not fen_por_lance:
        return

    for ponto in pontos:
        if isinstance(ponto, dict) and not ponto.get("fen"):
            fen = fen_por_lance.get(ponto.get("numero_lance"))
            if fen:
                ponto["fen"] = fen


@app.get(
    "/partidas/{partida_id}/resumo",
    response_model=ResumoPartidaResponse,
)
def obter_resumo_partida_endpoint(
    partida_id: str, user_id: str = Depends(verificar_sessao)
) -> ResumoPartidaResponse:
    """Retorna o status atual de processamento e a narrativa da partida se disponível.

    D-29: `.eq("user_id", user_id)` filtra a busca pelo dono da sessão — sem
    isso, qualquer sessão válida lia o resumo de qualquer partida de
    qualquer usuário, só por adivinhar/enumerar o UUID. Partida de outro
    dono responde 404 (igual a não existir), nunca 403 — não revela que a
    partida existe.
    """
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    try:
        resp_partida = (
            client.table("partidas")
            .select("id, external_id, status_processamento")
            .eq("id", partida_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao consultar partida: {error}"
        ) from error

    if not resp_partida.data:
        raise HTTPException(status_code=404, detail="Partida não encontrada.")

    row_partida = resp_partida.data[0]
    status_proc = row_partida.get("status_processamento", "pendente")
    external_id = row_partida.get("external_id")

    resumo_dados: dict[str, Any] | None = None
    if status_proc == "concluido":
        try:
            resp_resumo = (
                client.table("resumo_partida")
                .select("narrativa, pontos_criticos, momento_chave_estrategico")
                .eq("partida_id", partida_id)
                .execute()
            )
            if resp_resumo.data:
                resumo_dados = resp_resumo.data[0]
                _anexar_fen_aos_pontos_criticos(client, partida_id, resumo_dados)
        except Exception:
            pass

    return ResumoPartidaResponse(
        partida_id=partida_id,
        external_id=external_id,
        status=status_proc,
        resumo=resumo_dados,
    )


@app.get("/partidas/recentes", response_model=list[PartidaRecenteItem])
def listar_partidas_recentes(
    limite: int = 20, user_id: str = Depends(verificar_sessao)
) -> list[PartidaRecenteItem]:
    """Retorna o histórico de partidas analisadas manualmente.

    Filtrado pelo dono da sessão (D-18); ver `listar_revisoes_avulsas_recentes`.
    """
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    try:
        resp = (
            client.table("partidas")
            .select(
                "id, external_id, status_processamento, cor_jogada, resultado, "
                "eco_abertura, data_partida, created_at, pgn"
            )
            .eq("plataforma", "MANUAL")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(min(limite, 50))
            .execute()
        )
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao consultar histórico de partidas: {error}"
        ) from error

    itens: list[PartidaRecenteItem] = []
    for row in resp.data or []:
        itens.append(
            PartidaRecenteItem(
                partida_id=row["id"],
                external_id=row.get("external_id"),
                status=row.get("status_processamento", "pendente"),
                cor_jogada=row.get("cor_jogada"),
                resultado=row.get("resultado"),
                eco_abertura=row.get("eco_abertura"),
                data_partida=row.get("data_partida"),
                created_at=row.get("created_at"),
                jogadores=extrair_jogadores_pgn(row.get("pgn")),
                fen_final=extrair_fen_final_pgn(row.get("pgn")),
            )
        )
    return itens


@app.post(
    "/partidas/{partida_id}/reprocessar",
    status_code=202,
    response_model=AnalisarPgnResponse,
)
def reprocessar_partida_endpoint(
    partida_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verificar_limite_reprocessar),
) -> AnalisarPgnResponse:
    """Re-agenda a análise completa de uma partida já existente em segundo plano.

    D-29: `.eq("user_id", user_id)` filtra pelo dono da sessão — sem isso,
    qualquer sessão válida conseguia reagendar a partida de qualquer outro
    usuário só por adivinhar o UUID, consumindo Stockfish/Gemini em cima do
    dado alheio. Partida de outro dono responde 404, nunca 403 — não revela
    que existe. Limite diário (auditoria pós-D-49): dispara o mesmo pipeline
    caro de /analisar-pgn e tinha ficado de fora do D-32 por descuido.
    """
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    try:
        resp = (
            client.table("partidas")
            .select("id, external_id")
            .eq("id", partida_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao consultar partida: {error}"
        ) from error

    if not resp.data:
        raise HTTPException(status_code=404, detail="Partida não encontrada.")

    row = resp.data[0]
    external_id = row.get("external_id") or ""

    try:
        update_status(client, partida_id, "processando")
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao atualizar status da partida: {error}"
        ) from error

    background_tasks.add_task(_executar_analise_pgn_background, partida_id)

    return AnalisarPgnResponse(partida_id=partida_id, external_id=external_id)


# D-65: quantas partidas a importação sob demanda analisa por execução. É o
# número que governa o custo do onboarding: cada partida custa Stockfish (CPU) e
# uma chamada de Gemini por lance crítico encontrado. 10 partidas bastam para o
# Agente 2 achar um gargalo (ele exige 5 diagnósticos numa categoria) sem
# transformar um clique em dezenas de chamadas pagas.
IMPORTACAO_MAX_PARTIDAS = int(os.getenv("IMPORTACAO_MAX_PARTIDAS", "10"))


def _perfil_do_usuario(client: Any, user_id: str) -> dict[str, Any] | None:
    """Linha de `perfis_usuario` do dono da sessão, ou None se não cadastrou."""

    resposta = (
        client.table("perfis_usuario")
        .select("lichess_username, chesscom_username")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    linhas = resposta.data or []
    return linhas[0] if linhas else None


def _token_lichess_para_coleta(client: Any, user_id: str) -> str | None:
    """Token a usar na coleta do Lichess, na ordem certa de preferência.

    O do próprio usuário (OAuth, D-33) vem primeiro: é dele a conta, e num
    produto multiusuário cada importação deve correr sob a credencial de quem
    pediu. O `LICHESS_TOKEN` do ambiente é o reserva, e em produção ele
    simplesmente não existe — o Cloud Run só recebe as 4 variáveis do D-20.

    Sem nenhum dos dois não dá para coletar do Lichess: a API de partidas
    responde **404** sem `Authorization`, verificado em 17/09/2026.
    """

    try:
        token = obter_access_token_lichess(client, user_id)
    except Exception:
        token = None
    return token or os.getenv("LICHESS_TOKEN") or None


def _coletar_partidas_do_perfil(
    client: Any, user_id: str, perfil: dict[str, Any], logger: Any
) -> list[str]:
    """Coleta das plataformas cadastradas. Devolve as fontes que funcionaram.

    Cada plataforma é isolada: a queda de uma não pode impedir a outra de
    trazer partidas — mesmo princípio do `continue-on-error` do pipeline
    diário (D-61).
    """

    fontes: list[str] = []

    chesscom_username = (perfil.get("chesscom_username") or "").strip()
    if chesscom_username:
        try:
            settings_cc = carregar_settings_chesscom()
            coletar_chesscom_para_perfil(
                client, settings_cc, logger, user_id, chesscom_username
            )
            fontes.append("chesscom")
        except Exception as error:
            if logger:
                logger.error("Importação: falha na coleta do Chess.com: %s", error)

    lichess_username = (perfil.get("lichess_username") or "").strip()
    if lichess_username:
        token = _token_lichess_para_coleta(client, user_id)
        if not token:
            if logger:
                logger.warning(
                    "Importação: usuário %s tem Lichess cadastrado mas nenhum "
                    "token disponível; a API de partidas exige autenticação.",
                    user_id,
                )
        else:
            try:
                settings_li = SettingsLichess(
                    supabase_url="",
                    supabase_service_role_key="",
                    lichess_token=token,
                    limit=IMPORTACAO_MAX_PARTIDAS,
                )
                coletar_lichess_para_perfil(
                    client, settings_li, logger, user_id, lichess_username
                )
                fontes.append("lichess")
            except Exception as error:
                if logger:
                    logger.error("Importação: falha na coleta do Lichess: %s", error)

    return fontes


def _executar_importacao_background(user_id: str) -> None:
    """Coleta, analisa e recalcula o Hexágono de um usuário, sob demanda (D-65).

    É o pipeline diário inteiro, para uma pessoa só, disparado por ela. Sem
    isso o primeiro valor do produto depende de dois crons: a coleta das 6h e o
    Agente 2 de segunda — até **7 dias** entre cadastrar a conta e ver um
    diagnóstico.

    Duas economias deliberadas: no máximo `IMPORTACAO_MAX_PARTIDAS` partidas
    por execução, e **sem gerar resumo por partida** (a etapa mais cara em
    Gemini e a menos urgente — o pipeline diário a faz depois).
    """

    client = _state.get("supabase_client")
    logger = _state.get("logger")
    if not client:
        return

    try:
        perfil = _perfil_do_usuario(client, user_id)
        if not perfil:
            return

        _coletar_partidas_do_perfil(client, user_id, perfil, logger)

        # Só as pendentes DESTE usuário, e no máximo o teto: uma importação não
        # pode virar um varredor do backlog alheio nem da conta inteira.
        resposta = (
            client.table("partidas")
            .select("id")
            .eq("user_id", user_id)
            .eq("status_processamento", "pendente")
            .order("data_partida", desc=True)
            .limit(IMPORTACAO_MAX_PARTIDAS)
            .execute()
        )
        pendentes = [linha["id"] for linha in resposta.data or []]

        analysis_settings = load_analysis_settings()
        linter_settings = load_linter_settings()
        for partida_id in pendentes:
            try:
                executar_pipeline_partida(
                    client=client,
                    partida_id=partida_id,
                    gemini_client=_state.get("gemini_client"),
                    analysis_settings=analysis_settings,
                    linter_settings=linter_settings,
                    logger=logger,
                    engine_lock=_state.get("engine_lock"),
                    gerar_resumo=False,
                )
            except Exception as error:
                # `executar_pipeline_partida` já marcou a partida como
                # `falhou`; uma partida ruim não aborta a importação.
                if logger:
                    logger.error(
                        "Importação: falha ao analisar a partida %s: %s",
                        partida_id,
                        error,
                    )

        # O Hexágono é o que o usuário veio ver. Sem esta chamada ele teria as
        # partidas analisadas e continuaria olhando uma tela vazia até segunda.
        try:
            analisar_usuario_hexagono(
                client, _state.get("gemini_client"), logger, user_id
            )
        except Exception as error:
            if logger:
                logger.error("Importação: falha ao recalcular o Hexágono: %s", error)
    except Exception as error:
        if logger:
            logger.error("Importação: falha geral para o usuário %s: %s", user_id, error)


@app.post("/perfis/importar", status_code=202, response_model=ImportacaoResponse)
def importar_partidas_endpoint(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verificar_limite_importar),
) -> ImportacaoResponse:
    """Dispara a importação sob demanda das partidas de quem está logado (D-65).

    Responde 202 na hora e trabalha em `BackgroundTasks`, como `/analisar-pgn`:
    o trabalho leva minutos e segurar a resposta só produziria timeout.
    """

    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    perfil = _perfil_do_usuario(client, user_id)
    if not perfil:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cadastre seu usuário do Lichess ou do Chess.com no Perfil "
                "antes de importar."
            ),
        )

    fontes: list[str] = []
    detalhes: list[str] = []
    if (perfil.get("chesscom_username") or "").strip():
        fontes.append("chesscom")
    if (perfil.get("lichess_username") or "").strip():
        if _token_lichess_para_coleta(client, user_id):
            fontes.append("lichess")
        else:
            # Dito na resposta, não escondido no log: sem isso o usuário veria
            # só partidas do Chess.com chegando e não teria como saber por quê.
            detalhes.append(
                "A importação do Lichess exige conexão da conta — conecte no "
                "Perfil para incluir as partidas de lá."
            )

    if not fontes:
        raise HTTPException(
            status_code=400,
            detail=(
                detalhes[0]
                if detalhes
                else "Nenhuma plataforma cadastrada para importar."
            ),
        )

    background_tasks.add_task(_executar_importacao_background, user_id)

    return ImportacaoResponse(
        iniciada=True,
        fontes=fontes,
        detalhe=" ".join(detalhes)
        or "Importação iniciada. Isso leva alguns minutos.",
    )


@app.get("/perfis/importacao", response_model=StatusImportacaoResponse)
def status_importacao_endpoint(
    user_id: str = Depends(verificar_sessao),
) -> StatusImportacaoResponse:
    """Progresso da importação, para a tela acompanhar sem recarregar (D-65)."""

    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    def _contar(**filtros: str) -> int:
        consulta = (
            client.table("partidas").select("id", count="exact").eq("user_id", user_id)
        )
        for coluna, valor in filtros.items():
            consulta = consulta.eq(coluna, valor)
        return consulta.limit(1).execute().count or 0

    try:
        total = _contar()
        pendentes = _contar(status_processamento="pendente")
        processando = _contar(status_processamento="processando")
        concluidas = _contar(status_processamento="concluido")

        # `!inner` nos dois embeds transforma o embed em join de verdade, que é
        # o que permite filtrar pela coluna aninhada `partidas.user_id` (mesmo
        # cuidado do D-28 em `agente2_analista.fetch_diagnosticos`). Sem ele o
        # filtro só afetaria o conteúdo do embed, e a contagem viria global.
        diagnosticos = (
            client.table("diagnosticos")
            .select(
                "id, lances_criticos!inner(partidas!inner(user_id))", count="exact"
            )
            .eq("lances_criticos.partidas.user_id", user_id)
            .limit(1)
            .execute()
        ).count or 0

        hexagono = (
            client.table("analises_hexagono")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        ).count or 0
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao consultar a importação: {error}"
        ) from error

    em_andamento = pendentes > 0 or processando > 0
    return StatusImportacaoResponse(
        partidas=total,
        pendentes=pendentes,
        processando=processando,
        concluidas=concluidas,
        diagnosticos=diagnosticos,
        tem_hexagono=hexagono > 0,
        em_andamento=em_andamento,
        # "Pronto" é ter o que o usuário veio ver — o Hexágono —, não apenas
        # ter terminado de processar.
        pronto=hexagono > 0 and not em_andamento,
    )


@app.get("/partidas/composicao", response_model=ComposicaoCadenciaResponse)
def composicao_das_partidas(
    user_id: str = Depends(verificar_sessao),
) -> ComposicaoCadenciaResponse:
    """Quantas partidas analisadas há em cada cadência (D-57).

    Uma contagem `exact` por cadência, e não um select das linhas: é a mesma
    armadilha do teto de 1000 do PostgREST que o D-54 encontrou em
    `/treino/foco/disponibilidade`, e com 240 partidas hoje ela morderia assim
    que o acervo crescesse.
    """

    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    por_cadencia: dict[str, int] = {}
    for cadencia in CADENCIAS:
        try:
            resp = (
                client.table("partidas")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("cadencia", cadencia)
                .eq("status_processamento", "concluido")
                .limit(1)
                .execute()
            )
        except Exception as error:
            raise HTTPException(
                status_code=500, detail=f"Falha ao consultar as partidas: {error}"
            ) from error
        quantidade = resp.count or 0
        if quantidade:
            por_cadencia[cadencia] = quantidade

    total = sum(por_cadencia.values())
    if not total:
        return ComposicaoCadenciaResponse(por_cadencia={}, total=0)

    dominante = max(por_cadencia, key=lambda chave: por_cadencia[chave])
    return ComposicaoCadenciaResponse(
        por_cadencia=por_cadencia,
        total=total,
        dominante=dominante,
        percentual_dominante=round(100 * por_cadencia[dominante] / total, 1),
    )


@app.get("/insights/repertorio")
def insights_repertorio_endpoint(
    user_id: str = Depends(verificar_sessao),
) -> dict[str, Any]:
    """Agregações de repertório: taxa de vitória, precisão e padrão de erro por abertura.

    Cálculo puro sobre dado já persistido (sem Stockfish nem Gemini) — ver
    backend/agentes/insights_repertorio.py e D-12/D-13 em DECISOES.md.

    D-30: filtrado pelo dono da sessão — cada uma das 4 queries internas de
    `calcular_insights_repertorio` já recebe `user_id`, não só o endpoint.
    """
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    try:
        return calcular_insights_repertorio(client, user_id)
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao calcular insights de repertório: {error}"
        ) from error


@app.get("/insights/puzzles")
def insights_puzzles_endpoint(
    user_id: str = Depends(verificar_sessao),
) -> dict[str, Any]:
    """Agregações de puzzles e diagnóstico do Gap Tático (D-41).

    Compara a precisão por tema tático nos puzzles com as vulnerabilidades das
    partidas reais sob pressão de tempo (D-30: filtrado pelo dono da sessão).
    """
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    try:
        return calcular_insights_puzzles(client, user_id)
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao calcular insights de puzzles: {error}"
        ) from error


@app.get("/partidas/{partida_id}/teoria-abertura")
def teoria_abertura_endpoint(
    partida_id: str,
    user_id: str = Depends(verificar_sessao),
) -> dict[str, Any]:
    """Identifica o ponto exato de saída da teoria de abertura de mestres para uma partida (D-42)."""
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    resp = (
        client.table("partidas")
        .select("id, pgn, cor_jogada")
        .eq("id", partida_id)
        .eq("user_id", user_id)
        .execute()
    )
    linhas = resp.data or []
    if not linhas:
        raise HTTPException(status_code=404, detail="Partida não encontrada.")

    partida = linhas[0]
    pgn = partida.get("pgn")
    if not pgn:
        return {"sucesso": False, "disponivel": False, "motivo": "sem_pgn"}

    token = obter_access_token_lichess(client, user_id)
    return detectar_saida_teoria(
        pgn, token=token, cor_jogada=partida.get("cor_jogada")
    )


@app.get("/analise/syzygy")
def syzygy_endpoint(
    fen: str,
    lance: str | None = None,
    _user_id: str = Depends(verificar_sessao),
) -> dict[str, Any]:
    """Consulta a Syzygy Tablebase para posições de final com até 7 peças (D-42)."""
    if lance:
        return avaliar_lance_final_syzygy(fen, lance)
    resultado = consultar_syzygy(fen)
    if resultado is None:
        return {
            "elegivel_syzygy": False,
            "motivo": "Posição possui mais de 7 peças, é inválida ou motor indisponível.",
        }
    return {"elegivel_syzygy": True, "dados": resultado}


@app.post("/lichess/oauth/iniciar", response_model=IniciarOauthLichessResponse)
def iniciar_oauth_lichess(
    user_id: str = Depends(verificar_sessao),
) -> IniciarOauthLichessResponse:
    """Começa o fluxo OAuth do Lichess para a conta de quem está logado (D-33).

    Gera o par PKCE e um `state` aleatório, amarra os dois ao `user_id` da
    sessão em `lichess_oauth_pkce`, e devolve a URL de autorização do Lichess
    para o frontend redirecionar. O `code_verifier` nunca sai do servidor.
    """

    client = _state.get("supabase_client")
    if client is None:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    config = _state.get("lichess_oauth") or _resolver_config_lichess_oauth()
    code_verifier, code_challenge = _gerar_par_pkce()
    state = secrets.token_urlsafe(32)
    expira_em = datetime.now(timezone.utc) + timedelta(
        minutes=LICHESS_OAUTH_PKCE_TTL_MINUTOS
    )

    try:
        # Varre o lixo de fluxos abandonados (a pessoa abriu e desistiu) antes
        # de criar o novo: sem isso a tabela só cresce, já que o caminho feliz
        # é o único que apaga a própria linha.
        client.table("lichess_oauth_pkce").delete().lt(
            "expires_at", datetime.now(timezone.utc).isoformat()
        ).execute()
        client.table("lichess_oauth_pkce").insert(
            {
                "state": state,
                "user_id": user_id,
                "code_verifier": code_verifier,
                "expires_at": expira_em.isoformat(),
            }
        ).execute()
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao iniciar a conexão com o Lichess: {error}"
        ) from error

    parametros = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "scope": config["scopes"],
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
        "state": state,
    }
    return IniciarOauthLichessResponse(
        url_autorizacao=f"{LICHESS_OAUTH_AUTHORIZE_URL}?{urlencode(parametros)}",
        expira_em=expira_em.isoformat(),
    )


@app.get("/lichess/oauth/callback")
def callback_oauth_lichess(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Recebe o retorno do Lichess, troca o código pelo token e o guarda (D-33).

    **Esta rota não passa por `verificar_sessao` de propósito** e é a única
    exceção ao gate de D-25: quem chega aqui é o navegador da pessoa numa
    navegação de topo vinda do lichess.org, sem o header `Authorization` que
    o frontend anexa nas chamadas via fetch. A identidade não vem da sessão,
    vem do `state`: um valor aleatório de 256 bits, de uso único, que só
    existe porque `/lichess/oauth/iniciar` — essa sim protegida por sessão —
    o gravou amarrado a um `user_id`. Um `state` forjado não existe na tabela,
    e um `state` reusado já foi apagado: é o que fecha o CSRF.

    Erros terminam em redirect com um marcador, não em JSON: o destino é um
    navegador, não um cliente de API.
    """

    if error:
        return _redirecionar_para_frontend("erro=lichess_negado")
    if not code or not state:
        return _redirecionar_para_frontend("erro=lichess_resposta_invalida")

    client = _state.get("supabase_client")
    if client is None:
        return _redirecionar_para_frontend("erro=lichess_indisponivel")

    config = _state.get("lichess_oauth") or _resolver_config_lichess_oauth()

    try:
        # DELETE ... RETURNING: consome o state de forma atômica, então dois
        # callbacks concorrentes com o mesmo state não podem ambos prosseguir.
        consumido = (
            client.table("lichess_oauth_pkce").delete().eq("state", state).execute()
        )
    except Exception:
        return _redirecionar_para_frontend("erro=lichess_indisponivel")

    linhas = consumido.data or []
    if not linhas:
        return _redirecionar_para_frontend("erro=lichess_state_invalido")

    pendente = linhas[0]
    if datetime.fromisoformat(pendente["expires_at"]) <= datetime.now(timezone.utc):
        return _redirecionar_para_frontend("erro=lichess_state_expirado")

    try:
        resposta = requests.post(
            LICHESS_OAUTH_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": pendente["code_verifier"],
                "redirect_uri": config["redirect_uri"],
                "client_id": config["client_id"],
            },
            timeout=30,
        )
        resposta.raise_for_status()
        token = resposta.json()
    except Exception:
        logger = _state.get("logger")
        if logger:
            # Sem o corpo da resposta no log: ele pode conter o token em caso
            # de erro parcial, e log não é lugar de credencial.
            logger.warning("Falha ao trocar o código OAuth do Lichess por token.")
        return _redirecionar_para_frontend("erro=lichess_troca_falhou")

    access_token = token.get("access_token")
    if not access_token:
        return _redirecionar_para_frontend("erro=lichess_troca_falhou")

    expires_in = token.get("expires_in")
    expires_at = (
        (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()
        if expires_in
        else None
    )

    try:
        client.table("lichess_oauth_tokens").upsert(
            {
                "user_id": pendente["user_id"],
                "access_token": access_token,
                "refresh_token": token.get("refresh_token"),
                "expires_at": expires_at,
                "scopes": config["scopes"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="user_id",
        ).execute()
    except Exception:
        return _redirecionar_para_frontend("erro=lichess_gravacao_falhou")

    return _redirecionar_para_frontend("conectado=lichess")


@app.get("/lichess/oauth/status", response_model=LichessOauthStatusResponse)
def status_oauth_lichess(
    user_id: str = Depends(verificar_sessao),
) -> LichessOauthStatusResponse:
    """Informa se o usuário logado tem uma conexão OAuth ativa com o Lichess (D-35).

    Usa `obter_access_token_lichess` (com margem de expiração) para garantir
    que só devolve `conectado: true` se o token for válido e utilizável agora.
    O access_token nunca é devolvido ao frontend (D-33).
    """

    client = _state.get("supabase_client")
    if client is None:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    token = obter_access_token_lichess(client, user_id)
    if not token:
        return LichessOauthStatusResponse(conectado=False)

    try:
        resp = (
            client.table("lichess_oauth_tokens")
            .select("expires_at")
            .eq("user_id", user_id)
            .execute()
        )
        linhas = resp.data or []
        expires_at = linhas[0].get("expires_at") if linhas else None
    except Exception:
        expires_at = None

    return LichessOauthStatusResponse(conectado=True, expires_at=expires_at)


@app.post("/lichess/oauth/desconectar")
def desconectar_oauth_lichess(
    user_id: str = Depends(verificar_sessao),
) -> dict[str, bool]:
    """Remove o token OAuth do Lichess do usuário logado (D-35)."""

    client = _state.get("supabase_client")
    if client is None:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    try:
        client.table("lichess_oauth_tokens").delete().eq("user_id", user_id).execute()
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao desconectar conta do Lichess: {error}"
        ) from error

    return {"desconectado": True}


@app.get("/guia-passos")
def guia_passos() -> dict[str, list[dict[str, Any]]]:
    """Retorna só os títulos numerados dos passos do guia (conteúdo público).

    Serve o resumo leve exibido no frontend; lido do .md em runtime, então
    acompanha edições do guia sem mudança de código.
    """

    passos = carregar_passos_guia()
    return {
        "passos": [
            {"numero": passo["numero"], "titulo": passo["titulo"]}
            for passo in passos
        ]
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Endpoint de verificação de saúde da aplicação para balanceadores e CI/CD."""
    return {"status": "ok"}
