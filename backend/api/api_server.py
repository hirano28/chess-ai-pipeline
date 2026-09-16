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
from backend.agentes.agente2_analista import HEXAGON_CATEGORIES  # noqa: E402
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
    load_settings as load_analysis_settings,
    update_status,
)
from backend.common.lichess_explorer import (  # noqa: E402
    detectar_saida_teoria,
)
from backend.common.lichess_oauth import (  # noqa: E402
    obter_access_token_lichess,
)
from backend.common.progress import log_and_print  # noqa: E402
from backend.common.spaced_repetition import (  # noqa: E402
    atualizar_agendamento,
    nota_sm2_da_qualidade_lance,
)
from backend.common.syzygy_tablebase import (  # noqa: E402
    avaliar_lance_final_syzygy,
    consultar_syzygy,
)
from backend.ingestao.common_ingestao import create_supabase_client  # noqa: E402

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
}
MENSAGEM_LIMITE_DIARIO = "Limite diário atingido, tente novamente amanhã."

# D-49: quantos exercícios do catálogo tático entram na fila de uma vez
# quando o usuário clica "Focar" numa categoria (mesmo padrão de
# configuração por env var de TREINO_NOVOS_POR_DIA, D-48).
TREINO_FOCO_QTD_EXERCICIOS = int(os.getenv("TREINO_FOCO_QTD_EXERCICIOS", "8"))

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
    numero_lance: int | None = None
    cor_jogada: str | None = None
    data_partida: str | None = None
    plataforma: str | None = None
    categoria: str | None = None
    repeticoes: int
    total_revisoes: int


class FilaTreinoResponse(BaseModel):
    """Fila de hoje + contadores para o indicador de progresso do frontend."""

    itens: list[ItemFilaTreino]
    feitas_hoje: int
    total_hoje: int


class ResponderTreinoRequest(BaseModel):
    """Payload da resposta a um card: só o lance (ver D-48 - sem raciocínio)."""

    lance: str


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
    proxima_revisao_data: str
    repeticoes: int


class FocoTreinoResponse(BaseModel):
    """Resposta de POST /treino/foco/{categoria} (D-49)."""

    adicionados: int


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
def obter_fila_treino(user_id: str = Depends(verificar_sessao)) -> FilaTreinoResponse:
    """Lista os cards de repetição espaçada vencidos hoje (D-48).

    Não revela tags_falha, causa raiz nem citação de livro - isso só aparece
    na resposta de POST /treino/{fila_id}/responder, depois de tentar o lance.
    """
    client = _state.get("supabase_client")
    if not client:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.")

    hoje = _hoje_america_sao_paulo()
    inicio_do_dia = datetime.combine(hoje, time.min, tzinfo=ZoneInfo("America/Sao_Paulo"))

    try:
        resp_pendentes = (
            client.table("fila_treino_espacado")
            .select(
                "id, origem, repeticoes, total_revisoes, "
                "lances_criticos(numero_lance, fen_antes_lance, "
                "partidas(cor_jogada, data_partida, plataforma)), "
                "exercicios_taticos(fen, categoria_hexagono)"
            )
            .eq("user_id", user_id)
            .lte("proxima_revisao_data", hoje.isoformat())
            .order("proxima_revisao_data")
            .execute()
        )
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

        if origem == "exercicio_tatico":
            exercicio = row.get("exercicios_taticos") or {}
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
        itens.append(
            ItemFilaTreino(
                fila_id=row["id"],
                fen=fen,
                origem=origem,
                numero_lance=lance.get("numero_lance") or 0,
                cor_jogada=partida.get("cor_jogada"),
                data_partida=partida.get("data_partida"),
                plataforma=partida.get("plataforma"),
                repeticoes=row.get("repeticoes") or 0,
                total_revisoes=row.get("total_revisoes") or 0,
            )
        )

    feitas_hoje = len(resp_feitas.data or [])
    return FilaTreinoResponse(
        itens=itens, feitas_hoje=feitas_hoje, total_hoje=len(itens) + feitas_hoje
    )


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
                "lances_criticos(fen_antes_lance), exercicios_taticos(fen)"
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

    if origem == "exercicio_tatico":
        exercicio = fila_row.get("exercicios_taticos") or {}
        if isinstance(exercicio, list):
            exercicio = exercicio[0] if exercicio else {}
        fen = exercicio.get("fen")
    else:
        lance_critico = fila_row.get("lances_criticos") or {}
        if isinstance(lance_critico, list):
            lance_critico = lance_critico[0] if lance_critico else {}
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
        proxima_revisao_data=agendamento.proxima_revisao_data.isoformat(),
        repeticoes=agendamento.repeticoes,
    )


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

    try:
        resp_ja_na_fila = (
            client.table("fila_treino_espacado")
            .select("exercicio_id")
            .eq("user_id", user_id)
            .eq("origem", "exercicio_tatico")
            .execute()
        )
        ja_na_fila = {
            row["exercicio_id"] for row in resp_ja_na_fila.data or [] if row.get("exercicio_id")
        }

        resp_candidatos = (
            client.table("exercicios_taticos")
            .select("id")
            .eq("categoria_hexagono", categoria)
            .execute()
        )
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao buscar exercícios da categoria: {error}"
        ) from error

    candidatos = [
        row["id"] for row in resp_candidatos.data or [] if row["id"] not in ja_na_fila
    ]
    if not candidatos:
        return FocoTreinoResponse(adicionados=0)

    escolhidos = random.sample(candidatos, k=min(TREINO_FOCO_QTD_EXERCICIOS, len(candidatos)))

    # Mesma citação pra todos os exercícios desta categoria neste lote - um
    # único resolver_citacao (buscar_conceitos, sem custo de LLM), reaproveitado
    # de popular_fila_treino_espacado.py (D-48).
    citacao = resolver_citacao(client, categoria)
    hoje = _hoje_america_sao_paulo()
    linhas = [
        {
            "user_id": user_id,
            "exercicio_id": exercicio_id,
            "origem": "exercicio_tatico",
            "proxima_revisao_data": hoje.isoformat(),
            "livro_citado": citacao.get("livro") if citacao else None,
            "capitulo_citado": citacao.get("capitulo") if citacao else None,
            "pagina_citada": citacao.get("pagina_aprox") if citacao else None,
        }
        for exercicio_id in escolhidos
    ]

    try:
        # ignore_duplicates: um duplo clique em "Focar" antes do botão
        # desabilitar vira no-op, não um 500 pela unique(user_id, exercicio_id).
        client.table("fila_treino_espacado").upsert(
            linhas, on_conflict="user_id,exercicio_id", ignore_duplicates=True
        ).execute()
    except Exception as error:
        raise HTTPException(
            status_code=500, detail=f"Falha ao adicionar exercícios à fila: {error}"
        ) from error

    return FocoTreinoResponse(adicionados=len(linhas))


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
