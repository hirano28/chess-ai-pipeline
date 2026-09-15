---
doc: BANCO.md
escopo: schema do Supabase, vocabulário controlado, invariantes e regras de migração
nao_contem: contagem de linhas nem estado dos dados (ver ESTADO.md)
verificado_em: 2026-09-13
fonte: introspecção direta do projeto Supabase pmzmershonrqzwbmhaco
---

# Banco de dados — Supabase (Postgres + pgvector)

## 1. Tabelas

### Núcleo do pipeline

| Tabela | Colunas relevantes | Papel |
|---|---|---|
| `partidas` | `id`, `plataforma`, `external_id`, `pgn`, `data_partida`, `resultado`, `cor_jogada`, `rating_proprio`, `rating_oponente`, `eco_abertura`, `abertura_normalizada`, `status_processamento`, `created_at` | toda partida coletada |
| `lances_criticos` | `partida_id`, `numero_lance`, `numero_lance_fim`, `tipo_evento`, `gravidade_cpl`, `queda_win_percent`, `fen_antes_lance`, `origem` | lances e janelas ruins achados pelo Stockfish. `fen_antes_lance` (D-27) é o FEN de antes do lance (ou do início da janela, em EROSAO); `origem` (D-43) indica se o lance foi detectado pelo motor (`'GRAVIDADE'`) ou promovido por anotação de pensamento do jogador no estudo (`'ANOTACAO'`) |
| `diagnosticos` | `lance_id`, `tags_falha[]`, `diagnostico_mecanico`, `tipo_erro` | causa do erro, gerada pelo Gemini; `tipo_erro` (D-43) categoriza `PROCESSO` vs `CONTEUDO` vs `INDETERMINADO` contrastando o raciocínio do jogador com a avaliação do motor |
| `analises_hexagono` | `data_analise`, `metricas` (jsonb), `narrativa`, `gargalo_sistemico_atual` | saída do Agente 2 |
| `sessoes_treino` | `diagnostico_gargalo`, `modulos` (jsonb), `data_prescrita`, `data_concluida`, `eficacia_medida`, `observacoes` | sprints do Agente 3 |

### Enriquecimento

| Tabela | Colunas relevantes | Papel |
|---|---|---|
| `metricas_lichess_partida` | `partida_id`, `precisao_propria`, `precisao_oponente`, `acpl`, `fase_abertura_fim`, `fase_meiojogo_fim`, `precisao_abertura`, `precisao_meiojogo`, `precisao_final` | métricas que o próprio Lichess já calcula. **Só Lichess** — a API do Chess.com não expõe equivalente. As 3 últimas colunas vêm de `players.<cor>.analysis.phases` (lado próprio) e só existem para partidas enriquecidas a partir de agora — sem reprocessamento retroativo automático das partidas já enriquecidas antes |
| `tempos_lance` | `partida_id`, `numero_lance`, `cor`, `tempo_restante_seg`, `tempo_gasto_seg` | relógio por lance; habilita a tag `gestao_de_tempo_ruim` |
| `anotacoes_pensamento` | `partida_id`, `numero_lance`, `texto_pensamento`, `origem` | o que o jogador escreveu, importado de um Lichess Study |
| `perguntas_pendentes` | `lance_id`, `pergunta_texto`, `status` | perguntas retroativas para lances sem anotação |
| `puzzle_atividade` | `puzzle_id`, `data`, `acertou`, `temas[]`, `rating_puzzle` | histórico de puzzles do Lichess |

### Ferramentas interativas

| Tabela | Colunas relevantes | Papel |
|---|---|---|
| `revisoes_pensamento` | `partida_id`, `numero_lance`, `texto_pensamento`, `qualidade_lance`, `qualidade_raciocinio`, `feedback_texto`, `queda_win_percent`, `lance_jogado`, `melhor_lance` | revisão de raciocínio em partida real |
| `revisao_exercicio_avulso` | `fen`, `lance_jogado`, `melhor_lance`, `queda_win_percent`, `texto_pensamento`, `qualidade_lance`, `qualidade_raciocinio`, `feedback_texto`, `origem` | mesma revisão, para exercício avulso do Laboratório |
| `resumo_partida` | `partida_id`, `narrativa`, `pontos_criticos` (jsonb), `momento_chave_estrategico` | resumo narrativo da partida inteira |
| `explicacoes_posicao` | `fen`, `lado_analisado`, `resultado` (jsonb, resposta completa), `created_at` | histórico do Explicador de Posição (fecha P-10 — ver `DECISOES.md` D-11) |

