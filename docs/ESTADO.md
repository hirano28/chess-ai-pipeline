---
doc: ESTADO.md
escopo: ÚNICO lugar do repositório onde mora estado factual (contagens, status, pendências)
verificado_em: 2026-09-14
como_reverificar: rode as queries da seção 6 e os comandos da seção 1
aviso: número sem data de verificação em qualquer outro documento deve ser tratado como suspeito
---

# Estado verificado — 2026-09-14

Tudo nesta página foi conferido nesta data contra o banco real
(`pmzmershonrqzwbmhaco`), o código e os workflows. Ao mudar qualquer fato aqui,
atualize também a data no cabeçalho.

## 1. Testes e build

| Item | Valor verificado |
|---|---|
| Testes de backend | **426**, todos passando, em 24 módulos |
| Testes de frontend (Vitest) | **92**, todos passando, em 12 arquivos |
| `ng build` de produção | passa; avisa excesso de bundle (~794 kB), conhecido e aceito |

`.github/workflows/deploy-backend.yml` lista os 24 módulos de teste do backend
à mão (incluindo `backend.agentes.test_medir_eficacia`, `backend.common.test_lichess_oauth`,
`backend.ingestao.test_importar_puzzle_activity`, `backend.agentes.test_agente2_analista`,
`backend.common.test_notacao_pt`, `backend.analise_engine.test_backfill_fen_lances_criticos`,
`backend.ingestao.test_coletar_partidas`, `backend.ingestao.test_coletar_partidas_chesscom`
e `backend.ingestao.test_common_ingestao` — regra R8 cumprida). Continua sendo
uma lista mantida manualmente: todo módulo de teste novo precisa ser
adicionado lá também.

## 2. Volume de dados

As 6 tabelas raiz (`partidas`, `analises_hexagono`, `sessoes_treino`,
`explicacoes_posicao`, `puzzle_atividade`, `revisao_exercicio_avulso`) têm
`user_id NOT NULL` desde 11/09/2026, com as **900 linhas existentes
backfilladas** para o dono único atual (ver D-14 em `DECISOES.md` e a
pendência P-11 abaixo).

| Tabela | Linhas |
|---|---|
| `partidas` | 215 (02/07/2026 a 11/09/2026); as 215 já têm `abertura_normalizada` preenchida (ver D-12 em `DECISOES.md`). Uma 216ª foi ingerida em 13/09/2026 pela validação real de D-28, ainda sem `abertura_normalizada`/ECO processados — as distribuições abaixo não a incluem |
| `lances_criticos` | 510 — 492 `PICO`, 18 `EROSAO` |
| `diagnosticos` | 473 |
| `puzzle_atividade` | 660, em 41 dias distintos |
| `tempos_lance` | 2.863, cobrindo 40 partidas |
| `livros_chunks` | 370 |
| `indice_conceitual` | 67 |
| `anotacoes_pensamento` | 23, cobrindo 3 partidas |
| `revisoes_pensamento` | 23, todas em 1 único dia |
| `revisao_exercicio_avulso` | 11 |
| `explicacoes_posicao` | 7 (tabela nova, ver D-11 em `DECISOES.md`) |
| `metricas_lichess_partida` | 4, para 61 partidas do Lichess; nenhuma tem ainda `precisao_abertura`/`precisao_meiojogo`/`precisao_final` — colunas novas (ver `BANCO.md`), só preenchidas a partir de agora, sem reprocessamento retroativo das 4 já existentes |
| `analises_hexagono` | 3 |
| `sessoes_treino` | 3 |
| `resumo_partida` | 3 |

## 3. Composição do corpus — dado que muda a leitura de tudo

| Cadência (`TimeControl` do PGN) | Partidas analisadas |
|---|---|
| 180 s (blitz 3 min) | 87 |
| 300 s (blitz 5 min) | 47 |
| Lichess, sem header de TimeControl | 40 |
| 600 s (rapid 10 min) | 7 |

**74% do corpus analisado é blitz de 3 a 5 minutos**, e não existe coluna de
cadência em `partidas` — não dá nem para filtrar. Qualquer conclusão sobre "o
gargalo do jogador" está hoje misturada com o efeito do relógio. A tag mais
frequente é `calculo_tatico_deficiente` (29,8% de todas as tags), o que é
esperado a ~2 segundos por lance.

Sinal na direção oposta: nos puzzles, ~60% de acerto em puzzles de rating médio
~2000, contra rating de blitz ~1424. Escalas diferentes, não comparáveis
diretamente, mas sugerem que o padrão é conhecido e falha sob pressão de tempo.

Temas de puzzle mais fracos: `defensiveMove` 45,2%, `deflection` 48,5%,
`veryLong` 50,8%, `quietMove` 53,8% — todos sobre ameaça do adversário e lance
não forçado.

### Distribuição de `abertura_normalizada` (215/215 partidas, 11/09/2026)

| Abertura | Partidas |
|---|---|
| Francesa | 51 |
| Peão de Dama | 22 |
| Moderna | 17 |
| Sistema Londres | 17 |
| Siciliana | 17 |
| Italiana | 12 |
| Escandinava | 10 |
| Gambito da Dama | 7 |
| Caro-Kann | 7 |
| Gambito do Rei | 6 |
| (restante) | 49, em 26 famílias/nomes distintos, nenhum com mais de 4 partidas |

