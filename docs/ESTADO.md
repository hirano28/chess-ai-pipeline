---
doc: ESTADO.md
escopo: ÚNICO lugar do repositório onde mora estado factual (contagens, status, pendências)
verificado_em: 2026-09-17
como_reverificar: rode as queries da seção 6 e os comandos da seção 1
aviso: número sem data de verificação em qualquer outro documento deve ser tratado como suspeito
---

# Estado verificado — 2026-09-17

Tudo nesta página foi conferido nesta data contra o banco real
(`pmzmershonrqzwbmhaco`), o código e os workflows. Ao mudar qualquer fato aqui,
atualize também a data no cabeçalho.

## 0. Saúde da automação — confira ANTES de confiar em qualquer número abaixo

`verificado_em: 17/09/2026.` Os três workflows estão verdes, o backend de
produção serve o commit mais recente e a coleta voltou a rodar.

Entre 15/09 e 17/09 nada disso era verdade, e **nenhum documento teria
denunciado**: os testes locais passavam, a suíte estava verde e o `/health`
respondia 200 — enquanto o CI falhava, o backend congelava no D-49 e a coleta
parava. Ver D-61 em `DECISOES.md`.

```bash
gh run list --limit 5                                  # os 3 workflows verdes?
gh issue list --label falha-automacao --state open     # tem que voltar vazio
```

A segunda linha é o canário desde o D-61: qualquer falha ou cancelamento de
workflow abre uma issue com esse rótulo. Issue aberta = automação quebrada,
independentemente do que as seções seguintes digam.

> ### ✅ Incidente de 17/09/2026 — Gemini sem cota (resolvido no mesmo dia)
>
> O projeto do Gemini estourou o teto mensal de gastos (`429 RESOURCE_EXHAUSTED`)
> depois que a recuperação do D-61 processou 29 partidas acumuladas de uma vez.
> O dono subiu o teto em https://ai.studio/spend; as chamadas voltaram a
> responder — confirmado de novo na verificação do D-67, com a consulta ao vivo
> gerada pelo modelo. Se voltar a acontecer: o Stockfish e a estatística seguem
> funcionando, e o que para é tudo que depende do modelo (Agentes 1–3, resumos,
> Laboratório, Explicador, Analisador, consulta ao vivo).

> ### ✅ Incidente de 14/09 a 17/09/2026 — Explicador travado
>
> Desde que o default de `STOCKFISH_SEARCHTIME_MS` virou 0 (commit `1c221c6`,
> 14/09), `analisar_posicao_com_engine` passava `searchtime=0` ao Stockfish, que
> busca sem fim nesse caso. Toda chamada ao Explicador travava **segurando o
> `engine_lock`**, o que também fazia Treino, trecho e Laboratório esperarem 60 s
> e responderem 503 enquanto isso. A última explicação gravada é de 11/09.
> Ninguém notou porque o dublê de teste aceitava qualquer `searchtime`. Achado
> ao verificar o D-67, que reaproveita a mesma função; corrigido em `1e47cbf`.

## 1. Testes e build

| Item | Valor verificado |
|---|---|
| Testes de backend | **958**, todos passando, em 43 módulos |
| Testes de frontend (Vitest) | **322**, todos passando, em 35 arquivos |
| `ng build` de produção | passa com **0 warnings e 0 erros**; bundle inicial ~10.73 kB (D-44), CSS 42,4 kB cru / 7,5 kB transferido após o sistema de design (D-47) |

`.github/workflows/deploy-backend.yml` lista os **37** módulos de teste do
backend à mão, e em 16/09/2026 a lista do CI batia exatamente com os 37
arquivos `test_*.py` em disco — regra R8 cumprida. A enumeração nominal que
ficava aqui foi removida na revisão de documentação de 16/09/2026: ela
envelhecia a cada módulo novo (chegou a listar 35 quando já eram 37) e
duplicava uma lista que já existe em dois lugares mantidos à mão. O jeito
certo de conferir é comparar os dois números, não ler nomes:

```bash
find backend -name "test_*.py" | wc -l                                # 37
grep -cE "^\s+backend\..*test_" .github/workflows/deploy-backend.yml  # 37
```

Divergiu? O módulo novo entrou em disco e não no CI — o teste existe, passa
localmente e **nunca roda no CI**. Foi o que aconteceu com
`backend.common.test_notacao_pt`, e é a razão de a R8 existir.

## 2. Volume de dados

As 6 tabelas raiz (`partidas`, `analises_hexagono`, `sessoes_treino`,
`explicacoes_posicao`, `puzzle_atividade`, `revisao_exercicio_avulso`) têm
`user_id NOT NULL` desde 11/09/2026, com as **900 linhas existentes
backfilladas** para o dono único atual (ver D-14 em `DECISOES.md` e a
pendência P-11 abaixo).

