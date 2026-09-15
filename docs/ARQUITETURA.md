---
doc: ARQUITETURA.md
escopo: componentes, fluxo de dados, superfície de API, frontend, topologia de deploy
nao_contem: estado factual (ver ESTADO.md), comandos (ver OPERACAO.md), schema (ver BANCO.md)
verificado_em: 2026-09-15
---

# Arquitetura do Chess AI Pipeline

## 1. Duas metades independentes

O repositório contém dois sistemas que compartilham o mesmo banco e as mesmas
bibliotecas, mas rodam de formas diferentes:

- **Pipeline em lote** — scripts Python em `backend/`, sem servidor HTTP,
  executados por GitHub Actions ou na mão. Coletam partidas, rodam Stockfish,
  diagnosticam, agregam estatística e prescrevem treino.
- **Aplicação web** — FastAPI (`backend/api/api_server.py`) no Cloud Run +
  Angular (`frontend/`) na Vercel. Dá feedback sob demanda, com o usuário na
  frente da tela.

## 2. Fluxo de dados do pipeline em lote

```
tabela perfis_usuario (uma linha por usuário logado, D-28)
        ↓
Lichess API / Chess.com API
        ↓  backend/ingestao/coletar_partidas*.py         [1 rodada por perfil]
   tabela partidas (status_processamento = 'pendente', user_id do perfil)
        ↓  backend/analise_engine/analisar_partidas.py  [Stockfish]
   tabela lances_criticos (eventos PICO e EROSAO)
        ↓  backend/agentes/agente1_linter.py            [Gemini]
   tabela diagnosticos (tags_falha, causa raiz)
        ↓  backend/agentes/agente2_analista.py          [pandas + Gemini p/ narrar, 1x por usuário]
   tabela analises_hexagono (métricas agregadas + gargalo atual)
        ↓  backend/agentes/agente3_prescritor.py        [RAG pgvector + YouTube + Gemini, 1x por usuário]
   tabela sessoes_treino (sprint com módulos citando livro/capítulo/página)
        ↓  backend/agentes/medir_eficacia.py
   coluna sessoes_treino.eficacia_medida (fecha o loop adaptativo)
```

Desde D-28, o pipeline em lote é multi-tenant de ponta a ponta:
`coletar_partidas*.py` percorre `perfis_usuario` (uma rodada de coleta por
pessoa cadastrada, cada uma gravando no próprio `user_id`), e Agentes 2 e 3
recalculam hexágono e sprint separadamente para cada `user_id` com dado
próprio — sem isso, os dois agentes misturariam diagnósticos de pessoas
diferentes num único hexágono global. Agente 1 não precisou mudar: já
processa lance a lance, herdando o dono via `partida_id` sem precisar saber
"de quem" é cada um.

Enriquecimentos que entram lateralmente nesse fluxo:

- `backend/ingestao/enriquecer_partidas_lichess.py` → `metricas_lichess_partida`
  e `tempos_lance` (precisão geral e por fase — abertura/meio-jogo/final — e
  relógio, tudo calculado pelo próprio Lichess).
- `backend/agentes/normalizar_aberturas.py` → `partidas.abertura_normalizada`
  (agrupamento por família reconhecível; ver `BANCO.md` §4 e `DECISOES.md` D-12).
- `backend/ingestao/importar_anotacoes_lichess.py` → `anotacoes_pensamento`
  (comentários que o jogador escreveu em um Lichess Study).
- `backend/ingestao/importar_puzzle_activity.py` → `puzzle_atividade`.
- `backend/agentes/gerar_resumo_partida.py` → `resumo_partida` (narrativa da
  partida inteira + momento-chave estratégico).
- `backend/agentes/gerar_perguntas_pendentes.py` → `perguntas_pendentes`.

## 3. Os três agentes de LLM

| Agente | Arquivo | Entrada | Saída | Papel do LLM |
|---|---|---|---|---|
| 1 — Linter | `agente1_linter.py` | um lance crítico + linha do motor | `diagnosticos` | diagnostica a causa do erro em 16 tags fechadas |
| 2 — Analista | `agente2_analista.py` | diagnósticos de um usuário (loop por `user_id`, D-28) | `analises_hexagono` | só narra; a estatística é pandas puro |
| 3 — Prescritor | `agente3_prescritor.py` | gargalo + RAG de livros | `sessoes_treino` | monta a sprint citando teoria real |

O Agente 1 usa **prompts diferentes por `tipo_evento`**: um para `PICO` (erro
pontual em um lance) e `build_erosion_prompt` para `EROSAO` (perda gradual ao
longo de uma janela de lances). Misturar os dois inverte a perspectiva e faz o
modelo atribuir lances do jogador ao adversário — ver `D-3` em `DECISOES.md`.

