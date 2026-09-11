---
doc: BANCO.md
escopo: schema do Supabase, vocabulário controlado, invariantes e regras de migração
nao_contem: contagem de linhas nem estado dos dados (ver ESTADO.md)
verificado_em: 2026-09-11
fonte: introspecção direta do projeto Supabase pmzmershonrqzwbmhaco
---

# Banco de dados — Supabase (Postgres + pgvector)

## 1. Tabelas

### Núcleo do pipeline

| Tabela | Colunas relevantes | Papel |
|---|---|---|
| `partidas` | `id`, `plataforma`, `external_id`, `pgn`, `data_partida`, `resultado`, `cor_jogada`, `rating_proprio`, `rating_oponente`, `eco_abertura`, `status_processamento`, `created_at` | toda partida coletada |
| `lances_criticos` | `partida_id`, `numero_lance`, `numero_lance_fim`, `tipo_evento`, `gravidade_cpl`, `queda_win_percent` | lances e janelas ruins achados pelo Stockfish |
| `diagnosticos` | `lance_id`, `tags_falha[]`, `diagnostico_mecanico`, `tipo_erro` | causa do erro, gerada pelo Gemini |
| `analises_hexagono` | `data_analise`, `metricas` (jsonb), `narrativa`, `gargalo_sistemico_atual` | saída do Agente 2 |
| `sessoes_treino` | `diagnostico_gargalo`, `modulos` (jsonb), `data_prescrita`, `data_concluida`, `eficacia_medida`, `observacoes` | sprints do Agente 3 |

### Enriquecimento

| Tabela | Colunas relevantes | Papel |
|---|---|---|
| `metricas_lichess_partida` | `partida_id`, `precisao_propria`, `precisao_oponente`, `acpl`, `fase_abertura_fim`, `fase_meiojogo_fim` | métricas que o próprio Lichess já calcula. **Só Lichess** — a API do Chess.com não expõe equivalente |
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