A Francesa domina sozinha quase 1 em cada 4 partidas do corpus. Ver
`DECISOES.md` D-12 para como cada plataforma resolve o nome cru antes de
agrupar.

### Francesa cruzada com resultado e erro (`GET /insights/repertorio`, 11/09/2026)

Agora cruzada de verdade via `GET /insights/repertorio` (D-13):

| cor_jogada | partidas | % vitória |
|---|---|---|
| PRETAS | 44 | 52,27% |
| BRANCAS | 7 | 57,14% |

`precisao_media_abertura/meiojogo/final` vieram `null` nas duas linhas — as 3
colunas novas de `metricas_lichess_partida` (ver acima) ainda não têm nenhuma
linha preenchida, então não há precisão por fase pra cruzar ainda.

Lance onde ocorrem eventos `PICO` na Francesa: **111 eventos**, lance médio
**24,02**, mediana **21** — os erros pontuais de cálculo tendem a aparecer
já perto do fim da abertura/início do meio-jogo, não na abertura propriamente.

Distribuição de categoria do hexágono nos diagnósticos da Francesa (294 no
total): **TATICA 168 (57%)**, CALCULO 71 (24%), ESTRATEGIA 25 (9%), FINAIS 13
(4%), GESTAO_DE_TEMPO 8 (3%), ESTRUTURA_DE_PEOES 9 (3%). Confirma o padrão já
visto na seção 3 do corpus inteiro — `calculo_tatico_deficiente` domina — mas
agora isolado só na abertura de maior volume, e mais concentrado ainda
(57% vs. 29,8% da tag isolada no corpus geral, embora as bases não sejam
diretamente comparáveis: aqui é % de categoria TATICA, lá era % de uma tag
específica).

## 4. Pendências

### P-1 — Chaves de API expostas, rotação nunca feita 🔴

`GEMINI_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY` e as `API_SECRET_KEYS` antigas
foram compartilhadas em texto puro durante o desenvolvimento. **Prioridade nº 1
em qualquer trabalho de segurança.**

### P-2 — 6 tabelas sem RLS, expostas pela chave anon ✅ RESOLVIDA em 13/09/2026

Eram `metricas_lichess_partida`, `tempos_lance`, `anotacoes_pensamento`,
`perguntas_pendentes`, `revisoes_pensamento`, `puzzle_atividade` — todas com
`rls_ligado = false`, isto é, acesso irrestrito para qualquer portador da chave
`anon` (que é pública, vai no bundle do frontend). Tratada como incidente: o
vazamento foi confirmado chegando ao navegador, com uma conta de teste em
produção recebendo HTTP 200 com o texto íntegro de uma pergunta do dono.

**Resolução (D-22 em `DECISOES.md`).**
`backend/db/rls_tabelas_sem_politica.sql` ligou RLS nas 6 e aplicou o padrão de
D-19 (raiz por `user_id = auth.uid()`, filha por `exists` até
`partidas.user_id`), **sem criar policy de `anon`** — mantê-la seria manter o
vazamento. Validado por curl real, tabela a tabela, com 2 contas de teste
(A com dado próprio semeado, B sem dado):

| Tabela | Caminho até o dono | anon | conta B | conta A (dona) |
|---|---|---|---|---|
| `perguntas_pendentes` | `lance_id` → `lances_criticos` → `partidas` | 0 | 0 | 1 (só a dela) |
| `anotacoes_pensamento` | `partida_id` → `partidas` | 0 | 0 | 1 (só a dela) |
| `revisoes_pensamento` | `partida_id` → `partidas` | 0 | 0 | 1 (só a dela) |
| `tempos_lance` | `partida_id` → `partidas` | 0 | 0 | 1 (só a dela) |
| `metricas_lichess_partida` | `partida_id` → `partidas` | 0 | 0 | 1 (só a dela) |
| `puzzle_atividade` | `user_id` próprio | 0 | 0 | 1 (só a dela) |

Antes da correção as três colunas traziam as **mesmas** linhas (7 / 24 / 24 /
200+ / 5 / 200+). Testes de regressão: fluxo do dono íntegro (SELECT com join
embutido, upsert e update todos HTTP 200); conta B tentando anotar na partida
da conta A → **HTTP 403** (`new row violates row-level security policy`);
pipeline intacto (service role ignora RLS). Dashboard anônimo segue renderizando
sem nenhum 4xx/5xx nem erro de console — só o cartão "Perguntas pendentes"
passou a exigir login, consequência deliberada.

Hoje **nenhuma tabela do schema `public` está sem RLS** (varredura de
`pg_class` reconferida após a migration).

### P-13 — 7 tabelas ainda servem o corpus do dono para `anon` ✅ RESOLVIDA em 13/09/2026

Era a mesma classe de exposição da P-2 — só que por policy explícita, não por
RLS desligado. As policies `to anon using(true)` criadas em D-16 e preservadas
em D-19 entregavam, para qualquer visitante com a chave pública: `partidas`
(215 linhas, PGN completo), `lances_criticos` (525), `diagnosticos` (525),
`revisao_exercicio_avulso` (12), `resumo_partida` (4), `analises_hexagono` (3),
`sessoes_treino` (3).