## 4. RAG de livros de xadrez

Distinto do conhecimento de agente deste repositório. `backend/rag/processar_livro.py`
faz OCR quando necessário, quebra o PDF em chunks por capítulo, gera embeddings e
grava em `livros_chunks` (pgvector). A busca acontece via RPC
`match_livros_chunks` (`backend/db/match_livros_chunks.sql`), consumida pelo
Agente 3. A tabela `indice_conceitual` é um mapa **manual** de
conceito → livro → capítulo → página, populado por SQL depois de processar cada
livro.

## 5. Superfície da API

**Todo endpoint marcado com 🎫 exige `Authorization: Bearer <token da sessão
Supabase Auth>`** — é o único mecanismo de acesso da API desde D-25. Sem token,
ou com token inválido/expirado, a resposta é `401` antes de qualquer trabalho
caro (Stockfish, Gemini, banco), pela dependency `verificar_sessao`. Só
`/health` e `/guia-passos` ficam fora: um é liveness probe do Cloud Run, o
outro é conteúdo estático sem dado de usuário. A terceira e última exceção é
`/lichess/oauth/callback` (D-33), pelo motivo explicado na própria linha da
tabela — ela não pode exigir header porque é um redirect de navegador, e usa
um `state` de uso único no lugar.

`X-API-Key` **foi aposentada como porta de entrada** e não abre mais nada —
nem com a chave correta. `API_SECRET_KEYS` ainda é lida no startup e
`verificar_api_key` continua no arquivo, sem nenhuma rota usando: a limpeza
dessas duas está registrada como pendência em `ESTADO.md`, não foi feita.

As rotas marcadas com 👤 recebem o `user_id` real por injeção
(`user_id: str = Depends(verificar_sessao)`) e o usam como dono da escrita ou
filtro da leitura — sem fallback nenhum, porque quem chega lá tem sessão
garantida.

As rotas marcadas com ⏱️ passam por `limite_diario(rota)` (D-32): a chamada é
contada atomicamente em `uso_diario_usuario` (RPC `incrementar_uso_diario`,
dia calculado em `America/Sao_Paulo`) ANTES do corpo da rota, e responde `429`
se o limite do dia (configurável por variável de ambiente, ver OPERACAO.md)
já foi atingido — mesmo princípio de "falhar rápido" de 🎫, mas para custo
(Stockfish/Gemini) em vez de acesso. São as 4 rotas mais caras da API.

| Método e rota | Função |
|---|---|
| `GET /health` | health check do Cloud Run (público) |
| `GET /guia-passos` | títulos dos 8 passos da rubrica (público) |
| `POST /revisar-avulso` 🎫⏱️ | avalia lance único ou sequência a partir de FEN/PGN + texto do raciocínio |
| `POST /revisar-avulso/salvar` 🎫👤 | persiste um exercício revisado; devolve o `id` da linha criada |
| `GET /revisoes-avulsas/recentes` 🎫👤 | histórico do Laboratório, filtrado pelo dono da sessão (D-18) |
| `POST /explicar-posicao` 🎫👤⏱️ | avaliação objetiva + explicação didática de uma posição; persiste em `explicacoes_posicao` e devolve o `id` (falha de persistência não derruba a resposta — ver D-11) |
| `GET /explicacoes-posicao/recentes` 🎫👤 | histórico do Explicador, filtrado pelo dono; cada item embute a resposta completa, sem endpoint "buscar por id" |
| `GET /resolver-fen` 🎫 | resolve FEN ou PGN para o FEN final; parsing puro, sem Gemini nem Stockfish |
| `POST /reconhecer-posicao` 🎫⏱️ | recebe foto de diagrama (multipart) e devolve o FEN, via Gemini multimodal |
| `POST /analisar-pgn` 🎫👤⏱️ | dispara o pipeline completo de uma partida; responde `202` na hora e processa em `BackgroundTasks` |
| `GET /partidas/{id}/resumo` 🎫👤 | status do processamento + `resumo_partida` quando concluído; partida de outro dono responde 404 (D-29) |
| `GET /partidas/recentes` 🎫👤 | histórico para a tela do Analisador, filtrado pelo dono |
| `POST /partidas/{id}/reprocessar` 🎫👤 | reseta para `pendente` e reexecuta; partida de outro dono responde 404 (D-29) |
| `POST /lichess/oauth/iniciar` 🎫👤 | começa o OAuth do Lichess (D-33): gera o par PKCE + `state`, amarra os dois ao dono da sessão em `lichess_oauth_pkce` e devolve a URL de autorização; o `code_verifier` nunca sai do servidor |
| `GET /lichess/oauth/callback` | destino do redirect do lichess.org — **única rota de negócio sem 🎫, de propósito**: chega como navegação de topo do navegador, sem header `Authorization`. Quem autentica é o `state` de uso único gravado pela rota acima. Troca o código pelo token, grava em `lichess_oauth_tokens` e redireciona para `/perfil?conectado=lichess` (ou `?erro=…`), sem nunca pôr token, `code` ou `state` na URL |
| `GET /lichess/oauth/status` 🎫👤 | informa se o usuário tem token Lichess ativo e válido (D-35); não expõe o token ao frontend |
| `POST /lichess/oauth/desconectar` 🎫👤 | revoga localmente a conexão, removendo a linha de `lichess_oauth_tokens` (D-35) |
| `GET /insights/repertorio` 🎫👤 | agregações de repertório por abertura (taxa de vitória, precisão por fase, lance de PICO, categoria do hexágono) — cálculo puro em Python sobre dado já persistido, sem Stockfish nem Gemini; ver `backend/agentes/insights_repertorio.py` e D-13 em `DECISOES.md`. As 4 buscas internas filtram por dono desde D-30 (achado correlato de D-29) |
| `GET /insights/puzzles` 🎫👤 | compara a precisão por tema tático nos puzzles com as vulnerabilidades das partidas reais sob pressão de tempo — diagnóstico do "Gap Tático" (D-41); ver `backend/agentes/insights_puzzles.py`, filtrado pelo dono da sessão |
| `GET /partidas/{partida_id}/teoria-abertura` 🎫👤 | identifica o ponto exato em que a partida sai da teoria de abertura de mestres, via Lichess Opening Explorer (D-42); partida de outro dono responde 404 |
| `GET /analise/syzygy` 🎫 | consulta a Syzygy Tablebase para posições de final com até 7 peças, avaliando se um lance é o melhor plano teórico (D-42); `user_id` só protege acesso, não filtra dado — a posição vem por FEN |