| Tabela | Linhas |
|---|---|
| `partidas` | **269** (02/07/2026 a 16/09/2026); **269 `concluido`, 0 `falhou`**. As duas `variant: fromPosition` que o D-62 desmascarou foram analisadas de verdade pelo D-63 (a trava de variante as recusava; "From Position" é xadrez padrão a partir de uma posição própria) — uma rendeu 4 lances críticos, a outra nenhum, o que é legítimo numa partida de 8 lances. 230 com `abertura_normalizada`; **268 das 269 com cadência real** desde o D-62, a única exceção sendo um PGN colado à mão |
| `lances_criticos` | **806** — 700 `PICO` e 106 `EROSAO`. Até o D-65 as erosões não tinham formato de treino e ficavam paradas; desde o D-66 entram na fila como "Refazer o trecho" |
| `diagnosticos` | **802** — paridade total com `lances_criticos`, nenhum lance sem diagnóstico |
| `perguntas_pendentes` | 6, **todas ainda `PENDENTE` e nenhuma respondida desde que o recurso existe**, todas de partidas de 10 dias atrás. Com o prazo de validade do D-64 (14 dias contados da PARTIDA) elas expiram sozinhas em 4 dias, virando `EXPIRADA` em vez de sumirem |
| `perfis_usuario` | 2 (o dono do acervo + uma conta sem partida ingerida). É a tabela que prova que o multi-tenant do D-28 não é hipótese |
| `puzzle_atividade` | 660, em 41 dias distintos |
| `tempos_lance` | 16.161, cobrindo 228 partidas (4.847 do Lichess + 11.314 do Chess.com via backfill D-43) |
| `livros_chunks` | 2092 (1621 anteriores + 244 de "Arte do Ataque no Xadrez", Vukovic, D-78 — só RAG vetorial — + 227 de "The Complete Manual of Positional Chess Vol 1", Sakaev/Landa, D-78) |
| `indice_conceitual` | 370 (274 anteriores + 96 de "The Complete Manual of Positional Chess Vol 1", D-78) |
| `anotacoes_pensamento` | 23, cobrindo 3 partidas |
| `revisoes_pensamento` | 23, todas em 1 único dia |
| `revisao_exercicio_avulso` | 17 |
| `explicacoes_posicao` | 7 (tabela nova, ver D-11 em `DECISOES.md`) |
| `metricas_lichess_partida` | 18, para 67 partidas do Lichess; 14 já têm `precisao_abertura`/`precisao_meiojogo` preenchidas e 12 têm `precisao_final` — colunas novas (ver `BANCO.md`) sendo preenchidas prospectivamente pelo pipeline automatizado (D-37), sem reprocessamento retroativo das linhas mais antigas |
| `analises_hexagono` | **7** — as 2 mais recentes (17/09/2026, D-63) são as primeiras com `metricas.por_cadencia`, e foram gravadas **sem narrativa** por causa do incidente do Gemini (seção 0). Dono principal: gargalo do conjunto TATICA, em blitz TATICA, em rápidas **CALCULO** — o gargalo muda com a cadência |
| `sessoes_treino` | 5 prescritas, **0 concluídas**, 0 com eficácia medida. A validação do D-54 concluiu uma sessão de verdade (5/0/0 → 5/1/0, a primeira da história do produto) e **foi revertida de propósito**: aquele treino não aconteceu — os 12 exercícios foram respondidos por script, com lances quaisquer. Deixar a marca produziria a primeira medição de eficácia do produto em cima de um treino inexistente. O caminho está validado; o número volta a subir quando houver sessão real |
| `resumo_partida` | **258** |
| `fila_treino_espacado` | **716** — 658 do dono principal (agendada até 17/11) e 58 do segundo perfil (até 29/09). **16 são cards de trecho (EROSAO, D-66)**: 15 entraram na primeira execução da população com o recurso, todos no segundo perfil, espalhados pela cota de 2 por dia (22/09 a 29/09); o dono principal não recebeu nenhum porque a fila dele está cheia até o horizonte ("fila cheia até 18/11"), e o 16º é o card de verificação inserido à mão para ele. A válvula do D-64 continua em vigor. **712 dos 716 nunca foram respondidos** — o gargalo real do recurso não é o tamanho da fila, é o hábito de responder |
| `exercicios_taticos` | 1.200 (D-49); 300 por categoria em `TATICA`/`CALCULO`/`FINAIS`/`ESTRUTURA_DE_PEOES` — `ESTRATEGIA`/`GESTAO_DE_TEMPO` seguem sem cobertura AQUI, e é esperado: não existe tema de puzzle equivalente |
| `exercicios_posicionais` | **2.381** (tabela nova, D-55), de **1.764 partidas OTB em 510 torneios** distintos (broadcasts do Lichess, maio a agosto/2026), 451 delas com um GM; ~594 em cada uma de `ESTRATEGIA`/`GESTAO_DE_TEMPO`/`FINAIS`/`ESTRUTURA_DE_PEOES`. A primeira leva do D-55 tinha 1.200 exercícios de só **69 torneios**, quase todos do mesmo dia — a amostragem por reservatório do D-58 é o que multiplicou a variedade por 7 |
| **Catálogo somado, por categoria** | `TATICA` 300, `CALCULO` 300, `ESTRATEGIA` 593, `GESTAO_DE_TEMPO` 600, `FINAIS` 894, `ESTRUTURA_DE_PEOES` 894 — **as 6 categorias do Hexágono têm material pela primeira vez** (fecha o P-15) |

## 3. Composição do corpus — dado que muda a leitura de tudo

`verificado_em: 17/09/2026`, pela coluna `partidas.cadencia` (D-57), **depois
da correção de ingestão do D-62**.

| Cadência | Corpus inteiro | Dono principal (`tantofaz123`) |
|---|---|---|
| BLITZ | 187 | 180 |
| RAPIDA | 78 | 68 |
| CLASSICA | 3 | **0** |
| DESCONHECIDA | 1 | 1 |
| **Total** | **269** | **249** |

**As duas colunas existem porque o produto é multiusuário.** O acervo tem dois
donos: `tantofaz123`/`edinho230` (249 partidas) e `Gazola` (20). O Hexágono e
`GET /partidas/composicao` filtram por dono, então quem olha a tela vê a coluna
da direita — 72,3% blitz, não 69,5%. Somar os dois só faz sentido para falar do
banco, nunca para falar do jogador.

**As 3 partidas clássicas que o D-62 revelou são do `Gazola`.** O dono
principal continua sem nenhuma partida clássica no acervo, o que mantém de pé a
ressalva de sempre sobre o diagnóstico dele.

A ressalva que o Hexágono exibe acima do diagnóstico sai daqui, calculada ao
vivo e por dono.