**Resolução (D-23 em `DECISOES.md`).**
`backend/db/rls_remove_anon_dashboard.sql` removeu as 7 policies `to anon`, e
`app.routes.ts` ligou o `authGuard` nas 4 rotas do dashboard — as duas coisas
juntas, porque isolada nenhuma das duas fecha o buraco (RLS sem guard: dado
some da tela mas nada exige login pra não ver; guard sem RLS: dado continua
público pra quem chama a API direto). Confirmado por curl, antes × depois, chave
anon pura: as 7 tabelas caíram de 215/525/525/12/4/3/3 linhas para **0 em
todas**. Logado com a conta oficial real, as mesmas 7 voltaram às contagens de
sempre — nenhuma linha perdida pro dono. Validado também no navegador
(Playwright local): as 4 rotas redirecionam pra `/login` sem sessão, e
carregam normalmente logado, com screenshot de conferência.

Efeito colateral corrigido na mesma migration: `sessoes_treino` tinha um
UPDATE anônimo (`"Permitir atualizar data_concluida"`) sem nenhum equivalente
pra `authenticated` — o botão "Marcar como concluída" quebraria pra todo
usuário logado assim que o anon caísse. Policy nova
`user_id = auth.uid()` criada e testada (UPDATE via JWT real, valor restaurado
depois).

**Consequência aceita e confirmada com o usuário antes de aplicar:** os 4
amigos que só têm `X-API-Key` (D-7), sem conta Supabase Auth, ficam sem acesso
ao Laboratório/Explicador/Analisador pela tela do Vercel até migrarem — ver
P-11.

### P-14 — IDOR em /partidas/{id} e /insights/repertorio: sessão de qualquer um acessava dado/ação de qualquer dono ✅ RESOLVIDA em 13/09/2026

Achado a partir de uma inconsistência na tabela de `ARQUITETURA.md` (dois
endpoints por-ID sem marcação 👤 de filtro por dono). Confirmado por código
E por teste com 2 contas reais em duas rodadas (D-29, depois D-30, achado
correlato da primeira):

- `GET /partidas/{id}/resumo` devolvia a narrativa completa de qualquer
  partida pra qualquer sessão válida.
- `POST /partidas/{id}/reprocessar` reagendava Stockfish/Gemini em cima da
  partida de qualquer outro usuário — confirmado por SQL que o
  `status_processamento` da partida da vítima mudava, disparado pela conta
  atacante.
- `GET /insights/repertorio` devolvia o repertório agregado **completo** de
  outro usuário pra qualquer sessão válida, sem precisar nem de um UUID —
  conta de teste sem nenhuma partida própria recebeu as 212 partidas, a
  taxa de vitória e os 525 eventos `PICO` reais do Edson.

**Resolução (D-29 e D-30 em `DECISOES.md`).** `/partidas/{id}/resumo` e
`/reprocessar` passaram a filtrar a busca por `.eq("user_id", user_id)`,
devolvendo 404 (não 403) pra partida de outro dono. As 4 buscas internas de
`insights_repertorio.py` passaram a filtrar `user_id` na própria query
(direto em `partidas`; via embed `!inner` nas 3 tabelas filhas sem coluna
própria — mesma técnica de D-28). Revalidado com contas reais nos dois
casos: quem não é dono recebe 404 ou payload vazio (conforme o tipo de
rota), quem é dono continua vendo exatamente o próprio dado, sem nada a
menos nem a mais.

Com isso, os três únicos pontos de vazamento cross-account encontrados nesta
varredura (2 rotas por-ID + 1 rota de agregação) estão fechados; nenhum
endpoint conhecido do projeto responde hoje com dado de um usuário pra
sessão de outro.

### P-3 — O gargalo é cumulativo e está congelado em TATICA 🟢 (resolvido em D-26)

`_identify_bottleneck` em `agente2_analista.py` passou a usar métricas recentes
(`frequencia_por_categoria_recente` e `gravidade_media_por_categoria_recente`,
`RECENT_WINDOW_DAYS = 30`). As métricas cumulativas continuam gravadas para alimentar
o radar histórico.

Além disso, `fetch_diagnosticos` e `build_dataframe` passaram a usar `queda_win_percent`
em vez de `gravidade_cpl`, integrando a métrica D-1 à decisão do gargalo. `top_3_tags` e o
prompt narrativo do Gemini também foram atualizados para focar no período recente. 11 testes
unitários adicionados em `backend.agentes.test_agente2_analista`.

### P-4 — O loop adaptativo nunca fechou 🟡

3 sprints prescritas, **0 concluídas, 0 com eficácia medida**. `medir_eficacia.py`
não está em nenhum workflow, apesar de documentação antiga afirmar que rodava no
semanal. Falta também o botão de concluir sprint no dashboard.

### P-5 — 14% das partidas morrem em silêncio 🟡

28 partidas em `falhou` e 2 travadas em `processando`, concentradas entre
28/08 e 09/09 — justamente as mais recentes. `analisar_partidas.py` só busca
`pendente`, então nada é retomado e nenhum alerta é emitido.