Recursos caros (Stockfish, cliente Gemini, cliente Supabase, `engine_lock`) são
inicializados uma vez no startup e guardados em `_state`, um dict de módulo.

## 6. Frontend

Angular 21, standalone components, signals, Tailwind CSS 4, testes em Vitest.

| Rota | Componente | O que faz |
|---|---|---|
| `/` | `hexagono-radar` | radar das 6 categorias + narrativa + sessões de treino |
| `/laboratorio` | `laboratorio-raciocinio` | exercício avulso com feedback imediato |
| `/explicador` | `explicador-posicao` | explicação didática de uma posição |
| `/analisador` | `analisador-partida` | cola PGN, acompanha o progresso, lê o resumo |
| `/perfil` | `perfil-usuario` | cadastra a(s) conta(s) de Lichess/Chess.com de quem está logado (D-28) |
| `/login` | `login` | signUp/signInWithPassword do Supabase Auth (Fase B.1 — ver D-15 em `DECISOES.md`) |

`authGuard` está ligado nas 5 rotas do dashboard (todas acima, exceto
`/login`) desde D-23 — ver a nota mais abaixo sobre a Fase B.

Componentes de apoio: `tabuleiro-preview` (tabuleiro 8x8 em CSS Grid com SVGs do
conjunto cburnett), `narrativa-analise`, `perguntas-pendentes`, `sessoes-treino`,
`historico-analise` (lista de histórico genérica e reutilizável — ver D-11 em
`DECISOES.md`; as 3 telas interativas mapeiam seus próprios itens para o shape
`HistoricoAnaliseItem` e tratam `(itemClicado)` para restaurar o que só cada uma
sabe restaurar).

Cada uma das 3 telas interativas persiste o item ativo em `localStorage` para
sobreviver a um F5 (`chess_analisador_partida_ativa`, `chess_explicador_ativo`,
`chess_laboratorio_ativo`). `frontend/src/app/shared/data.ts` guarda o
formatador de data compartilhado por todas elas.

**Sistema de design — `frontend/src/styles.css` é a única fonte de verdade de
cor, sombra, raio e tipografia (D-47).** Um bloco `@theme` do Tailwind 4 define
os tokens (`ardosia-*` para superfície, `linha`/`linha-forte` para traço,
`marfim`/`bruma-*` para texto, `latao-*` para o acento da marca, mais
`sucesso`/`perigo`/`info`/`roxo` e as casas do tabuleiro), e o Tailwind gera os
utilitários a partir deles (`bg-ardosia-800`, `text-latao-500`, `border-linha`).
Um `@layer components` define o vocabulário que os templates usam: `.cartao`,
`.painel`, `.btn` + variantes, `.campo`, `.selo` + variantes, `.aviso`,
`.segmentado`, `.metrica`, `.estado-vazio`, `.esqueleto`, `.pulso`, `.prosa`,
`.nav-link`, `.titulo-pagina`.