> **O que estes números eram até 17/09/2026, e por quê.** A tabela dizia BLITZ
> 142 / DESCONHECIDA 68 / RAPIDA 30, com o texto afirmando que **não havia
> nenhuma partida clássica no acervo**. As três afirmações estavam
> contaminadas pela nossa própria coleta: `build_pgn()` reconstruía o PGN do
> Lichess sem o header `TimeControl`, então 100% das partidas de lá caíam em
> DESCONHECIDA. Corrigida a ingestão e rebuscados os 87 PGNs oficiais
> (`backfill_pgn_lichess.py`), apareceram **3 partidas clássicas** — do
> `Gazola`, não do dono principal — e a contagem de rápidas mais que dobrou.
>
> Repare na direção: o viés de blitz **aumentou**, de 59% para 69,5% no corpus
> e 72,3% na tela do dono principal. A correção não melhorou o retrato,
> tornou-o honesto — e esse é o ponto. Ver D-62 em `DECISOES.md`.

A única `DESCONHECIDA` restante é um PGN colado à mão (`plataforma = MANUAL`),
sem fonte de onde rebuscar cabeçalho. Qualquer conclusão sobre "o gargalo do
jogador" continua misturada com o efeito do relógio; a diferença desde o D-57 é
que agora **dá para filtrar**. A tag mais frequente é
`calculo_tatico_deficiente` (29,8% de todas as tags), o que é esperado a ~2
segundos por lance.

**Duas partidas `From Position` foram desmascaradas no caminho** (D-62): a
reconstrução antiga as gravava a partir da posição inicial padrão, e uma delas
constava como `concluido` tendo sido analisada com **um único lance**. As duas
agora estão em `falhou`, recusadas pelo motor com "variante não padrão" — que é
a resposta certa. São as 2 do total de 269 que não entram em nenhuma
estatística de diagnóstico.

**Resolvido em 17/09/2026 (D-63):** o Agente 2 passou a gravar, dentro do
mesmo `metricas` jsonb, um hexágono por cadência (`por_cadencia`), e a tela `/`
ganhou um seletor Todas / Blitz / Rápida que redesenha o radar e avisa quando o
gargalo do recorte é outro que o do conjunto. As 5 análises anteriores não
precisaram de backfill: sem a chave, a tela mostra só o total. O que **ainda**
segue em aberto, de propósito: a sprint do Agente 3 continua prescrita a partir
do gargalo do conjunto — fazê-la seguir uma cadência é decisão de produto
("treinar para qual cadência?"), não de cálculo.

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

### P-15 — Duas categorias do Hexágono sem exercício de catálogo ✅ RESOLVIDA em 16/09/2026

`verificado_em: 16/09/2026` (consulta direta aos dois catálogos no projeto
`pmzmershonrqzwbmhaco` + chamada real a `POST /treino/foco/ESTRATEGIA` e
`POST /treino/foco/GESTAO_DE_TEMPO`, que agora devolvem `adicionados: 8`).

Era o buraco de conteúdo: metade da taxonomia do produto não tinha treino
focado. `ESTRATEGIA` e `GESTAO_DE_TEMPO` ficaram em 0 exercícios porque a
única fonte era o dump de puzzles do Lichess, e **puzzle é tática por
construção** — não existe tema que signifique estratégia, e posição de puzzle
não tem relógio. Duas tentativas anteriores trataram só o sintoma de
interface (D-52 explicou depois do clique; D-53 removeu o botão).

Resolvido pelo **D-55**, com outra fonte: o banco de broadcasts do Lichess
(partidas OTB reais, com `[%eval]` e `[%clk]` em todo lance). O filtro exige
que o melhor lance seja quieto, o que produz material genuinamente posicional;
e o relógio do PGN dá a `GESTAO_DE_TEMPO` exercícios cronometrados com o tempo
que o jogador realmente tinha. **As 6 categorias têm material** — ver a tabela
de volume na seção 2.

O que foi recusado e continua recusado: remapear temas de puzzle para
`ESTRATEGIA`. `quietMove` e `defensiveMove` são os mais próximos e ainda assim
descrevem um lance dentro de uma sequência tática; usá-los seria reetiquetar
tática como estratégia — a mesma cobertura fingida que o D-49 recusou.

### P-1 — Chaves de API expostas, rotação nunca feita 🔴

`GEMINI_API_KEY` e `SUPABASE_SERVICE_ROLE_KEY` foram compartilhadas em texto
puro durante o desenvolvimento (as antigas `API_SECRET_KEYS` também foram,
mas essa variável foi removida numa auditoria pós-D-49 — não há mais nada
pra rotacionar ali, só apagar do `.env`/GitHub Secrets se ainda estiver
configurada em algum lugar). **Prioridade nº 1 em qualquer trabalho de
segurança.** Runbook de rotação (confirmado por auditoria): `GEMINI_API_KEY`
é lida em 9 arquivos + 3 workflows; `SUPABASE_SERVICE_ROLE_KEY` em ~20
arquivos + 3 workflows (praticamente todo script do pipeline). Rotação
concreta: gerar a nova chave no console do provedor (Google AI Studio /
Supabase Dashboard), atualizar `.env` local + os GitHub Secrets usados por
`deploy-backend.yml`, rodar o workflow (o `--env-vars-file` substitui o
Cloud Run por completo, D-20, nada fica órfão). Vercel não entra: o
frontend só guarda a chave `anon` pública do Supabase, não essas duas.

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

### P-4 — O loop adaptativo nunca fechou ✅ RESOLVIDA em 14/09/2026 (D-37 e D-38)

O ciclo completo foi fechado:
1. **Backend:** `medir_eficacia.py` automatizado no `pipeline-semanal.yml` com isolamento multi-tenant (D-37), calculando a redução percentual de falhas na janela de 15 dias pós-treino.
2. **Frontend:** `SessoesTreinoComponent` e `SupabaseService` atualizados (D-38) com métricas de resumo (prescritas, concluídas, eficácia média), ação de concluir sprint, opção de desmarcar/reabrir e exibição do impacto na frequência de falhas com observações (ou aviso de espera da janela pós-treino).

### P-5 — 14% das partidas morrem em silêncio ✅ RESOLVIDA em 14/09/2026 (D-39)

