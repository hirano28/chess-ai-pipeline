---
doc: DECISOES.md
escopo: decisões de design e o motivo delas; conhecimento durável, não envelhece
regra: nunca reescreva uma decisão antiga — acrescente uma nova marcando a anterior como substituída
verificado_em: 2026-09-13
---

# Registro de decisões

Cada entrada responde: qual era o problema, o que foi decidido, e o que muda por
causa disso. Cite o ID (`D-n`) em commits e comentários quando a decisão for o
motivo de uma escolha.

---

## D-1 — Gravidade medida em queda de Win%, não em centipawns crus

**Problema.** Perder 300 centipawns numa posição equilibrada e numa posição já
ganha contavam igual, distorcendo quais lances eram realmente críticos.

**Decisão.** Usar a fórmula pública do Lichess
`Win% = 50 + 50 * (2 / (1 + exp(-0.00368208 * cp)) - 1)`, em
`backend/common/chess_math.py`, e gravar `lances_criticos.queda_win_percent`.
`gravidade_cpl` continua gravada para não quebrar o histórico.

**Consequência.** Validado matematicamente contra os valores públicos do Lichess
(cp 300 → ~75%, cp 800 → ~95%). A mesma queda de 300cp vale 16,4 pontos
percentuais a mais quando parte do equilíbrio do que quando parte de posição
ganha. **Pendência conhecida:** o Agente 2 ainda agrega por `gravidade_cpl` — ver
`ESTADO.md`.

---

## D-2 — Detectar erosão estratégica, não só picos isolados

**Problema.** Erro estratégico nunca produz um pico de avaliação: ele se dissolve
ao longo de vários lances e por isso ficava invisível. O resultado era um
diagnóstico enviesado em que quase tudo virava "tática".

**Decisão.** `analisar_partidas.py` percorre janelas deslizantes de lances do
jogador e soma a perda de Win% acumulada. Ultrapassando o limiar sem nenhum lance
individual ser crítico, grava um evento `tipo_evento = 'EROSAO'` com janela
delimitada por `numero_lance`/`numero_lance_fim`.

**Consequência.** Categorias estratégicas deixaram de ficar zeradas. Trouxe à
tona `falta_de_coordenacao_de_pecas`, que já existia no vocabulário desde o
início e estava subutilizada — não foi preciso criar tag nova.

---

## D-3 — Prompt dedicado para eventos de erosão

**Problema.** Aplicar o prompt de `PICO` a um evento `EROSAO` fazia o Agente 1
inverter a perspectiva, atribuindo lances do próprio jogador ao oponente, e citar
lances fora da janela.

**Decisão.** `build_erosion_prompt` separado, roteado por `tipo_evento`. A
pergunta muda de "que erro houve neste lance" para "que padrão nesta sequência
causou a perda gradual".

---

## D-4 — Consumir o que o Lichess já calcula, em vez de recalcular

**Problema.** Precisão e erros por fase (abertura/meio-jogo/final) seriam caros e
redundantes de recalcular com Stockfish próprio.

**Decisão.** `GET /game/export/{id}?evals=1&accuracy=1&clocks=1&division=1` já
devolve tudo pronto. `enriquecer_partidas_lichess.py` faz o ETL para
`metricas_lichess_partida` e `tempos_lance`.

**Consequência.** Não se aplica ao Chess.com, cuja API não tem equivalente — o
fallback lá é extrair `%clk` do PGN já armazenado. Essa assimetria entre as duas
plataformas é permanente e esperada.

---

## D-5 — Anotação do jogador promove o lance a analisável

**Problema.** Selecionar lances críticos só por gravidade escondia justamente os
erros de processo mais corrigíveis. Validado com partidas anotadas à mão: dois
erros que o próprio jogador identificou (xeque não visto, ameaça percebida tarde)
não entraram na lista porque a queda de avaliação foi pequena.

**Decisão.** Qualquer lance com registro em `anotacoes_pensamento` entra em
`lances_criticos` mesmo com gravidade baixa. O Agente 1 recebe o texto da
anotação junto com a linha do motor e classifica `tipo_erro` em `PROCESSO` (nem
cogitou) ou `CONTEUDO` (viu e avaliou errado).

**Consequência.** A existência do relato é, por si só, sinal de valor
diagnóstico — independentemente do que o motor achou.

---

## D-6 — Anti-alucinação por verificação contra a fonte, com fallback não-LLM

**Problema.** O LLM inventava lances SAN, páginas de livro e nomes de capítulo.

**Decisão.** Padrão fixo, implementado de referência em
`backend/agentes/revisar_pensamento.py`: extrair as menções por regex → comparar
com a fonte real (tabuleiro, `livros_chunks`) → divergiu, retry de correção →
falhou de novo, fallback determinístico que formata o dado real literalmente.