Duas consequências práticas para quem for mexer aqui:

- **Nenhum template deve escrever hex.** A única exceção viva é a configuração
  do Chart.js em `hexagono-radar.component.ts`, que exige string literal de cor;
  os valores lá espelham os tokens e estão comentados como tal.
- **Helper de cor em TypeScript devolve nome de variante, não classe de cor** —
  `corBadgeStatus()` e companhia retornam `'selo-sucesso'`, `'selo-perigo'`, e a
  cor em si mora no CSS. Trocar a paleta é editar `styles.css` e nada mais.

O cabeçalho de navegação (`app.html`) só renderiza para quem tem sessão: sem
login a única rota alcançável é `/login` (authGuard, D-23), então mostrar os
links ali seria oferecer 5 caminhos que voltam para a mesma tela.

**Autenticação — um sistema só, desde D-25.** `AuthService`
(`services/auth.service.ts`) é o Supabase Auth, e é tudo que existe:
expõe `usuario` (signal), `autenticado` (computed) e `sessaoPronta`
(computed a partir de uma promise interna, usada pelo `authGuard` pra não
decidir antes de `getSession()` responder). Não existe "client Supabase
autenticado" separado do anônimo — é o mesmo `SupabaseService.client`, e
`AuthService` só chama `auth.signInWithPassword`/`signUp` nele; a partir daí
`hexagono-radar`, `narrativa-analise`, `sessoes-treino` e
`perguntas-pendentes` (os únicos 4 componentes que leem Supabase direto,
todos via `SupabaseService`) passam a carregar com a sessão automaticamente,
sem precisar de nenhuma mudança de código.

**Login passou a ser obrigatório pro dashboard (Fase B concluída — D-23).**
`authGuard` está ligado nas rotas do dashboard (`/`, `/laboratorio`,
`/explicador`, `/analisador`, e `/perfil` desde D-28) em `app.routes.ts`;
visitante sem sessão é redirecionado pra `/login`. As tabelas por trás dos 4
primeiros componentes acima não têm mais nenhuma
policy `to anon` — só `authenticated`, isolada por dono (`user_id =
auth.uid()`, direto ou via `exists` até `partidas`, ver D-19/D-22/D-23 em
`DECISOES.md`). Consequência aceita: os 4 amigos que só têm `X-API-Key` (D-7),
sem conta Supabase Auth, ficam sem acesso a nenhuma das 4 telas até migrarem —
ver P-11 em `ESTADO.md`.

**As chamadas ao FastAPI também passaram a usar a sessão, e só ela (D-25).**
`RevisaoAvulsaService.headersComSessao()` monta `Authorization: Bearer
<access_token>` e é usado em **todos** os métodos do serviço — não existe mais
`headersComChave()`, nem `AuthLocalService` (o arquivo foi removido junto com
a tela de "Chave de acesso" das 3 telas interativas). Um `401` da API agora
só pode significar sessão expirada no meio do uso, já que a rota em si já
exigiu login pelo guard; o serviço devolve `sessaoExpirada: true` e a tela
mostra a mensagem pra entrar de novo.

Convenções do frontend que não são óbvias:

- Assets ficam em `frontend/public/`, **não** em `src/assets/` — é o que o
  `angular.json` serve. Referencie sem prefixo (`pieces/cburnett/wK.svg`).
- O Angular colapsa espaço entre elementos no template. Para manter um espaço
  entre dois `<span>` irmãos, use a entidade `&ngsp;`.
- `frontend/src/app/shared/` guarda funções puras reaproveitáveis entre
  componentes (ex.: `lichess.ts`, que monta a URL do analisador do Lichess).

## 7. Topologia de deploy

- **Frontend**: Vercel, deploy automático a cada push na `main`.
  `https://chess-ai-pipeline.vercel.app`
- **Backend**: Cloud Run, serviço `laboratorio-xadrez`, região `us-east1`,
  projeto GCP `gen-lang-client-0828609060`.
  `https://laboratorio-xadrez-kltmum75rq-ue.a.run.app`
- **CI/CD do backend**: `.github/workflows/deploy-backend.yml`, disparado por push
  na `main` que toque `backend/**` ou `Dockerfile`. Roda os testes, autentica no
  GCP com a service account `github-deployer` (secret `GCP_SA_KEY`), builda com
  buildx e cache, publica no Artifact Registry, faz `gcloud run deploy` e valida
  com `curl /health`.
- **Banco**: Supabase Postgres + pgvector, projeto `pmzmershonrqzwbmhaco`.

Deploy manual de emergência:

```bash
gcloud run deploy laboratorio-xadrez --source . --region us-east1 \
  --allow-unauthenticated --max-instances=3 --env-vars-file=env.yaml
```