Todas as 31 partidas retidas (28 `falhou` e 3 `processando`) mais 2 pendentes (33 no total) foram reprocessadas e recuperadas com 100% de sucesso (0 falhas). A causa raiz (`STOCKFISH_SEARCHTIME_MS = 3_000` forçando >5 minutos por partida) foi sanada com o padrão `searchtime=0` (avaliando a `depth=16` em ~0.12s por lance). `analisar_partidas.py` agora recupera automaticamente partidas órfãs em `processando`, suporta `--reprocessar-falhas` e `--partida-id`, com deleção limpa de tabelas dependentes (Regra R7). O status atual do corpus é 230 partidas concluídas, 0 em falhou, 0 em processando, 0 pendentes, e o total de lances críticos subiu para 685.

### P-6 — 6 scripts existem mas não estão automatizados ✅ 5 automatizados em 14/09/2026 (D-37)

5 dos 6 scripts foram automatizados nos workflows do GitHub Actions:
- `pipeline-diario.yml`: `importar_puzzle_activity.py` (puzzles via OAuth), `enriquecer_partidas_lichess.py` (clocks e fases), `gerar_perguntas_pendentes.py` (perguntas reflexivas) e `gerar_resumo_partida.py` (narrativas).
- `pipeline-semanal.yml`: `medir_eficacia.py` (agora com isolamento multi-tenant).

Apenas `importar_anotacoes_lichess.py` permanece manual por depender do escopo OAuth `study:write` (fora do escopo atual).

### P-7 — Repertório é ponto cego total ✅ RESOLVIDA em 14/09/2026 (D-40)

O ponto cego foi completamente sanado em duas frentes:
1. `coletar_partidas_chesscom.py` passou a extrair o código ECO padrão internacional diretamente do cabeçalho PGN (`[ECO "..."]`). O script `backfill_eco_abertura.py` foi executado contra o banco e atualizou 153/153 partidas do Chess.com (100%) com seus respectivos códigos ECO.
2. Criados o serviço (`RepertorioService`) e o componente de interface (`RepertorioInsightsComponent`) no frontend, exibindo taxa de vitória de Brancas vs Pretas, filtro por cor, momento médio de erro crítico (lance de pico) e categorias vulneráveis do hexágono por abertura.

### P-8 — Ferramentas interativas sem hábito de uso (Aproveitamento de Puzzles) ✅ RESOLVIDA em 14/09/2026 (D-41)

O hábito consistente de puzzles (660 puzzles em 41 dias distintos) foi plenamente incorporado ao pipeline analítico:
1. Módulo analítico puro `backend/agentes/insights_puzzles.py` calcula estatísticas gerais (taxa global de 70.3%, rating médio de 1.854), mapeia e traduz temas do Lichess para português, separa vulnerabilidades (<55% de acerto: lances defensivos 45.2%, desvio 48.5%, lances silenciosos 53.8%) e pontos fortes (>70%: mates curtos, ataques na ala do rei), formulando um diagnóstico comparativo profundo do "Gap Tático" (cálculo calmo vs decisões sob pressão de tempo em blitz).
2. Endpoint autenticado `GET /insights/puzzles` exposto no backend (`backend/api/api_server.py`) com isolamento multi-tenant (D-30).
3. Criados `PuzzlesService` e o componente visual `PuzzlesInsightsComponent` integrado ao dashboard, fornecendo cards de métricas, diagnóstico narrativo do Gap Tático, temas vulneráveis com barra de progresso e links diretos de treino no Lichess (`https://lichess.org/training/{slug}`), além de badges para pontos fortes dominados.

### P-9 — Pendências menores 🟢

`verificado_em: 17/09/2026.` **Duas foram fechadas nesta data:**

- ✅ **FK `fila_treino_espacado.posicional_id` sem índice.** O D-55 criou a
  coluna mas não o índice que as outras duas origens de card ganharam em
  `indices_fk_faltantes.sql`. A unique `(user_id, posicional_id)` não cobria:
  índice composto só serve a busca que começa pela primeira coluna, e a
  checagem de FK filtra por `posicional_id` puro. Resolvido por
  `backend/db/indice_fk_posicional_id.sql`; o advisor de performance do
  Supabase parou de apontar `unindexed_foreign_keys`.
- ✅ **`sessao.service.ts` sem spec.** Era o serviço mais novo (D-54) e o único
  sem teste. 9 casos, cobrindo inclusive dois que só aparecem em uso real: o
  bloco de índice `0` (valor falsy que é índice válido) e o 404 de sessão de
  outro dono, que **não** pode ser tratado como "sessão expirada" — mandaria o
  usuário relogar para resolver o que não é problema de autenticação.

Seguem em aberto:

- Livro "How to Calculate Chess Tactics" (inglês): pipeline adaptado em D-44 com
  parâmetro `--ocr-lang eng`, cache diferenciado por idioma e detecção de capítulos
  em inglês (`CHAPTER`, `PART`, `SECTION`).
- Projeto GCP `chess-ai-pipeline`, criado por engano, pode ainda existir.
  Verifique com `gcloud projects list` e delete se estiver lá. O projeto correto
  é `gen-lang-client-0828609060`.
- **Proteção contra senha vazada (Supabase Auth) desligada.** O advisor de
  segurança do Supabase aponta `auth_leaked_password_protection` como
  desabilitado (checagem contra HaveIBeenPwned no cadastro/login). Risco
  baixo dado o modelo de ameaça do projeto (conta única + alguns amigos via
  chave nomeada, ver AGENTS.md), mas é um toggle de ~1 minuto no Dashboard
  (Authentication → Policies → Password) que nenhuma ferramenta MCP
  disponível nesta sessão conseguia acionar — fica registrado para quem
  tiver acesso ao Dashboard ligar quando quiser.

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