### RAG de livros

| Tabela | Colunas relevantes | Papel |
|---|---|---|
| `livros_chunks` | `livro`, `capitulo`, `pagina_aprox`, `conteudo`, `embedding` (vector) | trechos vetorizados dos livros |
| `indice_conceitual` | `conceito`, `livro`, `capitulo`, `pagina_aprox` | mapa **manual** conceito → localização |

### Dono do dado (`user_id`) — Fase A do multi-tenant

Estas **6 tabelas raiz** têm `user_id uuid not null`, porque são as únicas sem
pai natural: `partidas`, `analises_hexagono`, `sessoes_treino`,
`explicacoes_posicao`, `puzzle_atividade`, `revisao_exercicio_avulso`.

Toda tabela filha **herda o dono pela cadeia de FK** que já existe
(`lances_criticos.partida_id`, `diagnosticos.lance_id`, etc.) e por isso
**não** tem coluna `user_id` — duplicar o fato criaria divergência possível.
Ver D-14 em `DECISOES.md` antes de acrescentar a coluna em qualquer outra
tabela. `livros_chunks` e `indice_conceitual` ficam de fora por serem corpus
compartilhado, não dado de usuário.

O valor vem de `DEFAULT_USER_ID` (obrigatória), lida por
`backend/common/tenant.py`. A FK para `auth.users` ainda **não** existe nestas
6 — ver P-11 em `ESTADO.md`.

### Perfis de usuário — Fase C do multi-tenant (D-28)

| Tabela | Colunas relevantes | Papel |
|---|---|---|
| `perfis_usuario` | `user_id` (PK, **FK real** para `auth.users(id)`), `lichess_username`, `chesscom_username` | conta(s) de Lichess/Chess.com de cada usuário logado |

Fonte que `backend/ingestao/coletar_partidas.py` e
`coletar_partidas_chesscom.py` usam pra saber DE QUEM buscar partidas e a QUEM
atribuir o `user_id` gravado — sem uma linha aqui, a pessoa pode logar e ver as
telas, mas nunca tem partida nenhuma ingerida. Constraint `check` exige pelo
menos uma das duas colunas preenchida. RLS: cada usuário só lê/grava a própria
linha (`user_id = auth.uid()`, mesmo padrão de D-19).

### Limite diário de uso (D-32)

| Tabela | Colunas relevantes | Papel |
|---|---|---|
| `uso_diario_usuario` | `user_id` (**FK real** para `auth.users(id)`), `data`, `rota`, `contagem` — PK composta `(user_id, data, rota)` | contador de chamadas por usuário/dia/rota, para o limite diário das rotas caras da API |

Incrementada só por `incrementar_uso_diario(p_user_id, p_rota)`, uma função
Postgres `SECURITY DEFINER` que faz `INSERT ... ON CONFLICT DO UPDATE SET
contagem = contagem + 1` atomicamente (evita a corrida de 2 requisições
concorrentes lendo a mesma contagem) e devolve a nova contagem. `data` é
calculada em `America/Sao_Paulo`, não UTC — o limite reseta à meia-noite local,
não às 21h. `EXECUTE` da função é **revogado** de `anon`/`authenticated`: só o
backend (service role) chama; sem a revogação, qualquer usuário logado
poderia chamar o RPC direto via `POST /rest/v1/rpc/incrementar_uso_diario`
passando o `user_id` de outra pessoa e esgotar o limite dela. RLS na tabela:
cada usuário só lê a própria linha (`user_id = auth.uid()`), sem policy de
escrita para `authenticated` — a única escrita é via RPC. ### OAuth do Lichess (D-33)

