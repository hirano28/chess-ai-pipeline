---
doc: ESTADO.md
escopo: ÚNICO lugar do repositório onde mora estado factual (contagens, status, pendências)
verificado_em: 2026-09-13
como_reverificar: rode as queries da seção 6 e os comandos da seção 1
aviso: número sem data de verificação em qualquer outro documento deve ser tratado como suspeito
---

# Estado verificado — 2026-09-13

Tudo nesta página foi conferido nesta data contra o banco real
(`pmzmershonrqzwbmhaco`), o código e os workflows. Ao mudar qualquer fato aqui,
atualize também a data no cabeçalho.

## 1. Testes e build

| Item | Valor verificado |
|---|---|
| Testes de backend | **326**, todos passando, em 16 módulos |
| Testes de frontend (Vitest) | **72**, todos passando, em 9 arquivos |
| `ng build` de produção | passa; avisa excesso de bundle (~770 kB), conhecido e aceito |

`.github/workflows/deploy-backend.yml` lista os 16 módulos de teste do backend
à mão (incluindo `backend.common.test_notacao_pt`, que já esteve faltando —
regra R8 corrigida). Continua sendo uma lista mantida manualmente: todo módulo
de teste novo precisa ser adicionado lá também.

## 2. Volume de dados

As 6 tabelas raiz (`partidas`, `analises_hexagono`, `sessoes_treino`,
`explicacoes_posicao`, `puzzle_atividade`, `revisao_exercicio_avulso`) têm
`user_id NOT NULL` desde 11/09/2026, com as **900 linhas existentes
backfilladas** para o dono único atual (ver D-14 em `DECISOES.md` e a
pendência P-11 abaixo).

| Tabela | Linhas |
|---|---|
| `partidas` | 215 (02/07/2026 a 11/09/2026); as 215 já têm `abertura_normalizada` preenchida (ver D-12 em `DECISOES.md`) |
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

### P-11 — Fase B do multi-tenant: Auth no frontend + RLS por usuário 🟡

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

**Fase B.3, primeira parte concluída (13/09/2026) — leitura também filtrada
pelo dono real (D-18).** `GET /revisoes-avulsas/recentes`,
`/explicacoes-posicao/recentes` e `/partidas/recentes` passaram a filtrar a
query com `.eq("user_id", resolver_user_id_para_escrita(request))` —
reaproveitando, sem alterar, a mesma função de resolução de identidade de
D-17. RLS não foi tocado: o filtro é na query do backend, suficiente porque
só o backend fala com essas tabelas, sempre com a `service role key` (que
ignora RLS). Testado com 2 contas reais (`teste-d18-conta-a/b`), cada uma
salvando um exercício com sua própria sessão: a listagem de cada conta
devolveu só o próprio item, confirmado por SQL direto que os `user_id`
gravados batem com os UUIDs reais das duas contas. Repetido sem
`Authorization` (só `X-API-Key`): a listagem voltou a mostrar exclusivamente
o histórico sob `DEFAULT_USER_ID`, sem nenhuma das duas linhas de teste —
os dois caminhos continuam isolados um do outro. Contas e linhas de teste
apagadas ao final.

Falta, para o sistema ser multiusuário de verdade (resto da Fase B.3, ainda
não iniciado):

- **`auth.users` está vazia** (0 contas — confirmado em 13/09/2026, depois de
  eu mesmo criar e apagar contas de teste pra validar B.1, a correção de
  paridade, a B.2 e agora a primeira parte da B.3). Por isso a coluna
  `user_id` é `uuid` puro, **sem FK** — a constraint está escrita e comentada
  no fim de `backend/db/user_id_tabelas_raiz.sql`.
- **Migrar os 4 amigos para conta própria.** Enquanto eles só tiverem
  `X-API-Key`, toda leitura e escrita deles continua caindo em
  `DEFAULT_USER_ID` — nem B.2 nem esta parte de B.3 migraram ninguém (nem
  deveriam, ainda). Explicitamente fora do escopo até aqui.
- **Ligar o `authGuard`** nas rotas do dashboard, quando fizer sentido exigir
  login de verdade (agora sem o bloqueio de dado vazio que existia antes).
- **Isolamento por usuário via RLS.** Trocar `using(true)` por
  `user_id = auth.uid()` nas policies de `authenticated` das 6 raízes (as que
  D-16 criou com `using(true)`), e por um `exists` subindo a cadeia de FK nas
  tabelas filhas (D-14 explica por que filha não ganha coluna própria). As
  policies de `anon` provavelmente precisam ser revistas nesse momento
  também — hoje elas continuam dando acesso total a qualquer portador da
  chave pública. D-18 filtrou só a leitura que passa pelo FastAPI; RLS
  continua sem isolamento nenhum.
- **Fim do `DEFAULT_USER_ID` como fallback.** Enquanto ele existir, quem não
  tiver sessão Supabase Auth continua lendo e gravando pro mesmo dono —
  correto enquanto os amigos não migrarem, mas não é o estado final.

Isto **não** resolve P-2 (6 tabelas sem RLS nenhum): as duas coisas se cruzam,
e o certo é tratá-las na mesma passada.

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
