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
| `lances_criticos` | `partida_id`, `numero_lance`, `numero_lance_fim`, `tipo_evento`, `gravidade_cpl`, `queda_win_percent` | lances e janelas ruins achados pelo Stockfish |
| `diagnosticos` | `lance_id`, `tags_falha[]`, `diagnostico_mecanico`, `tipo_erro` | causa do erro, gerada pelo Gemini |
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
`backend/common/tenant.py`. A FK para `auth.users` ainda **não** existe — ver
P-11 em `ESTADO.md`.

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

Estas tabelas estão com **RLS desabilitado** e portanto legíveis e graváveis por
qualquer portador da chave `anon`, que é pública no bundle do frontend:
`metricas_lichess_partida`, `tempos_lance`, `anotacoes_pensamento`,
`perguntas_pendentes`, `revisoes_pensamento`, `puzzle_atividade`.

Habilitar RLS sem criar policies bloqueia todo o acesso, inclusive o dos scripts
que usam a service role. Tratar como decisão do dono do projeto, não como
correção automática. Ver pendência em `ESTADO.md`.

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
As policies `to anon` continuam intactas (`using(true)`), permitindo que o
fluxo histórico sem login continue operando normalmente.
Ao criar uma tabela nova com RLS, decida a lista de roles de propósito —
`to public` cobre as duas de uma vez; `to anon` sozinho exclui autenticados.