| Tabela | Colunas relevantes | Papel |
|---|---|---|
| `lichess_oauth_tokens` | `user_id` (PK, **FK real** para `auth.users(id)`), `access_token`, `refresh_token`, `expires_at`, `scopes` | token de acesso de cada usuário à própria conta do Lichess |
| `lichess_oauth_pkce` | `state` (PK), `user_id`, `code_verifier`, `expires_at` | estado efêmero de um fluxo OAuth em andamento (TTL 10 min, consumo único) |

**As duas não têm policy de RLS nenhuma** — nem `anon`, nem `authenticated`.
Isso é o mecanismo, não esquecimento: o conteúdo das duas é material secreto
que não pode chegar ao frontend em hipótese alguma (o `access_token` dá acesso
à conta Lichess da pessoa; o `code_verifier` é o que impede um código de
autorização interceptado de virar token). Só a service role, que ignora RLS,
lê e escreve. Confirmado no banco real: um JWT do próprio dono do token recebe
`[]` ao consultar `lichess_oauth_tokens` via PostgREST.

`refresh_token` é sempre `NULL`: o Lichess **não emite** refresh tokens — o
access token já vem com ~1 ano de validade. Quem precisar do token deve pegá-lo
por `obter_access_token_lichess()` em `api_server.py`, que valida `expires_at`
antes de entregar e devolve `None` quando a pessoa precisa reconectar.

`perfis_usuario`, `uso_diario_usuario`, `lichess_oauth_tokens` e
`lichess_oauth_pkce` são as únicas tabelas do schema com FK declarada
para `auth.users` até agora — as 6 tabelas raiz da seção anterior não têm.

## 2. Vocabulário controlado — as 16 tags de falha

`diagnosticos.tags_falha` é um array restrito a estas 16 tags, e só elas
(regra R1 em `AGENTS.md`):

`calculo_tatico_deficiente`, `seguranca_do_rei`, `perda_de_iniciativa`,
`erro_tecnico_de_final`, `fraqueza_estrutural_de_peoes`,
`negligencia_profilatica`, `gestao_de_tempo_ruim`,
`abertura_de_linhas_desfavoravel`, `simplificacao_prematura`,
`avaliacao_posicional_incorreta`, `troca_desfavoravel`,
`falta_de_coordenacao_de_pecas`, `ataque_prematuro`, `passividade_excessiva`,
`visao_em_tunel`, `perda_de_material`.

As tags são agrupadas em 6 categorias do hexágono por `HEXAGON_CATEGORIES`, em
`backend/agentes/agente2_analista.py` — essa constante é a fonte de verdade do
mapeamento tag → categoria.

## 3. Valores enumerados

| Coluna | Valores possíveis |
|---|---|
| `partidas.status_processamento` | `pendente`, `processando`, `concluido`, `falhou` |
| `partidas.plataforma` | `LICHESS`, `CHESSCOM`, `MANUAL` |
| `partidas.cor_jogada` | `BRANCAS`, `PRETAS` |
| `partidas.resultado` | `VITORIA`, `DERROTA`, `EMPATE` |
| `lances_criticos.tipo_evento` | `PICO` (erro pontual), `EROSAO` (perda gradual numa janela) |
| `diagnosticos.tipo_erro` | `PROCESSO`, `CONTEUDO`, `INDETERMINADO` |
| `revisoes_pensamento.qualidade_lance` | `BOM`, `SUBOTIMO`, `RUIM` |
| `revisoes_pensamento.qualidade_raciocinio` | `SOLIDO`, `FALHO`, `INDETERMINADO` |

## 4. Invariantes que o código assume

- **Só `pendente` é processado.** `analisar_partidas.py` busca exclusivamente
  `status_processamento = 'pendente'`. Partida marcada `falhou` ou travada em
  `processando` nunca é retomada sozinha — precisa de reset manual (regra R7) ou
  do endpoint `POST /partidas/{id}/reprocessar`.
- **`EROSAO` usa janela, não lance único.** Nesses registros
  `numero_lance`/`numero_lance_fim` delimitam a janela, e o prompt do Agente 1
  precisa ser o de erosão.