**Consequência.** Nenhum caminho pode terminar entregando texto não verificado.
Vale para qualquer agente novo que cite dado técnico (regra R2).

---

## D-7 — Chaves de API múltiplas e nomeadas

**Problema.** Compartilhar o Laboratório com amigos usando uma chave única
impedia saber quem usou e revogar individualmente.

**Decisão.** `API_SECRET_KEYS` no formato `nome:chave,nome:chave`, parseado para
um dict `{chave: nome}`. Qualquer chave válida autentica, e o nome vai para o log
com timestamp. A `API_SECRET_KEY` antiga continua aceita.

---

## D-8 — Notação em português aceita, com fallback para inglês

**Problema.** O dono do projeto escreve lances em português (C, T, D, R, B) e o
`python-chess` só entende as iniciais em inglês.

**Decisão.** `backend/common/notacao_pt.py` traduz a inicial da peça e a letra de
promoção. `resolver_lance_usuario` tenta primeiro a leitura em português e cai
para o texto original em inglês se ela for ilegal na posição.

**Consequência.** A ordem importa e é deliberada: `R` é Rei em português e Torre
em inglês. Quando as duas leituras são legais na mesma posição, **o português
vence**, porque é como o usuário escreve. A resposta da API devolve
`lance_interpretado` em português para ele conferir que entendemos certo.

---

## D-9 — Assets do frontend em `public/`, não em `src/assets/`

**Problema.** Arquivos colocados em `frontend/src/assets/` não eram servidos e
resultavam em 404 silencioso nas imagens.

**Decisão.** Seguir o que o `angular.json` deste projeto realmente declara:
`{"glob": "**/*", "input": "public"}`. Referenciar sem prefixo, como o
`favicon.ico` já fazia.

---

## D-10 — Peças do tabuleiro em SVG cburnett, não em Unicode

**Problema.** Caracteres Unicode de xadrez renderizavam de forma inconsistente
entre dispositivos e navegadores, às vezes como emoji colorido.

**Decisão.** Os 12 SVGs do conjunto cburnett (Colin M. L. Burnett, GPL/CC-BY-SA),
obtidos do repositório oficial do Lichess, em
`frontend/public/pieces/cburnett/`, com atribuição visível abaixo do tabuleiro e
`ATTRIBUTION.md` na pasta. A lógica de parse do FEN não mudou — só a renderização.

---

## D-11 — Histórico genérico compartilhado entre as 3 telas interativas, cada tela restaurando o que só ela sabe restaurar

**Problema.** O Analisador de Partida já tinha histórico completo (lista, badges
de status, clique para restaurar, persistência do item ativo em `localStorage`
para sobreviver a F5). Generalizar isso para o Explicador de Posição e o
Laboratório de Raciocínio sem duplicar a lógica 3 vezes — e sem que o Explicador
sequer persistisse nada ainda (P-10, agora fechada).

**Decisão de design não-óbvia: onde fica a fronteira entre "genérico" e
"específico de cada tela".** Cogitamos um componente que soubesse buscar seus
próprios dados (`@Input() carregarItens: () => Promise<T[]>`) ou receber um
Observable já pronto. Optamos por algo mais simples e mais explícito: o
componente `historico-analise` só recebe uma **lista já mapeada** para um shape
genérico e comum:

```ts
interface HistoricoAnaliseItem {
  id: string;
  titulo: string;
  detalhes?: string[];
  dataIso?: string | null;
  status?: 'pendente' | 'processando' | 'concluido' | 'falhou';
}
```

Ele não conhece FEN, PGN, nem nenhuma regra de xadrez — só lista, badge (se
`status` estiver presente; ausente = sem badge, é o caso do Explicador e do
Laboratório, que não têm pipeline assíncrono) e emite `(itemClicado)` com o id.
Cada tela decide sozinha, no seu próprio `selecionarHistorico(id)`, como
restaurar — e as 3 restauram de formas **genuinamente diferentes**:

- **Analisador**: o item da lista não embute o resultado completo (`resumo`
  pode não existir ainda se a partida está `processando`) — restaurar dispara
  `GET /partidas/{id}/resumo`.
- **Explicador**: cada item de `GET /explicacoes-posicao/recentes` já embute
  o `resultado` inteiro (mesmo shape de `ExplicarPosicaoResponse`) — restaurar
  é local, sem chamada de rede, e usa a MESMA visualização rica de uma análise
  recém-gerada.
- **Laboratório**: `revisao_exercicio_avulso` guarda só um subconjunto dos
  campos de uma avaliação ao vivo (sem `top_candidatos`, `analise_mestre`,
  `checklist_rotina`, `lance_interpretado` — nunca foram persistidos).
  Restaurar mostra um card **somente-leitura**, deliberadamente mais simples
  que o card de uma análise ao vivo, em vez de fingir ter dados que não existem.