### P-6 — 6 scripts existem mas não estão automatizados ✅ 5 automatizados em 14/09/2026 (D-37)

5 dos 6 scripts foram automatizados nos workflows do GitHub Actions:
- `pipeline-diario.yml`: `importar_puzzle_activity.py` (puzzles via OAuth), `enriquecer_partidas_lichess.py` (clocks e fases), `gerar_perguntas_pendentes.py` (perguntas reflexivas) e `gerar_resumo_partida.py` (narrativas).
- `pipeline-semanal.yml`: `medir_eficacia.py` (agora com isolamento multi-tenant).

Apenas `importar_anotacoes_lichess.py` permanece manual por depender do escopo OAuth `study:write` (fora do escopo atual).

### P-7 — Repertório é ponto cego total (parcialmente mitigado em 11/09/2026) 🟡

**146 de 146 partidas do Chess.com continuam sem `eco_abertura`** — 77% do
corpus. `backfill_eco_abertura.py` nunca foi executado com sucesso para o
Chess.com. Qualquer código que dependa especificamente do código ECO (não do
nome) continua cego para essas 146 partidas.

**Mitigação parcial:** `abertura_normalizada` (D-12 em `DECISOES.md`) preenche
as 215/215 partidas independentemente do ECO — para o Chess.com ela vem da
tag `[ECOUrl]` do próprio PGN, não do backfill que nunca rodou. O vértice
ABERTURA do hexágono já pode usar `abertura_normalizada` como base real; só o
código ECO cru continua faltando.

### P-8 — Ferramentas interativas sem hábito de uso 🟡

`revisoes_pensamento` tem 23 registros concentrados em 1 único dia;
`revisao_exercicio_avulso`, 5 registros em 2 dias. O único hábito consistente são
os puzzles (660 em 41 dias), e é exatamente o dado que o pipeline não usa.

### P-9 — Pendências menores 🟢

- Livro "How to Calculate Chess Tactics" (inglês, precisa OCR com idioma inglês
  no Tesseract) nunca foi processado.
- Projeto GCP `chess-ai-pipeline`, criado por engano, pode ainda existir.
  Verifique com `gcloud projects list` e delete se estiver lá. O projeto correto
  é `gen-lang-client-0828609060`.

### P-10 — Explicador de Posição não persiste nada ✅ RESOLVIDA em 11/09/2026

Era lacuna confirmada (não decisão deliberada): `explicador_posicao.py` não
gravava nada no Supabase, e cada explicação gerada era descartada assim que a
resposta HTTP voltava.

**Resolução.** Nova tabela `explicacoes_posicao` (ver `BANCO.md`) +
`salvar_explicacao_posicao()` chamada automaticamente ao fim de
`POST /explicar-posicao` + `GET /explicacoes-posicao/recentes` + histórico
integrado na tela via o componente compartilhado `historico-analise`
(extraído do Analisador de Partida — ver D-11 em `DECISOES.md`). O mesmo
componente e o mesmo padrão de persistência do item ativo em `localStorage`
(sobrevive a F5) também foram levados para o Laboratório de Raciocínio, que já
salvava em `revisao_exercicio_avulso` mas não tinha histórico navegável.

### P-11 — Fase B do multi-tenant: Auth no frontend + RLS por usuário ✅ Fase B concluída em 13/09/2026

**Fase A concluída (11/09/2026).** `user_id NOT NULL` nas 6 tabelas raiz,
backfill das 900 linhas existentes, `DEFAULT_USER_ID` preenchendo toda escrita
nova (D-14 em `DECISOES.md`). Nenhuma policy de RLS foi criada ou alterada.

**Fase B.1 iniciada (12/09/2026) — login existe, mas está desligado do
fluxo.** `AuthService`, tela `/login` (signUp/signInWithPassword) e
`authGuard` foram implementados e testados (D-15 em `DECISOES.md`), mas
`app.routes.ts` **não** usa o guard em nenhuma rota — decisão explícita,
porque ligá-lo hoje bloquearia quem só usa X-API-Key e nunca criou conta,
contradizendo o objetivo de não travar nada ainda.

**Descoberta do teste manual de B.1, ✅ RESOLVIDA em 13/09/2026 (D-16):** login
funcionava, mas o dashboard ("Meu Hexágono") carregava vazio para quem estava
autenticado. Causa raiz confirmada via `pg_policies`: as policies de
`analises_hexagono`, `lances_criticos`, `partidas`, `resumo_partida`,
`revisao_exercicio_avulso`, `sessoes_treino` eram `roles: {anon}` — não
`{public}` — então a role `authenticated` caía em negação por padrão. Isso
nunca afetou Laboratório/Explicador/Analisador (falam com o FastAPI, que usa
service role e ignora RLS) nem a Fase A (nenhuma escrita passa por essas
policies de leitura) — só afetava quem logasse pela tela nova.

**Resolução.** `backend/db/rls_authenticated_paridade_dashboard.sql` acrescentou
uma 2ª policy de SELECT `to authenticated` em cada uma das 6 tabelas, com o
mesmo `using(true)` da policy de `anon` — paridade, não isolamento (D-16
detalha por que isso não é a Fase B.3). Testado de ponta a ponta com conta
real: conteúdo do dashboard **idêntico** (6823 caracteres) entre aba anônima
e aba autenticada, e confirmado direto via `curl` com o JWT (`HTTP 200`,
mesmas 6 linhas de `perguntas_pendentes`).