- **`queda_win_percent` é a métrica de gravidade correta** (ver `D-1` em
  `DECISOES.md`). `gravidade_cpl` continua gravada por compatibilidade
  histórica. Atenção: `agente2_analista.py` ainda agrega por `gravidade_cpl` —
  ver pendência em `ESTADO.md`.
- **ECO só existe para Lichess.** A coleta do Chess.com não preenche
  `eco_abertura`; existe `backend/ingestao/backfill_eco_abertura.py` para isso.
- **Não apague partida antiga sem anotação.** Ela segue válida para a estatística
  do hexágono; só não tem `tipo_erro` nem `checklist_rotina` preenchidos, e isso
  é esperado, não é defeito.
- **`abertura_normalizada` agrupa por família, não é o nome completo da linha.**
  Preenchida por `backend/agentes/normalizar_aberturas.py`, que resolve o nome
  cru de um jeito diferente por plataforma (tag `[ECOUrl]` no Chess.com, tag
  `[Opening]` quando presente, ou a API do Lichess quando nenhuma das duas
  tem o nome) e só agrupa em família (`"Siciliana"`, `"Francesa"`, ...) quando
  reconhece um padrão do dicionário em `MAPEAMENTO_FAMILIAS`; sem
  correspondência, grava o nome original completo (nunca inventa uma família).
  Rode o script de novo a cada leva nova de partidas — ele só processa linhas
  com a coluna ainda `null`.

## 5. Migrações

Os arquivos `.sql` versionados ficam em `backend/db/`. Depois de qualquer DDL,
rode `NOTIFY pgrst, 'reload schema';` (regra R5) — sem isso a API REST devolve
`PGRST204` para a coluna nova.

## 6. Row Level Security

**Nenhuma tabela do schema `public` está com RLS desabilitado** (varredura de
`pg_class` em 13/09/2026). As 6 que estavam — `metricas_lichess_partida`,
`tempos_lance`, `anotacoes_pensamento`, `perguntas_pendentes`,
`revisoes_pensamento`, `puzzle_atividade` — foram fechadas por D-22
(`backend/db/rls_tabelas_sem_politica.sql`), com policies só de
`authenticated` isoladas por dono e **nenhuma** de `anon`, já que era
justamente o acesso anônimo que vazava dado pessoal.

Habilitar RLS sem criar policies **não** bloqueia os scripts do pipeline: eles
usam a service role key, que ignora RLS por definição. Bloqueia só `anon` e
`authenticated` — é assim que `explicacoes_posicao`, `livros_chunks` e
`indice_conceitual` ficam fechadas de propósito (RLS ligado, zero policies),
já que nenhuma tela lê essas três direto.

**Policy de RLS é por role, não por condição.** Uma policy criada com
`to anon using (true)` só vale pra quem conecta como `anon` — a role
`authenticated` (usuário logado via Supabase Auth) cai em negação por
padrão se não existir NENHUMA policy própria pra ela.
Inicialmente (D-16), criaram-se policies `to authenticated using(true)` para
paridade. Na Fase B.3 (D-19), essas policies foram substituídas por
**isolamento estrito por dono**:
- Tabelas raiz com `user_id` próprio (`analises_hexagono`, `sessoes_treino`,
  `partidas`, `revisao_exercicio_avulso`): `using (user_id = auth.uid())`.
- Tabelas filhas sem `user_id` próprio (`lances_criticos`, `diagnosticos`,
  `resumo_partida`): `using (exists (select 1 from ... where ... partidas.user_id = auth.uid()))`.
**As policies `to anon` foram removidas dessas 7 tabelas (D-23, 13/09/2026),
e o INSERT `to anon` residual de `revisao_exercicio_avulso` também (D-24,
mesma data).** Não existe mais nenhuma policy `to anon` no schema `public`
inteiro — o dashboard passou a exigir login (`authGuard` ligado em
`app.routes.ts`), então o acesso anônimo que essas policies sustentavam
deixou de fazer sentido.
Ao criar uma tabela nova com RLS, decida a lista de roles de propósito —
`to public` cobre as duas de uma vez; `to anon` sozinho exclui autenticados.