> **Leia como registro histórico, fase por fase.** Cada parágrafo abaixo está
> datado e descreve o estado **daquele dia**, incluindo estados transitórios que
> já foram superados. Duas frases em particular não valem mais: o `authGuard`
> "não usa o guard em nenhuma rota" (B.1, 12/09) e "`X-API-Key` continua sendo
> exigida" (B.2, 13/09). Hoje o guard está nas 7 rotas do dashboard e o
> `X-API-Key` não existe mais no código — ver a seção 5 e `ARQUITETURA.md` §5.

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
- ✅ **`API_SECRET_KEYS`/`API_SECRET_KEY` removidas de vez (auditoria de
  segurança/operação pós-D-49).** Eram gate de acesso aposentado desde D-25;
  o código morto (`verificar_api_key`, `_resolver_api_keys()`, `_parse_api_keys`
  e a exigência da variável no startup) foi deletado — o achado da auditoria
  foi que essa exigência ainda **derrubava o boot** do servidor sem a
  variável configurada, um risco de disponibilidade real amarrado a uma
  feature morta. `deploy-backend.yml` (D-20) não propaga mais
  `API_SECRET_KEYS` como secret obrigatório. `DEFAULT_USER_ID` não foi
  tocada: continua sendo o dono gravado pelos scripts de CLI standalone, que
  não passam pela API.

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
futura, mesma categoria de pendência não bloqueante que `API_SECRET_KEYS`
foi até ser resolvida numa auditoria pós-D-49 (ver acima). As duas variáveis
continuam vivas no `.env` só para quem roda `analisar_pgn_avulso.py` direto
no terminal.

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

**Treino Diário — repetição espaçada (15/09/2026, D-48).** Maior gap do
produto contra o mercado (pesquisa de concorrentes: Aimchess, Chess DNA,
Chessy, Backrank.io, Blunders.ai, Noctie.ai) era diagnosticar sem virar
treino ativo. Tabela nova `fila_treino_espacado` (SM-2 simplificado),
script `popular_fila_treino_espacado.py` (roda depois do Agente 1 no
pipeline diário) e 2 endpoints (`GET /treino/fila`, `POST
/treino/{id}/responder`) reaproveitando a avaliação de lance já existente em
`revisar_exercicio_avulso.py` — sem chamar Gemini no card de revisão, de
propósito (decisão de escopo confirmada com o usuário). Validado contra a
conta real do Edson: 632 dos 714 diagnósticos existentes eram elegíveis
(`PICO` com `fen_antes_lance`), escalonados em 64 dias a 10 novos/dia;
servidor real respondeu um card de verdade (Stockfish real, sem mock),
classificou `BOM`, revelou a citação do livro e reagendou corretamente; 2ª
conta de teste confirmou isolamento por dono (404, nunca 403, mesmo padrão
de D-29/D-30).

**Catálogo de exercícios táticos + Treino Focado (15-16/09/2026, D-49).**
Fecha a lacuna do D-48 pra quem ainda não errou o suficiente numa categoria:
tabela nova `exercicios_taticos` (catálogo global, sem `user_id`) importada
do dump público de puzzles do Lichess (`backend/rag/
importar_exercicios_taticos.py`, import ocasional, não roda no pipeline
diário) e re-taggeada em `HEXAGON_CATEGORIES`. `fila_treino_espacado` passou
a aceitar uma segunda origem (`exercicio_tatico`, `exercicio_id` com `on
delete restrict`); novo endpoint `POST /treino/foco/{categoria}` injeta
exercícios na fila de hoje quando o usuário clica "Focar" no Hexágono — o
mesmo motor SM-2 e os mesmos `GET /treino/fila`/`POST /treino/{id}/
responder` do D-48 atendem as duas origens. Achado honesto: só `TATICA`,
`CALCULO`, `FINAIS` e `ESTRUTURA_DE_PEOES` têm exercícios de catálogo —
`ESTRATEGIA` e `GESTAO_DE_TEMPO` não têm tema equivalente no Lichess.
Validado com a conta real do Edson: import real trouxe 1.200 exercícios
(300/categoria, idempotente na 2ª execução), `POST /treino/foco/TATICA`
adicionou 8 exercícios reais, `GET /treino/fila` misturou as duas origens
sem vazar diagnóstico, e `POST /treino/{id}/responder` avaliou via Stockfish
real, classificou `BOM` e reagendou corretamente. **Não verificado:** o
clique manual em "Focar" no navegador — sem ferramenta de automação de
navegador disponível nesta sessão e sem servidor de dev acessível na porta
local; pendente de confirmação humana.

**Auditoria de qualidade — backend, segurança/operação, frontend
(16/09/2026, D-50).** A pedido explícito do usuário, consolidar em vez de
trazer recurso novo: 3 auditorias paralelas (backend/confiabilidade,
segurança/operação, frontend/UX) seguidas da implementação de tudo que era
corrigível diretamente. Fechou um buraco real de custo (`/reprocessar` sem
limite diário), um risco de disponibilidade (boot dependia de uma variável
de uma feature morta desde D-25), 22 policies de RLS reescritas e 4 índices
de FK criados no Supabase, uma função órfã removida do banco (achado que
nem estava documentado em nenhum `.sql` do repo), 18 `load_settings()`
duplicados consolidados num helper só, e 3 achados de UX no frontend
(estado de erro ausente no histórico compartilhado, empty state do
Hexágono renderizado como erro, cores do gráfico hardcoded). Testes: 583 →
**600** no backend, 151 → **171** no frontend, zero regressão. **Não
resolvido** (fora do alcance das ferramentas desta sessão): rotação de
verdade de `GEMINI_API_KEY`/`SUPABASE_SERVICE_ROLE_KEY` (exige acesso a
consoles externos, ver P-1) e o toggle de proteção contra senha vazada no
Dashboard do Supabase Auth (ver P-9).