**Consequência.** O componente genérico ficou realmente pequeno (badge +
lista + 2 outputs) porque a parte difícil — "o que significa restaurar este
item" — é decisão de cada tela, não do componente compartilhado. O formatador
de data (`formatarDataCurta`) também foi extraído para `frontend/src/app/shared/data.ts`
pelo mesmo motivo que `shared/lichess.ts` já existia: lógica pura sem estado,
reusada por mais de um lugar, sem virar um serviço Angular desnecessário.

**Persistência que isso destravou (fecha P-10).** O Explicador de Posição não
salvava nada antes desta mudança — era lacuna confirmada, não decisão
deliberada. `POST /explicar-posicao` agora chama
`salvar_explicacao_posicao(client, resultado)` (`backend/agentes/explicador_posicao.py`)
depois de gerar a explicação, e devolve o `id` da linha criada. A persistência é
tratada como efeito colateral, não como parte do contrato principal do
endpoint: se salvar falhar, a resposta ainda volta com a explicação, só sem
`id` (logado como warning) — mesma filosofia de "melhor entregar o que o
usuário pediu do que devolver 500 por causa de um efeito colateral" já usada em
`gerar_resumo_sequencia` (resumo geral da sequência é best-effort, ver
`revisar_exercicio_avulso.py`).

---

## D-12 — Nome de abertura resolvido diferente por plataforma, nunca inventado