**Fase B.2 concluída (13/09/2026) — escritas passam a usar a identidade real
de quem chamou, com fallback (D-17).** `POST /revisar-avulso/salvar`,
`/explicar-posicao` e `/analisar-pgn` resolvem o dono da linha nesta ordem:
`Authorization: Bearer <token>` válido → `user.id` real (via
`supabase_client.auth.get_user(token)`); caso contrário →
`DEFAULT_USER_ID` de sempre. `X-API-Key` continua sendo exigida pra acessar
o endpoint, sem nenhuma mudança — os dois headers convivem, um controla
acesso, o outro só refina atribuição. Testado de ponta a ponta pelo
Laboratório de verdade (Stockfish + Gemini reais): logado com conta de
teste, a linha nasceu com o `user_id` da conta; no mesmo navegador sem
sessão (só `X-API-Key`), nasceu com `DEFAULT_USER_ID` — os dois caminhos
coexistindo na mesma bateria de teste, como pedido.

**Fase B.3, primeira parte concluída (13/09/2026) — leitura filtrada pelo dono nos 3 endpoints do FastAPI (D-18).**
`GET /revisoes-avulsas/recentes`, `/explicacoes-posicao/recentes` e `/partidas/recentes`
filtram por `user_id = resolver_user_id_para_escrita(request)`.

**Fase B.3, segunda parte concluída (13/09/2026) — isolamento RLS por dono nas tabelas do dashboard (D-19).**
As policies de `authenticated` criadas com `using(true)` em D-16 foram substituídas por isolamento real:
- Tabelas raiz (`analises_hexagono`, `sessoes_treino`, `partidas`, `revisao_exercicio_avulso`): `using (user_id = auth.uid())`.
- Tabelas filhas (`lances_criticos`, `diagnosticos`, `resumo_partida`): `using (exists (select 1 from ... where ... partidas.user_id = auth.uid()))`.
- A conta do Edson (`edson.hirano.dev@gmail.com`, UUID `bfde845a-8e2e-4885-801f-0fed2dd3b426`) está confirmada em `auth.users`.
- As 900 linhas do corpus histórico foram migradas para o UUID real do Edson, e `DEFAULT_USER_ID` atualizado no `.env`.
- As policies de `anon` continuam intactas.
- Testado e validado de ponta a ponta com 2 contas reais: isolamento mútuo total verificado (nenhum dado vaza entre usuários).

**Fase B concluída (13/09/2026) — login obrigatório + zero acesso anônimo ao
dado pessoal (D-23).** As 2 peças que faltavam pra fechar de vez:
`backend/db/rls_remove_anon_dashboard.sql` removeu as 7 policies `to anon
using(true)` que ainda sobravam (`partidas`, `lances_criticos`,
`diagnosticos`, `revisao_exercicio_avulso`, `resumo_partida`,
`analises_hexagono`, `sessoes_treino` — ver P-13 abaixo); `app.routes.ts`
ligou o `authGuard` (existia desde D-15, nunca tinha sido aplicado) nas 4
rotas do dashboard (`/`, `/laboratorio`, `/explicador`, `/analisador`).
Confirmado por curl que a chave anon pura agora recebe 0 linhas nas 7
tabelas, e por navegador (Playwright local + screenshot) que visitante sem
sessão é redirecionado pra `/login` em qualquer uma das 4 rotas, enquanto a
conta oficial logada continua vendo e fazendo tudo exatamente como sempre —
incluindo o UPDATE de "Marcar como concluída" em `sessoes_treino`, que
ganhou policy própria pra `authenticated` nesta mesma migration (não existia
antes; o fluxo logado nunca tinha sido exercitado de verdade).

**Autenticação unificada (13/09/2026) — a API também passou a exigir a sessão
(D-25).** Era a última fronteira que ainda aceitava o mecanismo antigo:
`X-API-Key` continuava sendo a porta de entrada dos 12 endpoints do FastAPI,
com a sessão servindo só de bônus opcional. Agora a dependency
`verificar_sessao` substitui `verificar_api_key` em **todos** os 12; o
`user_id` real chega por injeção nas 6 rotas que precisam dele; e o fallback
pro `DEFAULT_USER_ID` sumiu dos caminhos de API (continua valendo **só** pro
CLI standalone, que não passa pela API). No frontend, `headersComSessao()`
substituiu os headers de chave em todos os métodos, a tela de "Chave de
acesso" saiu das 3 telas interativas e `AuthLocalService` foi removido por
ficar sem consumidor.

Validado por curl: os 12 endpoints devolvem `401` sem header **e também com
uma `X-API-Key` válida** — o mecanismo antigo não abre mais porta nenhuma;
com a sessão real, respondem `200` com os dados do dono. E no navegador, com
a conta real logada: as 4 telas abrem sem pedir chave em lugar nenhum, toda
chamada sai com `Authorization: Bearer` e nenhuma com `X-API-Key`, sem 4xx/5xx
nem erro de console.