**Miniaturas de posição nos resumos e históricos (16/09/2026, D-51).** Os
históricos das 3 telas interativas e os cards de ponto crítico do Analisador
passaram a mostrar uma miniatura do tabuleiro, para dar de bater o olho e
reconhecer de qual partida/análise/exercício a linha está falando. O
componente `tabuleiro-preview` já tinha o modo `[miniatura]` desde o D-45 e
estava sendo usado em só duas telas. Duas fontes de FEN eram novas: a
posição final da partida (reconstruída do PGN que a query do histórico já
buscava) e a posição de cada ponto crítico (junção com
`lances_criticos.fen_antes_lance` feita **na leitura** do resumo, não na
geração — por isso vale retroativamente, sem reprocessar nada; conferido
antes de implementar que 423/423 dos pontos críticos já existentes no banco
têm FEN correspondente). Verificado de verdade contra o servidor local com
sessão real: 12/12 partidas manuais devolveram `fen_final` válido e os 4
pontos críticos de uma partida real vieram todos com FEN. Testes: 600 →
**604** no backend, 171 → **179** no frontend. **Pendente de conferência
humana:** o visual em si no navegador (tamanho/legibilidade da miniatura na
linha, card de ponto crítico em tela estreita).

**Auditoria de UX e acessibilidade da aplicação inteira (16/09/2026, D-52).**
Varredura das 15 telas + `styles.css` + casca do app. O achado grave foi o
botão "Focar" do Hexágono descartando o retorno de `focarCategoria()` e
navegando para `/treino` em qualquer caso — inclusive nas duas categorias que
não têm exercício nenhum (ver P-15) e em erro de sessão. Também corrigidos:
rótulos crus (`ESTRUTURA_DE_PEOES`) no radar, modal sem Esc/scrim/foco
inicial, miniatura de tabuleiro despejando 32 `alt="wR"` em leitor de tela,
"Desconectar" e "Reiniciar análise" sem confirmação, ausência de link "pular
para o conteúdo", login sem mostrar-senha e sem dizer por que o botão está
desabilitado, `100vh` no lugar de `100dvh`. Testes: 604 → **606** no backend,
179 → **199** no frontend.

**A conferência visual foi feita de verdade**, com Playwright instalado fora
do projeto (ver "Verificação visual" na seção 6): 14 telas fotografadas em
1440px e 390px, com backend local e sessão real. Três defeitos só apareceram
olhando — o mais grave é que **a narrativa do Agente 2 exibia markdown cru**
(`**Tática**` com os asteriscos à mostra) nas duas telas que a renderizam,
comportamento que está em produção hoje. Também corrigidos ali: cartões de
ponto crítico espremidos no desktop pela miniatura do D-51, e navegação no
celular escondendo "Analisador"/"Perfil" sem pista de rolagem.

**A sessão de treino passou a ser executada (16/09/2026, D-54).** Achado que
motivou tudo: 5 sessões prescritas, **0 concluídas, 0 com eficácia medida** —
`medir_eficacia.py` só olha sessões com `data_concluida`, então o loop
adaptativo do produto nunca fechou uma única vez. A sessão era texto com um
botão manual que ninguém aperta. Agora tem tela própria (`/sessao/:id`) com
blocos de estudo (os módulos do Agente 3, preservados) e um bloco de prática
montado pelo backend com exercícios reais; a sessão **conclui sozinha** no
último bloco. Validado ponta a ponta contra o banco real, com o contador indo
de 5/0/0 para 5/1/0. Dois defeitos só apareceram rodando: o endpoint de
disponibilidade reportava 120/280 onde havia 300/300 (teto de 1000 linhas do
PostgREST, errado em silêncio) e o bloco de prática dizia "nenhum exercícios"
antes de a sessão abrir. Testes: 611 → **628** no backend, 206 → **216** no
frontend.

**Exercícios posicionais de partidas OTB reais (16/09/2026, D-55).** Fecha o
P-15 com uma fonte nova: o banco de broadcasts do Lichess (1,2 milhão de
partidas de torneio, com `[%eval]` e `[%clk]` em todo lance e a anotação do
próprio Lichess dizendo onde alguém errou). O filtro exige **melhor lance
quieto**, o que produz material genuinamente posicional para `ESTRATEGIA`; o
relógio do PGN dá a `GESTAO_DE_TEMPO` exercícios cronometrados com o tempo que
o jogador tinha, e estourar o cronômetro rebaixa o agendamento SM-2 de
verdade. A primeira execução real trouxe 1200 exercícios de um único dia de
opens juvenis — daí o filtro `POSICIONAL_EXIGIR_TITULO`, que na reimportação
rendeu 616 partidas em 69 torneios com GM/IM/WGM. Licença: broadcasts são CC
BY-SA 4.0 (os puzzles do D-49 são CC0), então a procedência é exibida depois
da resposta. Testes: 628 → **687** no backend, 216 → **223** no frontend.

**A fila ganhou teto e a sessão ganhou atalho (16/09/2026, D-56).** O D-55
acrescentou 1200 exercícios a um sistema cujo gargalo não era falta de
material: a fila cresce 10 cards/dia venha alguém respondê-los ou não, e o
bloco de prática da sessão caía no fim dela — o botão "Ir para os exercícios"
levava a uma tela onde os 12 cards da sessão ficavam atrás de dezenas de
outros. Agora `GET /treino/fila?sessao_id=` filtra pela sessão, e
`TREINO_TETO_FILA` (20) limita o que a tela mostra **sem** esconder o tamanho
do atraso (`vencidos_total`).

**Cadência das partidas (16/09/2026, D-57).** A maior ressalva do produto
saiu da documentação para a tela. `partidas` ganhou `cadencia`/
`tempo_base_segundos`/`incremento_segundos`, o acervo inteiro foi backfillado
(240 partidas: 142 blitz, 30 rápidas, 68 sem header) e o Hexágono passou a
exibir, acima do diagnóstico, que 59% do corpus é blitz e que o gargalo lido
ali carrega junto o efeito do relógio. **Ainda falta** filtrar o próprio
Hexágono por cadência — ver a ressalva no fim do D-57.

**Caminho da medição de eficácia validado (16/09/2026).** Com uma sessão
concluída, `medir_eficacia.py` rodou pela primeira vez com trabalho real:
encontrou a sessão elegível, extraiu a categoria do `diagnostico_gargalo` e
reportou corretamente "aguardando mais dados pós-treino (0/3 diagnósticos)".
O caminho funciona ponta a ponta; ele exige 3 diagnósticos da categoria na
janela de 15 dias após a conclusão. A sessão de teste foi revertida depois
(ver a linha de `sessoes_treino` na seção 2).

