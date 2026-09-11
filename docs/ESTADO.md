---
doc: ESTADO.md
escopo: ÚNICO lugar do repositório onde mora estado factual (contagens, status, pendências)
verificado_em: 2026-09-11
como_reverificar: rode as queries da seção 6 e os comandos da seção 1
aviso: número sem data de verificação em qualquer outro documento deve ser tratado como suspeito
---

# Estado verificado — 2026-09-11

Tudo nesta página foi conferido nesta data contra o banco real
(`pmzmershonrqzwbmhaco`), o código e os workflows. Ao mudar qualquer fato aqui,
atualize também a data no cabeçalho.

## 1. Testes e build

| Item | Valor verificado |
|---|---|
| Testes de backend | **269**, todos passando, em 12 módulos |
| Testes de frontend (Vitest) | **47**, todos passando, em 5 arquivos |
| `ng build` de produção | passa; avisa excesso de bundle (~770 kB), conhecido e aceito |

`.github/workflows/deploy-backend.yml` lista os 12 módulos de teste do backend
à mão (incluindo `backend.common.test_notacao_pt`, que já esteve faltando —
regra R8 corrigida). Continua sendo uma lista mantida manualmente: todo módulo
de teste novo precisa ser adicionado lá também.

## 2. Volume de dados

| Tabela | Linhas |
|---|---|
| `partidas` | 211 (02/07/2026 a 10/09/2026) |
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
| `metricas_lichess_partida` | 4, para 61 partidas do Lichess |
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

## 4. Pendências

### P-1 — Chaves de API expostas, rotação nunca feita 🔴

`GEMINI_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY` e as `API_SECRET_KEYS` antigas
foram compartilhadas em texto puro durante o desenvolvimento. **Prioridade nº 1
em qualquer trabalho de segurança.**

### P-2 — 6 tabelas sem RLS, expostas pela chave anon 🔴

`metricas_lichess_partida`, `tempos_lance`, `anotacoes_pensamento`,
`perguntas_pendentes`, `revisoes_pensamento`, `puzzle_atividade`. A chave `anon`
é pública no bundle do frontend. Habilitar RLS sem policies bloqueia tudo — é
decisão do dono, não correção automática. Detalhes em `BANCO.md`, seção 6.

### P-3 — O gargalo é cumulativo e está congelado em TATICA 🟡

`_identify_bottleneck` em `agente2_analista.py` usa `frequencia_por_categoria`,
calculada sobre **todo o histórico**. A janela recente (`frequencia_tags_recente`,
`RECENT_WINDOW_DAYS = 30`) é calculada e **nunca usada**. Prova: as análises de
06/09 e 07/09 têm contagens idênticas (351/148/112), e as 3 sprints existentes
apontam `TATICA`, `TATICA`, `TATICA`. Enquanto for cumulativo, o sistema é
incapaz de reconhecer melhora.

Junto disso: `fetch_diagnosticos` seleciona `gravidade_cpl` e nunca
`queda_win_percent`, então `D-1` não chega à decisão de gargalo.

### P-4 — O loop adaptativo nunca fechou 🟡

3 sprints prescritas, **0 concluídas, 0 com eficácia medida**. `medir_eficacia.py`
não está em nenhum workflow, apesar de documentação antiga afirmar que rodava no
semanal. Falta também o botão de concluir sprint no dashboard.

### P-5 — 14% das partidas morrem em silêncio 🟡

28 partidas em `falhou` e 2 travadas em `processando`, concentradas entre
28/08 e 09/09 — justamente as mais recentes. `analisar_partidas.py` só busca
`pendente`, então nada é retomado e nenhum alerta é emitido.

### P-6 — 6 scripts existem mas não estão automatizados 🟡

`enriquecer_partidas_lichess.py`, `importar_puzzle_activity.py`,
`importar_anotacoes_lichess.py`, `gerar_resumo_partida.py`,
`gerar_perguntas_pendentes.py`, `medir_eficacia.py`. Consequência direta nos
números da seção 2: 4 linhas de métricas Lichess para 61 partidas, puzzles
parados em 07/09.

### P-7 — Repertório é ponto cego total 🟡

**146 de 146 partidas do Chess.com sem `eco_abertura`** — 77% do corpus. O
vértice ABERTURA do hexágono não tem base real. Existe
`backfill_eco_abertura.py`, nunca executado com sucesso para o Chess.com.

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
contínuo de frontend e backend; autenticação por múltiplas chaves nomeadas.

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

-- o loop fechou?
select count(*) total, count(data_concluida) concluidas, count(eficacia_medida) medidas
from sessoes_treino;
```

```bash
# testes e cobertura do CI
python -m unittest $(find backend -name "test_*.py" | sed 's/\.py$//' | sed 's#/#.#g')
grep -c "backend\." .github/workflows/deploy-backend.yml   # módulos listados no CI
```