Com D-14 (dono em toda escrita) + D-17/D-18 (identidade real, leitura
filtrada) + D-19/D-22 (RLS isolado, zero tabela sem policy) + D-23 (zero
policy `anon`, login obrigatório) + D-25 (sessão como único gate da API),
**não sobra mais nenhum caminho anônimo nem por chave pro dado pessoal do
dono**. A Fase B está encerrada; o que resta é migração de usuário e limpeza,
não arquitetura de isolamento:

- **Migrar os 4 amigos para conta própria.** Agora é **pré-requisito**, não
  recomendação: D-23 fechou a porta na interface e D-25 fechou na API, então
  `X-API-Key` não dá mais acesso a nada. Ver D-25.
- **Adicionar FK para `auth.users(id)`** nas 6 tabelas raiz (comentada no fim
  de `backend/db/user_id_tabelas_raiz.sql`).
- **Limpeza candidata, NÃO fazer sem avaliar (registrado em D-25):**
  `API_SECRET_KEYS`/`API_SECRET_KEY` não são mais gate de acesso — o
  `verificar_api_key`, o `_resolver_api_keys()` e a exigência dessas variáveis
  no startup ficaram sem uso e podem sair. Já `DEFAULT_USER_ID` **não pode ser
  removida**: continua sendo o dono gravado pelos scripts de CLI standalone,
  que não passam pela API. Sair de vez com a chave também implica revisar o
  `deploy-backend.yml` (D-20), que hoje propaga `API_SECRET_KEYS` como secret
  obrigatório e abortaria o deploy sem ela.

O INSERT anônimo residual em `revisao_exercicio_avulso` (achado em D-23) foi
fechado em 13/09/2026 por D-24 — confirmado que nenhum fluxo real dependia
dele (frontend nunca escreve nessa tabela direto, só via FastAPI/service
role) e validado por curl que o INSERT anônimo agora recebe `HTTP 401`.

P-2 e P-13 estão fechadas (D-22 e D-23). A frente de RLS/Auth deste projeto
não tem mais pendência de segurança aberta — só a migração de usuário acima.

**Fase C — onboarding de novo usuário real (13/09/2026, D-28).** Antes de
D-28, mesmo com login e RLS por dono funcionando desde a Fase B, TODA a
coleta e análise ainda era single-tenant por baixo dos panos: a coleta em
lote sempre gravava no `DEFAULT_USER_ID`, e os Agentes 2 e 3 nunca filtravam
por dono — o Agente 2 misturaria os diagnósticos de qualquer segunda conta
com os do Edson no mesmo hexágono. Corrigido com a tabela `perfis_usuario`
(onde cada um cadastra sua própria conta de Lichess/Chess.com, tela `/perfil`)
e um loop por usuário em `coletar_partidas.py`, `coletar_partidas_chesscom.py`,
`agente2_analista.py` e `agente3_prescritor.py`. Validado de ponta a ponta com
conta de teste real (Admin API + limpeza ao final, mesmo padrão de D-19): a
conta de teste gerou hexágono e coleta próprios, isolados, sem tocar nos 525
diagnósticos nem no gargalo `TATICA` do Edson. **A Lais já pode ser
convidada** — falta só ela se cadastrar em `/login` e preencher `/perfil`.

Consequência menor: `LICHESS_USERNAME`/`CHESSCOM_USERNAME` deixaram de ter
leitor em `pipeline-diario.yml` (a coleta em lote lê `perfis_usuario` agora) —
os secrets correspondentes no GitHub ficaram órfãos, candidatos a remoção
futura, mesma categoria de pendência não bloqueante de `API_SECRET_KEYS` em
D-25. As duas variáveis continuam vivas no `.env` só para quem roda
`analisar_pgn_avulso.py` direto no terminal.

**Fase 1 do roadmap comercial — os 5 scripts restantes (14/09/2026, D-31).**
Investigação individual dos scripts que ainda não tinham passado pelo
tratamento de D-28: `gerar_resumo_partida.py`, `gerar_perguntas_pendentes.py`
e `normalizar_aberturas.py` já eram seguros (operam partida/lance por vez ou
não agregam entre partidas — confirmado por leitura, nenhuma mudança feita).
`enriquecer_partidas_lichess.py` tinha vazamento funcional real: usava um
`LICHESS_USERNAME` fixo do `.env` para identificar a cor rastreada, o que
faria `metricas_lichess_partida` nunca ser gravada para um segundo usuário —
corrigido com o mesmo loop por perfil de D-28. `importar_puzzle_activity.py`
gravava tudo sob `DEFAULT_USER_ID` sem checagem — corrigido de forma
diferente (a API de puzzles do Lichess só devolve dado do dono do token, não
aceita username): o script agora identifica o dono real via `GET
/api/account` e resolve o `user_id` correspondente em `perfis_usuario`, sem
fallback. Validado com 2 contas de teste reais e 2 partidas Lichess reais
(Admin API + limpeza ao final, mesmo padrão de D-19/D-28): cada perfil só
processou e só gravou `tempos_lance` da própria partida.