**Catálogo posicional reamostrado e títulos limpos (16/09/2026, D-58/D-59).**
O import passou a ler o mês inteiro e sortear por reservatório, em vez de
aceitar os primeiros N e parar — a primeira leva vinha toda de um único dia.
Reimportado sobre 3 meses (125.974 partidas lidas): a variedade foi de **69
para 510 torneios distintos**, e de 616 para 1.764 partidas.
E 7 linhas de `indice_conceitual` com sujeira de OCR (`| OJOGO CONTRA A. A
PEÇA C CRAVADA`), que apareciam na tela como citação de fonte, foram
corrigidas; o import agora limpa as pontas sozinho.

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
Agentes 1, 2 e 3; RAG com 7 livros/materiais processados ("Meu Sistema" de
Nimzowitsch, "Xadrez Vitorioso: Táticas" de Seirawan/Silman, "How to Reassess
Your Chess" de Jeremy Silman, "How to Calculate Chess Tactics" de Valeri Beim
(D-72), dois materiais curtos sobre estrutura de peões — aula da FEXPAR
(Bolívar Gonzalez) e slides do Xadrez Escolar (Frederico Gazel), D-73 — que
reforçam a busca vetorial mas ainda não geraram citação em
`indice_conceitual` por não terem capítulo detectável, e "Segredos da
Moderna Estratégia" de John Watson (D-74, 380 chunks, 58 conceitos);
`buscar_conceitos()` (`agente3_prescritor.py`) agora normaliza acento e
underscore antes de comparar (D-75) — a busca de citação por categoria do
Hexágono deixou de ignorar conceitos salvos em formato de tag
(`fraqueza_estrutural_de_peoes`), destravando conceitos que já estavam no
banco desde antes: TATICA 8→38, ESTRATEGIA 11→36, CALCULO 14→32 (FINAIS e
GESTAO_DE_TEMPO inalterados, ESTRUTURA_DE_PEOES continua em 4 — ver D-75);
e "Los 100 Finales que Hay que Saber" de Jesús de la Villa (D-76, 167
chunks só na busca vetorial — o livro nomeia finais como "Final 71. ..."
em vez de capítulo, então não gerou citação nova em `indice_conceitual`),
mais "Understanding Chess Endgames" de John Nunn (D-77, 267 chunks, mesmo
tratamento — organizado por final numerado, sem capítulo detectável),
"Arte do Ataque no Xadrez" de Vukovic (D-78, 244 chunks só na busca
vetorial — sumário e corpo usam formatos de capítulo inconsistentes entre
si) e "The Complete Manual of Positional Chess Vol 1" de Sakaev/Landa
(D-78, 227 chunks, 96 conceitos, 30 capítulos com título real conferido
manualmente página a página antes da sugestão de conceito);
Laboratório de Raciocínio com notação PT/EN, reconhecimento de posição por foto, preview do tabuleiro e
histórico navegável dos exercícios salvos; Explicador de Posição com
persistência automática e histórico navegável; Analisador de Partida com
histórico e reprocessamento; as 3 telas interativas compartilham o mesmo
componente de histórico (`historico-analise`) e o mesmo padrão de
sobrevivência a F5 via `localStorage` (ver D-11 em `DECISOES.md`); deploy
contínuo de frontend e backend; autenticação **só** por sessão do Supabase Auth
(`Authorization: Bearer`) — a frase "autenticação por múltiplas chaves nomeadas"
que ficava aqui descrevia o `X-API-Key`, aposentado como porta de entrada em
D-25 e removido do código numa auditoria pós-D-49;
`abertura_normalizada` preenchida para 230 das 240 partidas e captura de
precisão por fase (`precisao_abertura`/`precisao_meiojogo`/`precisao_final`)
daqui pra frente no enriquecimento Lichess (ver D-12 em `DECISOES.md`);
`GET /insights/repertorio` já consome isso (D-13) e cruza com resultado, lance
de PICO e categoria do hexágono por abertura — testado contra o banco de
produção em 11/09/2026, ver a distribuição da Francesa na seção 3. Consumido
pelo frontend desde D-40 (`RepertorioInsightsComponent`).

**Login (Fase B.1, 12/09/2026), paridade RLS (13/09/2026) e identidade real
nas escritas (Fase B.2, 13/09/2026) funcionam de ponta a ponta.** Cadastro,
confirmação de e-mail, login, logout e restauração de sessão num F5 foram
testados com uma conta real e zero erro de console. O achado de B.1 (logar
esvaziava o dashboard) foi corrigido em D-16: o conteúdo do "Meu Hexágono"
agora é idêntico entre anônimo e autenticado, confirmado caractere a
caractere e via `curl` direto no PostgREST com o JWT real. Uma análise real
no Laboratório (Stockfish + Gemini, não mock), salva estando logado, grava
com o `user_id` real da conta (D-17); a mesma ação sem sessão continua
gravando `DEFAULT_USER_ID`, como sempre. `authGuard` está ligado nas **7 rotas**
do dashboard desde D-23 (Fase B efetivamente concluída; `/treino` somou-se às 5
originais em D-48 e `/sessao/:id` em D-54) — a frase acima sobre
"deliberadamente desligado" descrevia só o estado transitório de B.1
(12/09/2026) e ficou desatualizada quando B foi fechada no dia seguinte; ver
`app.routes.ts`.

**A metade de treino também está validada de ponta a ponta** (D-48 a D-59,
setembro/2026), e é o que o texto acima, escrito antes dela, não cobria:

- **Fila diária de repetição espaçada** (`/treino`, D-48) sobre os próprios
  lances `PICO` já diagnosticados, com SM-2 real, teto de exibição e o número
  do atraso exposto em vez de escondido (D-56).
- **Dois catálogos de exercício** somando as 6 categorias do Hexágono pela
  primeira vez: táticos do dump de puzzles do Lichess (D-49, CC0) e posicionais
  de broadcasts OTB reais (D-55, CC BY-SA 4.0 — a procedência é exibida depois
  da resposta porque a licença exige atribuição, não por enfeite).
- **Sessão de treino focado executável** (`/sessao/:id`, D-54): blocos de estudo
  marcáveis e bloco de prática que enfileira exercícios de verdade, com
  conclusão automática quando o último termina. É o que faltava para
  `medir_eficacia.py` ter o que medir.
- **Cadência das partidas** (D-57): as 240 classificadas, e o Hexágono passou a
  exibir a ressalva de que 59,2% do corpus é blitz acima do diagnóstico.

O que **não** está validado: nenhuma sessão real foi concluída por um humano
até hoje (ver `sessoes_treino` na seção 2), então o loop adaptativo tem o
caminho provado mas ainda não produziu uma medição de eficácia legítima.

## 6. Como re-verificar

### Verificação visual

Teste unitário não pega defeito visual: o markdown cru na narrativa (D-52)
passou por 199 testes verdes e só apareceu quando alguém olhou a tela. As
ferramentas para isso estão no repositório desde o D-53:

```bash
# 1. uma vez: baixar o Chromium que o Playwright usa
cd frontend && npx playwright install chromium

# 2. subir os dois servidores (environment.development.ts já aponta a API
#    para localhost:8000, então o `ng serve` fala com o backend local)
.venv/Scripts/python.exe -m uvicorn backend.api.api_server:app --port 8000
cd frontend && npm start

# 3. gerar uma sessão real (magic link via Admin API, sem precisar de senha)
.venv/Scripts/python.exe backend/common/gerar_sessao_local.py \
    edson.hirano.dev@gmail.com sessao.json

# 4. fotografar as 7 telas em 1440px e 390px
cd frontend && npm run telas -- ../sessao.json ../telas
```

**Atenção ao e-mail:** os dados de partida pertencem a
`edson.hirano.dev@gmail.com`, não a `edson.hirano28@gmail.com`. Gerar a sessão
para o e-mail errado devolve históricos vazios e parece bug de código.

Olhar as duas larguras importa: dos três defeitos achados no D-52, um era
exclusivo do desktop (cartões espremidos) e outro exclusivo do celular
(navegação sem pista de rolagem).

`capturar-telas.mjs` é ferramenta de **captura, não de teste** — não afirma
nada sobre o que fotografou, e por isso não entra em CI nem quebra quando a UI
muda. O julgamento é de quem olha.

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

-- (a contagem manual de TimeControl por regex sobre o PGN que ficava aqui foi
--  substituída pela coluna partidas.cadencia no D-57 — ver a query mais abaixo)

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

-- RLS das 6 tabelas do dashboard. ATENÇÃO: o comentário que ficava aqui dizia
-- "tem que ter SELECT pra {anon} E {authenticated}" — isso valia no D-16 e
-- VIROU O CONTRÁRIO no D-23/D-24. Seguir a versão antiga hoje seria recriar o
-- vazamento que o P-13 documenta. O correto agora: policy só de
-- {authenticated}, isolada por dono, e NENHUMA de {anon} no schema inteiro.
select tablename, policyname, roles, cmd from pg_policies
where tablename in ('analises_hexagono','lances_criticos','partidas','resumo_partida','revisao_exercicio_avulso','sessoes_treino')
order by tablename, roles::text;

-- o schema inteiro continua sem policy de anon? Tem que voltar 0 linhas.
select tablename, policyname from pg_policies
where schemaname='public' and 'anon' = any(roles);

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

-- o loop fechou? (D-54 tornou a conclusão automática; antes dele era 5/0/0)
select count(*) total, count(data_concluida) concluidas, count(eficacia_medida) medidas
from sessoes_treino;

-- composição do corpus por cadência (D-57): é a ressalva que o Hexágono
-- mostra acima do diagnóstico. Nenhuma partida sem cadência preenchida.
select cadencia, count(*) from partidas group by 1 order by 2 desc;
select count(*) sem_cadencia from partidas where cadencia is null;

-- a fila está consumível? (D-56) A população acrescenta 10/dia venha alguém
-- respondê-los ou não; `atrasados` crescendo mês a mês é o sinal de alerta.
--
-- CUIDADO COM O FUSO: `current_date` aqui é UTC, mas a API decide o "hoje" da
-- fila em America/Sao_Paulo (`_hoje_local()` em api_server.py). Entre 21h e
-- meia-noite de Brasília as duas discordam em um dia, e a query parece acusar
-- cards que o app ainda não mostra. Não é bug da fila.
select count(*) filter (where proxima_revisao_data <= (now() at time zone 'America/Sao_Paulo')::date) vencidos,
       count(*) filter (where proxima_revisao_data <  (now() at time zone 'America/Sao_Paulo')::date) atrasados,
       count(*) total
from fila_treino_espacado;

-- catálogo somado por categoria (D-49 + D-55): as 6 precisam ter material,
-- senão o Hexágono volta a esconder botão de "Focar" (P-15)
select categoria_hexagono, sum(n) total from (
  select categoria_hexagono, count(*) n from exercicios_taticos group by 1
  union all
  select categoria_hexagono, count(*) n from exercicios_posicionais group by 1
) x group by 1 order by 1;

-- diversidade do catálogo posicional: poucos torneios distintos é sinal de
-- que o filtro de título foi desligado ou que o teto foi batido cedo demais
select count(*) exercicios, count(distinct jogo_url) partidas,
       count(distinct evento) torneios, min(data_partida), max(data_partida)
from exercicios_posicionais;
```

```bash
# testes e cobertura do CI
python -m unittest $(find backend -name "test_*.py" | sed 's/\.py$//' | sed 's#/#.#g')
grep -c "backend\." .github/workflows/deploy-backend.yml   # módulos listados no CI
```