**Problema.** A ideia inicial era ler o nome da abertura de uma tag `[Opening]`
no PGN já salvo em `partidas`. Verificação real (regra R3 do `AGENTS.md`: "não
confie sem checar o formato real") mostrou que isso não existe nos dados deste
projeto: **nenhuma** das 64 partidas do Lichess nem das 146 do Chess.com tem
essa tag — só as 4 partidas `MANUAL` (PGN colado à mão) têm.

**Decisão.** `backend/agentes/normalizar_aberturas.py` resolve o nome cru de um
jeito diferente por plataforma, na ordem:

1. Tag `[Opening "..."]` do PGN, quando presente (cobre `MANUAL`).
2. Tag `[ECOUrl "..."]` do Chess.com — o nome já está embutido na URL do
   artigo (`.../openings/French-Defense-Steinitz-Attack` → `"French Defense
   Steinitz Attack"`).
3. Só para Lichess, sem nenhuma das duas: chama
   `GET /game/export/{id}?opening=1` (mesmo endpoint que
   `enriquecer_partidas_lichess.py` já usa — D-4) e lê `opening.name` da
   resposta. É uma chamada de rede por partida, mas roda uma vez por leva nova
   (o script só processa `abertura_normalizada is null`).

Depois de obter o nome cru, `normalizar_abertura()` tenta casar contra um
dicionário de padrões reconhecíveis (`MAPEAMENTO_FAMILIAS`, ordenado do mais
específico ao mais genérico — ex.: `"Giuoco Piano"` precisa bater com Italiana
antes de qualquer regra genérica de peão de rei). **Sem correspondência, grava
o nome original completo**, nunca uma família aproximada — mesma filosofia
anti-invenção de `D-6`, adaptada de "não alucine dado técnico" para "não
alucine categoria que os dados não sustentam".

**Consequência.** Rodado contra as 215 partidas existentes: 0 falhas,
distribuição concentrada em `Francesa` (51), `Peão de Dama` (22), `Moderna`
(17), `Sistema Londres` (17) e `Siciliana` (17), com uma cauda longa de
variações raras mantidas com o nome original — ver `ESTADO.md`. O dicionário é
deliberadamente incompleto: **é para ser estendido conforme aparecer volume**,
não para cobrir todo o vocabulário ECO de uma vez.

---

## D-13 — Insights de repertório: só LICHESS/CHESSCOM, limiar de amostra por agregação

**Problema.** `GET /insights/repertorio` cruza `abertura_normalizada` (D-12)
com resultado, precisão por fase e diagnósticos — mas 4 agregações diferentes
sobre a mesma base pequena (215 partidas) correm risco de ruído estatístico
(uma abertura com 1-2 partidas "provando" 100% ou 0% de vitória) e de misturar
dado que não deveria entrar na mesma conta.

**Decisão.**

1. **Partidas `MANUAL` ficam de fora de toda agregação.** São PGN colado à mão
   no Analisador — podem ser qualquer partida (de um livro, de um amigo), não
   necessariamente do próprio jogador. Misturá-las em "minha taxa de vitória"
   seria dado errado, não só ruidoso.
2. **`MIN_AMOSTRA = 5`**, mesmo valor já usado como `CATEGORY_MIN_DIAGNOSTICS`
   em `agente2_analista.py` — reaproveita o limiar que este projeto já validou
   como "amostra mínima aceitável", em vez de inventar um novo número.
3. **Onde dá pra somar sem perder sentido (item 2, por abertura+cor), os
   grupos abaixo do limiar viram um bucket `"outras"`** — por `cor_jogada`
   separadamente, porque taxa de vitória de brancas e de pretas não deveriam
   se misturar dentro do mesmo "outras". Onde somar não faz sentido (item 3,
   lance de PICO; item 4, categoria do hexágono) o grupo abaixo do limiar é só
   omitido — a média de "lance onde ocorre PICO" de duas aberturas diferentes
   não vira uma média útil de coisa nenhuma.
4. **O limiar do item 4 (categorias por abertura) conta diagnósticos
   considerados, não incrementos de categoria válidos.** Um diagnóstico com
   tag fora do vocabulário fechado (R1) ainda consome uma vaga da amostra — a
   pergunta que o limiar responde é "quantos diagnósticos temos dessa
   abertura", não "quantos incrementos bateram".

**Consequência.** Rodado contra o banco de produção (210 partidas
LICHESS+CHESSCOM, 11/09/2026): Francesa aparece separada por cor (PRETAS: 44
partidas, 52,27% vitória; BRANCAS: 7 partidas, 57,14%) porque as duas
combinações batem o limiar sozinhas; nenhuma abertura precisou do bucket
`"outras"` para ficar de fora da lista principal nesta massa de dados —
"outras" apareceu só como agregado dos casos abaixo de 5 por cor. Nenhuma das
linhas trouxe `precisao_media_*`: as 3 colunas de fase (ver `BANCO.md`) só têm
valor a partir de agora, e nenhuma das 4 linhas existentes de
`metricas_lichess_partida` foi reprocessada retroativamente (decisão já
tomada ao criar essas colunas — ver `enriquecer_partidas_lichess.py`).

---

## D-14 — `user_id` só nas 6 tabelas raiz; Fase B (Auth + RLS) deliberadamente adiada

**Problema.** O banco nasceu single-tenant implícito: nenhuma linha diz de quem
ela é. Para um dia existir mais de um usuário, o dono precisa estar gravado —
mas travar acesso agora quebraria tudo que funciona hoje.

**Decisão: separar em duas fases, e fazer só a Fase A.**

**Fase A (feita).** `user_id uuid not null` em exatamente 6 tabelas:
`partidas`, `analises_hexagono`, `sessoes_treino`, `explicacoes_posicao`,
`puzzle_atividade`, `revisao_exercicio_avulso`.

**Por que só essas 6: são as únicas sem pai natural.** Todo o resto do schema
pendura numa cadeia de FK que já existe e já identifica o dono —
`lances_criticos.partida_id` → `partidas`, `diagnosticos.lance_id` →
`lances_criticos` → `partidas`, e assim por diante para `tempos_lance`,
`metricas_lichess_partida`, `anotacoes_pensamento`, `perguntas_pendentes`,
`revisoes_pensamento`, `resumo_partida`. Repetir `user_id` nelas criaria um
segundo lugar para o mesmo fato, que pode divergir do primeiro (um `user_id`
de `diagnosticos` diferente do `user_id` da `partida` do lance) — é a mesma
regra de "um fato, um só lar" que vale para a documentação (ver D-11),
aplicada ao schema. Na Fase B, a policy de uma tabela filha vira um `exists`
subindo a cadeia, não uma coluna nova.

`livros_chunks` e `indice_conceitual` ficam de fora por outro motivo: são
corpus de referência compartilhado (livros), não dado de usuário.

**A FK para `auth.users` NÃO entra agora.** `auth.users` está vazia — o Auth do
Supabase é justamente a Fase B — então nenhum UUID satisfaria a constraint
hoje. A coluna é `uuid` puro e a FK está escrita e comentada no fim de
`backend/db/user_id_tabelas_raiz.sql`, para entrar junto com a conta real.

**O valor vem de `DEFAULT_USER_ID`**, variável obrigatória lida por
`backend/common/tenant.py` **na hora da escrita**, não no import: os scripts só
chamam `load_dotenv()` dentro do próprio `load_settings()`, então capturar no
import pegaria vazio. Os 7 pontos de escrita nessas 6 tabelas
(`common_ingestao.insert_game`, `analisar_pgn_avulso.inserir_partida`,
`agente2_analista.salvar_analise`, `agente3_prescritor.salvar_sessao`,
`explicador_posicao.salvar_explicacao_posicao`,
`importar_puzzle_activity.upsert_puzzle_atividade`,
`revisar_exercicio_avulso.salvar_exercicio`) preenchem o campo.

**RLS não foi tocado.** Nenhuma policy criada, alterada ou removida; o
comportamento de leitura e escrita é idêntico ao de antes. Esta é uma mudança
de **dado**, não de **acesso** — o que é exatamente o que a torna segura de
fazer antes do Auth existir.

**Consequência.** 900 linhas backfilladas com o mesmo dono
(`partidas` 215, `puzzle_atividade` 660, `revisao_exercicio_avulso` 12,
`explicacoes_posicao` 7, `analises_hexagono` 3, `sessoes_treino` 3). Como a
coluna é `NOT NULL`, qualquer caminho de escrita novo nessas 6 tabelas que
esqueça o `user_id` **falha na hora** em vez de gravar órfão — o erro aparece
no desenvolvimento, não meses depois na migração para multi-tenant. A Fase B
está registrada como pendência P-11 em `ESTADO.md`.

---

## D-15 — Fase B.1: login existe e funciona, mas fica desligado do fluxo hoje

**Problema.** Ligar autenticação de verdade (D-14/P-11, Fase B) sem quebrar o
que já funciona: X-API-Key do Laboratório/Explicador, e o dashboard
("Meu Hexágono") que hoje é 100% anônimo.

**Decisão 1 — um único client, não dois.** O supabase-js não tem conceito de
"client anônimo" vs "client autenticado" como duas instâncias: é o MESMO
`SupabaseClient` que, a partir do momento em que `auth.signInWithPassword()`/
`signUp()` roda nele, passa a anexar o JWT da sessão em toda chamada
`.from(...)` seguinte. `SupabaseService` (usado por `hexagono-radar`,
`narrativa-analise`, `sessoes-treino`, `perguntas-pendentes`) já era um
singleton `providedIn: 'root'` com um único client — bastou expor
`get auth()` nele e fazer `AuthService` operar sobre esse mesmo client. Os 4
componentes que já liam Supabase direto **não precisaram de nenhuma mudança**
pra "usar o client autenticado": passaram a fazer isso automaticamente, de
graça, só por injetarem o mesmo `SupabaseService` de sempre.

**Decisão 2 — o guard existe, está testado, mas NÃO está ligado nas rotas.**
O próprio pedido desta fase tinha uma contradição real: a instrução de
abertura e a de fechamento diziam "não trave nenhum acesso
existente, deve continuar funcionando via anon"; o item pontual do guard
pedia redirecionar pra `/login` **qualquer** acesso às 4 telas do dashboard —
inclusive de quem só usa o Laboratório via X-API-Key e nunca criou conta.
Confirmado com o usuário: o guard (`guards/auth.guard.ts`) fica implementado
e coberto por teste, mas `app.routes.ts` não usa `canActivate` em nenhuma
rota. Hoje, literalmente nada muda para ninguém — login/cadastro existem
como uma porta nova, não como uma porta trancada. Ligar o guard é decisão
explícita de uma fase B.2.

**Descoberta durante o teste manual — RLS aqui é `TO anon`, não `TO public`.**
Testado de ponta a ponta com uma conta real (signUp → confirmação de e-mail
via Admin API, já que este projeto exige confirmação por padrão → login →
dashboard): **o dashboard carrega vazio para quem está autenticado**, embora
carregue normalmente para quem está anônimo. Causa raiz, confirmada por
`pg_policies`: toda policy em `analises_hexagono`, `lances_criticos`,
`partidas`, `resumo_partida`, `revisao_exercicio_avulso`, `sessoes_treino` é
`roles: {anon}` — não `{public}`. Postgres não trata "using(true)" como
"vale pra qualquer role": a policy só se aplica à role listada. Sem uma
policy para `authenticated`, a regra vira **negação por padrão** assim que o
PostgREST troca a role da requisição de `anon` para `authenticated`.

Isso **não foi corrigido aqui** — mexer em RLS estava explicitamente fora do
escopo deste passo ("RLS permanece como está"). Fica registrado como bloqueio
conhecido da Fase B.2 em `ESTADO.md` (P-11): antes de qualquer travamento por
usuário fazer sentido, alguém vai precisar decidir entre acrescentar policy
`TO authenticated` espelhando a de `anon`, ou trocar `TO anon` por
`TO public` nessas 6 tabelas — e só DEPOIS resolver o escopo por `user_id`
(D-14) por cima disso.

**Consequência prática hoje.** Fazer login pela tela nova é seguro (não
quebra nada, o guard está desligado), mas **não traz nenhum benefício ainda**
para as 4 telas do dashboard — elas ficam vazias pra quem loga, cheias pra
quem não loga. Laboratório/Explicador/Analisador não são afetados: eles
falam com o FastAPI (que usa a service role key, sem RLS) via X-API-Key, não
com o Supabase direto.

---

## D-16 — Paridade anon/authenticated nas 6 tabelas do dashboard (correção pontual, não é B.3)

**Problema.** D-15 registrou a descoberta: logar pela tela de B.1 fazia o
dashboard "Meu Hexágono" carregar vazio, porque `analises_hexagono`,
`lances_criticos`, `partidas`, `resumo_partida`, `revisao_exercicio_avulso`
e `sessoes_treino` só tinham policy de SELECT para a role `anon`
(`roles: {anon}`). Postgres nega por padrão quando não existe nenhuma
policy aplicável à role da sessão — `using(true)` na policy de `anon` não
"vaza" pra `authenticated`; são avaliadas por role, não por condição.

**Decisão.** `backend/db/rls_authenticated_paridade_dashboard.sql` acrescenta
uma 2ª policy de SELECT em cada uma das 6 tabelas, `to authenticated`, com o
**mesmo `using(true)`** da policy de `anon` — não um filtro novo, só a mesma
regra pra role nova. As policies de `anon` (leitura, e as de escrita em
`sessoes_treino`/`revisao_exercicio_avulso`) não foram tocadas: nem editadas,
nem removidas, nem recriadas.

**Isto é uma correção de paridade temporária, não a Fase B.3.** B.3 (ainda
não implementada) é sobre **isolar** dado por dono — trocar `using(true)`
por `using(user_id = auth.uid())` (ou o `exists` equivalente nas tabelas
filha, ver D-14). O que este commit faz é o oposto do escopo de B.3: garante
que, HOJE, autenticado e anônimo continuam vendo exatamente o mesmo dado —
zero isolamento, só paridade. Quando B.3 rodar, é a condição destas mesmas 6
policies de `authenticated` que vai mudar de `true` para o filtro por
usuário; as de `anon` provavelmente deixam de fazer sentido nesse momento
(ou são removidas, ou passam a exigir login de fato) — decisão de B.3, não
desta correção.

**Consequência.** Testado de ponta a ponta com uma conta real (mesmo e-mail
`+alias` de D-15, recriada — signUp, confirmação via Admin API já que este
projeto exige confirmação, login, comparação do `<main>` do dashboard entre
aba anônima e aba autenticada): conteúdo **byte-a-byte idêntico** (6823
caracteres nas duas), incluindo o radar do hexágono, a narrativa, as 6
perguntas pendentes (via `lances_criticos`→`partidas` embutido) e as 3
sessões de treino. Confirmado também direto via `curl` com o JWT real contra
o PostgREST (`HTTP 200`, `content-range: 0-5/*`, as mesmas 6 linhas), sem
depender do navegador. Um erro de CORS apareceu uma única vez no console
durante a transição de rota `/login` → `/` na primeira rodada do teste e não
se repetiu numa segunda rodada idêntica — tudo indica requisição abortada
pela própria navegação da SPA, não falha do fix (o servidor respondeu 200
via curl para a mesma query com o mesmo token). Conta de teste apagada ao
final (`auth.users` de volta a 0 linhas).

---

## D-17 — Identidade por sessão real, com fallback de API key (Fase B.2)

**Problema.** Depois de D-14 (coluna `user_id`) e D-15/D-16 (login funcionando
e vendo o mesmo dado que anônimo), toda escrita de verdade — Laboratório,
Explicador, Analisador — continuava gravando `DEFAULT_USER_ID` fixo. Os 4
amigos que usam o Laboratório com sua própria `X-API-Key` nomeada (D-7) têm
identidade individual **no log**, mas todo dado deles cai no mesmo dono no
banco que o do dono do projeto — o multi-tenant da Fase A não tinha, na
prática, nenhum dado realmente multi-tenant ainda.

**Decisão.** Dois caminhos de identidade coexistindo, resolvidos nesta ordem
em `api_server.resolver_user_id_para_escrita(request)`:

1. **Header `Authorization: Bearer <token>` presente e válido** → valida via
   `supabase_client.auth.get_user(token)` (mesmo client de sempre, criado com
   a service role key — confirmado que isso funciona: `get_user` valida a
   assinatura do JWT contra o projeto, independente de qual `apikey` o
   client usa pra suas próprias chamadas) → usa o `user.id` real.
2. **Qualquer outro caso** (sem header, token expirado/malformado, banco
   indisponível) → `DEFAULT_USER_ID` de sempre (D-14). `get_user()` levanta
   `AuthApiError` em token inválido (confirmado contra o Supabase real antes
   de implementar); qualquer exceção aqui vira fallback silencioso, nunca
   401 — isto é resolução de identidade pra escrita, não gate de acesso.

**`X-API-Key` continua sendo o gate de acesso ao endpoint, sem nenhuma
mudança.** `Authorization: Bearer` é aditivo, não substitui: um pedido sem
`X-API-Key` válida continua recebendo 401 antes de qualquer coisa (mesma
`verificar_api_key` de sempre), autenticado ou não via Supabase. Isso é
deliberado — "esta etapa só HABILITA o caminho novo em paralelo ao antigo",
os 4 amigos não precisam criar conta pra continuar usando exatamente como
hoje.

**As 3 funções de persistência ganharam `user_id: str | None = None`, não
passaram a exigi-lo.** `salvar_exercicio`, `salvar_explicacao_posicao`,
`inserir_partida` continuam utilizáveis sem esse argumento (os scripts
interativos de linha de comando em `revisar_exercicio_avulso.py` e
`analisar_pgn_avulso.py` chamam essas funções sem sessão HTTP nenhuma pra
resolver — `None` cai no `obter_default_user_id()` de sempre, zero mudança
de comportamento pra eles). Só `api_server.py` passa o `user_id` resolvido
explicitamente nos 3 endpoints de escrita (`/revisar-avulso/salvar`,
`/explicar-posicao`, `/analisar-pgn`).

**Frontend: um único método assíncrono de headers, só nos 3 métodos que
escrevem tabela raiz.** `RevisaoAvulsaService.headersComChaveEAuth()` monta
`X-API-Key` (sempre) + `Authorization: Bearer` (só se
`AuthService.autenticado()` E existir um `access_token` de verdade — sessão
pode ter expirado entre as duas checagens, tratado sem quebrar). Aplicado só
em `salvar()`, `explicarPosicao()` e `submeterPartidaPgn()` — os métodos de
leitura (`revisar`, `listarPartidasRecentes`, etc.) continuam com
`headersComChave()` de sempre, porque não escrevem em tabela raiz e portanto
não têm o que atribuir.

**Consequência.** Testado de ponta a ponta com uma conta real, pelo
Laboratório de verdade (Stockfish + Gemini reais, não mock): logado, a linha
nasceu com `user_id` = UUID da conta de teste; no mesmo navegador mas em
contexto sem sessão (só `X-API-Key`), a linha nasceu com `user_id` =
`DEFAULT_USER_ID`, igual a antes desta fase. Os dois caminhos coexistiram na
mesma sessão de teste sem nenhum conflito. Conta de teste e as 2 linhas de
teste apagadas ao final.

**O que isto NÃO faz ainda.** Não filtra leitura por usuário — `GET
/revisoes-avulsas/recentes` (e os equivalentes de Explicador/Analisador)
continuam devolvendo o histórico inteiro pra qualquer chave válida,
independente de quem gravou cada linha. Migrar os 4 amigos pra conta própria,
e filtrar leitura por dono, é decisão de uma fase seguinte — não desta.

---

## D-18 — Leitura filtrada pelo dono real da sessão (Fase B.3, primeira parte)

**Problema.** D-17 resolveu a *escrita*: cada exercício, explicação ou
partida passou a nascer com o `user_id` de quem realmente estava logado. Mas
a *leitura* — `GET /revisoes-avulsas/recentes`, `GET
/explicacoes-posicao/recentes`, `GET /partidas/recentes` — continuava sem
filtro nenhum: qualquer `X-API-Key` válida via o histórico inteiro, dos 4
amigos e do dono, misturado. O multi-tenant ficava pela metade: dado
corretamente atribuído na escrita, mas exposto por igual a todo mundo na
leitura.

**Decisão.** Os 3 endpoints de leitura passaram a receber `request: Request`
e a filtrar a query com `.eq("user_id", resolver_user_id_para_escrita(request))`
— a mesma função de resolução de identidade de D-17, reaproveitada sem
alteração: sessão real via `Authorization: Bearer` quando presente e válida,
senão `DEFAULT_USER_ID` (o comportamento de sempre, preservado para quem
ainda não migrou). Nomeadamente reaproveitada, não uma variante nova, porque
"quem é o dono de uma leitura" e "quem é o dono de uma escrita" é a mesma
pergunta — resolver das duas formas seria duplicar a mesma lógica de fallback
em dois lugares (o princípio de "um fato, um só lar").

**RLS não foi tocado.** O filtro está na query do backend, não numa política
do banco. Isso é suficiente porque hoje só o backend acessa essas 3 tabelas,
e sempre com a `service role key` — que ignora RLS por definição. Se algum
dia outro cliente passar a falar direto com o Postgres/PostgREST usando a
sessão do usuário (não a service role), esse filtro de aplicação deixa de ser
suficiente sozinho e vira a hora de revisitar RLS com isolamento de verdade —
não antes.

**Consequência, testado com 2 contas reais.** Duas contas de teste
(`teste-d18-conta-a`, `teste-d18-conta-b`) criadas via Admin API, cada uma
salvando um exercício em `/revisar-avulso/salvar` com sua própria sessão.
`GET /revisoes-avulsas/recentes` da conta A devolveu só o próprio exercício;
da conta B, idem — nenhuma viu a linha da outra. Confirmado por SQL direto
que os dois `user_id` gravados batem exatamente com os UUIDs reais das duas
contas em `auth.users`. Repetido sem `Authorization` (só `X-API-Key`): a
listagem voltou a mostrar exclusivamente o histórico sob `DEFAULT_USER_ID` —
nem uma das duas linhas de teste apareceu ali, confirmando que o caminho
antigo continua isolado do novo. Contas e linhas de teste apagadas ao final.

**O que isto NÃO faz ainda.** Não migra os 4 amigos de `X-API-Key` pra conta
própria — enquanto eles não tiverem sessão, toda leitura e escrita deles
continua caindo no `DEFAULT_USER_ID` compartilhado, exatamente como sempre
foi. Essa migração é o próximo passo da Fase B.3, fora do escopo daqui.

---

## D-19 — Isolamento RLS por dono nas tabelas do dashboard (Fase B.3, segunda parte)

**Problema.** D-16 introduziu paridade entre `anon` e `authenticated` criando
policies de SELECT `to authenticated` com `using(true)` em `analises_hexagono`,
`sessoes_treino`, `partidas`, `lances_criticos`, `revisao_exercicio_avulso` e
`resumo_partida`. Isso evitou que o dashboard carregasse vazio para usuários
logados, mas como efeito colateral permitia que qualquer usuário logado visse
os dados de todos os outros usuários. Com mais de uma pessoa real usando a
aplicação, a leitura direta via PostgREST precisava de isolamento estrito no
banco por dono de verdade.

**Decisão.** Trocar a cláusula `using(true)` das policies de `authenticated`
pelo filtro de identidade `auth.uid()`:

1. **Tabelas raiz com `user_id` próprio** (`analises_hexagono`, `sessoes_treino`,
   `partidas`, `revisao_exercicio_avulso`):
   `using (user_id = auth.uid())`
2. **Tabelas filhas sem `user_id` próprio** (`lances_criticos`, `diagnosticos`,
   `resumo_partida`):
   Filtram via `exists` subindo a cadeia de chaves estrangeiras até
   `partidas.user_id = auth.uid()`:
   - `lances_criticos`: `exists (select 1 from partidas where partidas.id = lances_criticos.partida_id and partidas.user_id = auth.uid())`
   - `diagnosticos`: `exists (select 1 from lances_criticos join partidas on partidas.id = lances_criticos.partida_id where lances_criticos.id = diagnosticos.lance_id and partidas.user_id = auth.uid())`
   - `resumo_partida`: `exists (select 1 from partidas where partidas.id = resumo_partida.partida_id and partidas.user_id = auth.uid())`

**As policies `to anon` NÃO foram alteradas.** O acesso não autenticado (via
chave pública anônima) continua funcionando como antes, sem quebrar o fluxo
histórico.

**Frontend não precisou de nenhuma mudança de código.** O `SupabaseClient` do
`SupabaseService` anexa o JWT da sessão automaticamente em todas as requisições
`.from(...)`. O PostgREST avalia `auth.uid()` diretamente contra as novas
policies, tornando o isolamento transparente para os componentes Angular
(Hexágono, Narrativa, Sessões de Treino, Perguntas Pendentes).

**Dono do corpus histórico migrado para Edson.** As 900 linhas anteriormente
backfilladas com o UUID provisório `51e682f1-50a7-4360-a40d-f17a5524c49b` foram
transferidas para o UUID real da conta confirmada do Edson
(`bfde845a-8e2e-4885-801f-0fed2dd3b426`), e `DEFAULT_USER_ID` no `.env` e
`env.yaml` foi atualizado para este mesmo UUID.

**Consequência e validação.** Testado via script automatizado com duas contas
reais (`edson.hirano.dev@gmail.com` e uma conta temporária via Admin API): cada
conta gerou seus registros em partidas, lances críticos, diagnósticos, resumos,
sessões de treino e análises de hexágono. Sob a sessão de cada conta, confirmou-se
que nenhuma enxerga qualquer dado pertencente à outra. A conta e dados de teste
temporários foram removidos ao final, mantendo a conta do Edson intacta.

---

## Decisões tomadas sobre o que NÃO fazer

- **ChessTempo não tem API pública.** Não gaste tempo tentando integrar; a
  alternativa adotada foi migrar exercícios temáticos para o sistema de puzzles
  do Lichess, que tem API.
- **Modelo Maia personalizado** (distinguir erro previsível de aleatório) é
  tecnicamente interessante mas exige treinar rede neural. Fora de escopo até o
  resto do roadmap amadurecer.
- **Gemini Code Assist na IDE** foi descontinuado pelo Google em 18/06/2026. Não
  é bug local e não tem correção.