**Fase 1 do roadmap comercial — limite diário por usuário (14/09/2026,
D-32).** As 4 rotas caras (`/analisar-pgn`, `/explicar-posicao`,
`/revisar-avulso`, `/reconhecer-posicao`) passaram a exigir também
`limite_diario(rota)`: RPC atômico (`incrementar_uso_diario`, tabela nova
`uso_diario_usuario`, dia calculado em `America/Sao_Paulo`) roda antes do
corpo da rota e barra com `429` quando a contagem do dia supera o limite
(20/50/50/30, configurável por env var, sem deploy). `/revisar-avulso` e
`/reconhecer-posicao` migraram de `dependencies=[Depends(verificar_sessao)]`
para injeção de `user_id` no processo (mesma correção de forma de D-29/D-30).
Validado com 2 contas reais e limite temporariamente baixo, servidor real
(Stockfish + Gemini reais, sem mock): 3ª chamada da conta A voltou `429` em
~1s contra ~36s das duas primeiras aceitas; conta B, sem uso prévio, não foi
afetada. RLS confirmada real (cada conta só lê a própria linha) e o `EXECUTE`
do RPC revogado de `authenticated` confirmado real (`403` ao tentar
incrementar o contador de outra conta direto via REST).

**OAuth do Lichess — Estágio 1 (14/09/2026, D-33).** A conexão com o Lichess
deixou de depender de um token pessoal no `.env` (que servia só para uma
conta): `POST /lichess/oauth/iniciar` e `GET /lichess/oauth/callback`
implementam Authorization Code + PKCE (S256), guardando o token de cada
usuário em `lichess_oauth_tokens` — tabela sem policy de RLS nenhuma, porque o
token nunca pode chegar ao frontend. Investigação da doc oficial confirmou que
o Lichess **não exige registro prévio de client_id** e **não emite refresh
token** (access token vale ~1 ano), o que mudou o desenho do item de renovação:
`obter_access_token_lichess()` valida `expires_at` e devolve `None` quando é
preciso reconectar, já que não há o que renovar. Validado de ponta a ponta com
a conta real `tantofaz123` autorizando no navegador: token gravado, e com ele
`GET /api/account` e `GET /api/puzzle/activity` reais responderam `200`.
**OAuth do Lichess — Estágio 2 (14/09/2026, D-34).** `importar_puzzle_activity.py`
reescrito para consumir `lichess_oauth_tokens` via módulo compartilhado
`backend/common/lichess_oauth.py`. O script percorre todas as contas com token
válido, isola erros por usuário (401 revogado avisa para reconectar sem derrubar
os demais), grava em `puzzle_atividade` com o `user_id` correto e aposentou o uso
de `LICHESS_STUDY_TOKEN` neste fluxo. Testado com a conta real do Edson (660 puzzles
importados com sucesso).

**OAuth do Lichess — Estágio 3 (14/09/2026, D-35).** Interface de conexão entregue em
`/perfil`: card de conexão com badge de status ativo/desconectado, botão "Conectar com
Lichess" (redireciona para autorização PKCE), botões de reconectar/desconectar, e tratamento
completo dos query params de retorno (`?conectado=lichess` e `?erro=...`). Backend ganhou
`GET /lichess/oauth/status` e `POST /lichess/oauth/desconectar`. **Ciclo OAuth 100% concluído.**

### P-12 — Deploy automático não sincronizava env vars com os Secrets ✅ RESOLVIDA em 13/09/2026

Não era decisão deliberada, era lacuna: `deploy-backend.yml` só propagava
`DEFAULT_USER_ID` via `--update-env-vars`; as demais variáveis
(`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`,
`API_SECRET_KEYS`) só chegavam ao Cloud Run se alguém lembrasse de rodar
manualmente `gcloud run deploy --env-vars-file=env.yaml`. Causou 2 incidentes
reais nesta sessão: a introdução de `DEFAULT_USER_ID` (D-14) e a mudança do
seu valor pro UUID real do Edson (D-19) — nos dois casos o deploy automático
seguinte continuou rodando com o valor antigo/vazio até alguém notar e
propagar na mão.

**Resolução (D-20 em `DECISOES.md`).** O workflow agora gera, a cada deploy,
um arquivo de env vars a partir dos GitHub Secrets e sobe o Cloud Run com
`--env-vars-file` (substituição total, não `--update-env-vars`/merge) — os 5
valores em produção passam a ser sempre exatamente o que os Secrets dizem
naquele momento, sem depender de ninguém rodar comando manual. Validado
localmente: confirmado via `gcloud run services describe` que os 5 valores
hoje em produção batem com `env.yaml`, e testada a geração do arquivo YAML
(incluindo que `API_SECRET_KEYS`, que tem vírgula no valor, sobrevive intacto
nesse formato — o que quebraria com `--update-env-vars` inline).

## 5. O que está validado e funcionando

Ingestão Lichess + Chess.com; Stockfish com detecção de `PICO` e `EROSAO`;
Agentes 1, 2 e 3; RAG com 2 livros processados ("Meu Sistema" de Nimzowitsch e
"Xadrez Vitorioso: Táticas" de Seirawan/Silman); Laboratório de Raciocínio com
notação PT/EN, reconhecimento de posição por foto, preview do tabuleiro e
histórico navegável dos exercícios salvos; Explicador de Posição com
persistência automática e histórico navegável; Analisador de Partida com
histórico e reprocessamento; as 3 telas interativas compartilham o mesmo
componente de histórico (`historico-analise`) e o mesmo padrão de
sobrevivência a F5 via `localStorage` (ver D-11 em `DECISOES.md`); deploy
contínuo de frontend e backend; autenticação por múltiplas chaves nomeadas;
`abertura_normalizada` preenchida para as 215 partidas existentes e captura de
precisão por fase (`precisao_abertura`/`precisao_meiojogo`/`precisao_final`)
daqui pra frente no enriquecimento Lichess (ver D-12 em `DECISOES.md`);
`GET /insights/repertorio` já consome isso (D-13) e cruza com resultado, lance
de PICO e categoria do hexágono por abertura — testado contra o banco de
produção em 11/09/2026, ver a distribuição da Francesa na seção 3. Ainda não
consumido por nenhuma tela do frontend.

**Login (Fase B.1, 12/09/2026), paridade RLS (13/09/2026) e identidade real
nas escritas (Fase B.2, 13/09/2026) funcionam de ponta a ponta.** Cadastro,
confirmação de e-mail, login, logout e restauração de sessão num F5 foram
testados com uma conta real e zero erro de console. O achado de B.1 (logar
esvaziava o dashboard) foi corrigido em D-16: o conteúdo do "Meu Hexágono"
agora é idêntico entre anônimo e autenticado, confirmado caractere a
caractere e via `curl` direto no PostgREST com o JWT real. Uma análise real
no Laboratório (Stockfish + Gemini, não mock), salva estando logado, grava
com o `user_id` real da conta (D-17); a mesma ação sem sessão continua
gravando `DEFAULT_USER_ID`, como sempre. `authGuard` existe e passa nos
testes, mas continua deliberadamente desligado de qualquer rota (decisão de
B.1, ainda válida).

## 6. Como re-verificar

```sql
-- volume por tabela e cobertura do pipeline
select
 (select count(*) from partidas) partidas,
 (select count(*) from partidas where status_processamento='concluido') concluidas,
 (select count(*) from partidas where status_processamento<>'concluido') travadas,
 (select count(*) from diagnosticos) diagnosticos,
 (select count(distinct partida_id) from metricas_lichess_partida) com_metricas,
 (select count(*) from partidas where eco_abertura is null) sem_eco;

-- distribuição das tags
select tag, count(*) n from diagnosticos d, unnest(d.tags_falha) tag
group by tag order by n desc;

-- composição por cadência
select coalesce(substring(pgn from '\[TimeControl "([^"]+)"\]'),'?') tc, count(*)
from partidas where status_processamento='concluido' group by 1 order by 2 desc;

-- distribuição de abertura_normalizada
select abertura_normalizada, count(*) n from partidas
group by 1 order by n desc;

-- spot-check de /insights/repertorio: taxa de vitória por abertura+cor
-- (sem o limiar MIN_AMOSTRA nem o bucket "outras" que o endpoint aplica)
select abertura_normalizada, cor_jogada, count(*) total,
 round(100.0 * count(*) filter (where resultado='VITORIA') / count(*), 2) taxa_vitoria_pct
from partidas
where plataforma in ('LICHESS','CHESSCOM') and abertura_normalizada is not null
group by 1, 2 order by total desc;

-- P-11/D-16: cada uma das 6 tabelas tem que ter SELECT pra {anon} E {authenticated}
select tablename, policyname, roles, cmd from pg_policies
where tablename in ('analises_hexagono','lances_criticos','partidas','resumo_partida','revisao_exercicio_avulso','sessoes_treino')
order by tablename, roles::text;

-- dono preenchido nas 6 tabelas raiz (P-11 / D-14): com_user tem que bater com total
select 'partidas' t, count(*) total, count(user_id) com_user from partidas
union all select 'analises_hexagono', count(*), count(user_id) from analises_hexagono
union all select 'sessoes_treino', count(*), count(user_id) from sessoes_treino
union all select 'explicacoes_posicao', count(*), count(user_id) from explicacoes_posicao
union all select 'puzzle_atividade', count(*), count(user_id) from puzzle_atividade
union all select 'revisao_exercicio_avulso', count(*), count(user_id) from revisao_exercicio_avulso;

-- P-11/D-17: distribuição de donos por tabela - hoje deve ser só DEFAULT_USER_ID
-- em todo lugar (nenhum amigo migrou ainda); um user_id diferente aparecendo
-- aqui confirma que o caminho de sessão real está gravando de verdade
select 'partidas' t, user_id, count(*) n from partidas group by 1, 2
union all select 'revisao_exercicio_avulso', user_id, count(*) from revisao_exercicio_avulso group by 1, 2
union all select 'explicacoes_posicao', user_id, count(*) from explicacoes_posicao group by 1, 2
order by 1, 3 desc;

-- o loop fechou?
select count(*) total, count(data_concluida) concluidas, count(eficacia_medida) medidas
from sessoes_treino;
```

```bash
# testes e cobertura do CI
python -m unittest $(find backend -name "test_*.py" | sed 's/\.py$//' | sed 's#/#.#g')
grep -c "backend\." .github/workflows/deploy-backend.yml   # módulos listados no CI
```
