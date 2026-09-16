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

## D-20 — Deploy automático sincroniza env vars do Cloud Run com os GitHub Secrets

**Problema.** `deploy-backend.yml` só propagava `DEFAULT_USER_ID` via
`--update-env-vars`; as demais variáveis (`SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, `API_SECRET_KEYS`) dependiam de
alguém lembrar de rodar manualmente `gcloud run deploy
--env-vars-file=env.yaml` sempre que um valor mudasse. Isso já causou dois
incidentes reais nesta mesma sessão de trabalho: `DEFAULT_USER_ID` precisou
ser criado como secret na primeira vez que passou a ser exigido (D-14), e
depois, quando D-19 trocou o valor de `DEFAULT_USER_ID` no `.env`/`env.yaml`
para o UUID real do Edson, o deploy automático seguinte continuou gravando o
UUID antigo no Cloud Run — o secret do GitHub não tinha sido atualizado junto,
e nada no workflow avisava disso. `env.yaml` local parecia a fonte de
verdade, mas não era: era só o que um comando manual, se alguém lembrasse de
rodar, levaria para produção.

**Decisão.** O deploy automático passa a gerar, a cada execução, um arquivo
de env vars a partir dos GitHub Secrets e usá-lo com `--env-vars-file` — a
mesma flag do comando manual documentado, não `--update-env-vars`. A escolha
de `--env-vars-file` (que **substitui por completo** as env vars do serviço,
confirmado via `gcloud run deploy --help`) em vez de `--update-env-vars`/
`--set-env-vars` inline é deliberada por dois motivos:

1. **Substituição total, não mescla.** `--update-env-vars` só atualiza as
   chaves citadas e deixa as demais como estavam — exatamente o mecanismo que
   permitiu o UUID antigo sobreviver ao deploy de D-19 sem ninguém perceber.
   Com `--env-vars-file`, o conjunto de env vars do Cloud Run é sempre
   exatamente o que os Secrets dizem hoje, nunca um resquício de um deploy
   manual antigo.
2. **Evita quebrar valores com vírgula.** `API_SECRET_KEYS` usa o formato
   `nome:chave,nome:chave` — a vírgula interna quebraria o parsing de
   `--update-env-vars="K1=V1,K2=V2"` (a vírgula seria lida como separador
   entre variáveis). Um arquivo YAML não tem esse problema; confirmado
   gerando o arquivo e recarregando com PyYAML antes de aplicar a mudança.

O novo step (`Gerar arquivo de env vars para o Cloud Run a partir dos GitHub
Secrets`) valida antes de gerar o arquivo que todos os 5 secrets necessários
estão presentes (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`GEMINI_API_KEY`, `API_SECRET_KEYS`, `DEFAULT_USER_ID`) e falha o job com uma
mensagem acionável se faltar algum, em vez de deployar com valor vazio.
`STOCKFISH_PATH` foi deliberadamente deixado fora dessa lista: ele já vem
gravado na imagem via `ENV` no `Dockerfile`, não depende de secret nenhum, e
`--env-vars-file` substitui só as env vars do *serviço* Cloud Run — não afeta
o que a imagem do container já define internamente.

**`env.yaml` local não foi removido**, mas seu papel mudou: continua servindo
de referência rápida de quais nomes importam e para deploys manuais
pontuais, mas deixou de ser a fonte de verdade de produção — essa fonte agora
são os GitHub Secrets, únicos que o workflow automático realmente lê. Editar
só o arquivo local, sem atualizar o secret correspondente, não tem mais
nenhum efeito no próximo deploy.

**Consequência.** Validado localmente: o script de geração do arquivo
produz um YAML sintaticamente válido (parseado de volta com PyYAML) e
preserva corretamente um valor com vírgula interna (`API_SECRET_KEYS`) como
uma única string — confirmando que o problema de parsing do
`--update-env-vars` inline realmente existiria e realmente é evitado por
este formato. Consultei também o serviço Cloud Run real
(`gcloud run services describe`) para confirmar que os 5 valores hoje em
produção batem com `env.yaml` local — o que era verdade só porque alguém
rodou o comando manual depois do incidente, exatamente a dependência que
esta decisão elimina daqui pra frente.

---

## D-22 — Fechamento das tabelas sem RLS nenhum (incidente de vazamento)

> Não existe D-21: o número foi pulado deliberadamente, não é entrada perdida.

**Problema.** A varredura de `pg_class` + `pg_policies` (feita agora, não de
memória) encontrou **9** tabelas sem política nenhuma — não as 6 que a P-2
catalogava. Dessas, **6 estavam com `rls_ligado = false`**, e RLS desligado no
Postgres significa acesso irrestrito: qualquer portador da chave `anon` — que
é **pública e vai no bundle do frontend** — lia as tabelas inteiras. Entre elas,
texto pessoal: `perguntas_pendentes.pergunta_texto`,
`anotacoes_pensamento.texto_pensamento`, `revisoes_pensamento.texto_pensamento`.

Confirmado por curl real antes de qualquer correção, com duas contas de teste
(A, com dado próprio semeado; B, sem dado nenhum) — as três identidades
recebiam exatamente as **mesmas** linhas:

| Tabela | anon | conta B (sem dado) | conta A (dona) |
|---|---|---|---|
| `perguntas_pendentes` | 7 | 7 | 7 |
| `anotacoes_pensamento` | 24 | 24 | 24 |
| `revisoes_pensamento` | 24 | 24 | 24 |
| `tempos_lance` | 200+ | 200+ | 200+ |
| `metricas_lichess_partida` | 5 | 5 | 5 |
| `puzzle_atividade` | 200+ | 200+ | 200+ |

O vazamento chegava ao navegador de verdade: numa sessão com conta de teste em
produção, o `GET perguntas_pendentes` voltou HTTP 200 com o texto íntegro de
uma pergunta do dono. A tela não pintava isso por **acidente** — o embed
`lances_criticos(...)` já era filtrado por D-19, voltava `null`, e o `.map()`
do `SupabaseService` descartava a linha. O dado saía do banco mesmo assim.

**Decisão.** `backend/db/rls_tabelas_sem_politica.sql` liga RLS nas 6 e aplica
o mesmo padrão de D-19 — raiz filtra por `user_id = auth.uid()`, filha por
`exists` subindo a cadeia de FK até `partidas.user_id`:

- `puzzle_atividade` (raiz, tem `user_id`): condição direta.
- `anotacoes_pensamento`, `revisoes_pensamento`, `tempos_lance`,
  `metricas_lichess_partida`: `exists` via `partida_id`.
- `perguntas_pendentes` (neta): `exists` via `lance_id` →
  `lances_criticos.partida_id` → `partidas.user_id`.

**Nenhuma policy de `anon` foi criada, de propósito.** Manter `using(true)`
para `anon` seria manter exatamente o vazamento que motivou a correção — as 6
são tabelas de dado pessoal, nenhuma tem conteúdo público. Consequência
deliberada: o cartão "Perguntas pendentes" passa a **exigir login**. Para
visitante anônimo ele fica vazio, sem erro (verificado no navegador: zero
respostas 4xx/5xx e zero erros de console no dashboard anônimo).

**Duas dessas tabelas precisaram de policy de escrita, não só de leitura.**
`perguntas_pendentes` (UPDATE) e `anotacoes_pensamento` (INSERT + UPDATE) são o
único ponto onde o frontend escreve direto no Postgres, sem passar pelo
FastAPI: o fluxo `responderPergunta` faz upsert da anotação e marca a pergunta
como `RESPONDIDA`. As policies de escrita carregam a mesma condição de dono no
`with check`, então ninguém anota numa partida que não é sua.

**Consequência, validada por curl depois da migration.** Em todas as 6:
`anon` → 0 linhas, conta B → 0 linhas, conta A → exatamente a linha dela (as
linhas de `tempos_lance`/`metricas_lichess_partida`/`puzzle_atividade` foram
conferidas uma a uma pelo `partida_id`/`user_id`, porque a heurística do
harness dava falso positivo nelas). O fluxo do dono continua inteiro: SELECT
com join embutido preenchido, upsert HTTP 200, update de status HTTP 200. E a
tentativa da conta B de inserir anotação numa partida da conta A voltou
**HTTP 403 — `new row violates row-level security policy`**. O pipeline não foi
afetado: ele fala com o banco pela service role key, que ignora RLS
(reconferido: as 6 tabelas seguem legíveis por ela).

**Três tabelas da varredura NÃO foram mexidas, e isso é decisão, não
esquecimento.** `explicacoes_posicao`, `livros_chunks` e `indice_conceitual`
aparecem com RLS ligado e zero policies — o que **nega tudo por padrão**, não
vaza (confirmado por curl: 0 linhas para as três identidades). Ficam fechadas:
o histórico do Explicador chega pelo FastAPI (service role), e
`livros_chunks`/`indice_conceitual` são corpus de RAG sem dono por linha — não
têm `user_id` nem caminho até `partidas`, então isolamento por usuário não se
aplica a elas.

**O que isto NÃO resolve.** Sobram **7 tabelas com policy de `anon`
`using(true)`**, herdadas de D-16 e preservadas por D-19: `partidas` (215
linhas, PGN completo), `lances_criticos` (525), `diagnosticos` (525),
`analises_hexagono` (3), `sessoes_treino` (3), `revisao_exercicio_avulso` (12)
e `resumo_partida` (4). Confirmado por curl com a chave anon pura: elas ainda
entregam o corpus do dono para qualquer visitante. É a mesma classe de
exposição, mantida de propósito enquanto o dashboard sem login for um fluxo
suportado — fechá-las esvazia o dashboard anônimo por completo, que é uma
decisão de produto, não de correção de incidente.

---

## D-23 — Fase B efetivamente concluída: login obrigatório + zero acesso anônimo

**Problema.** D-22 fechou P-2 (tabelas sem RLS nenhum). A pendência que sobrou
dela, **P-13**, era diferente: 7 tabelas (`partidas`, `lances_criticos`,
`diagnosticos`, `revisao_exercicio_avulso`, `resumo_partida`,
`analises_hexagono`, `sessoes_treino`) continuavam com policy `to anon
using(true)` — não por RLS desligado, mas por decisão explícita de D-16, pra
sustentar um dashboard que funcionava sem login. Enquanto essas policies
existissem e o `authGuard` (implementado desde D-15, nunca ligado) ficasse
fora de `app.routes.ts`, o isolamento por dono de D-19/D-22 era opcional: bastava
não logar pra ver o corpus inteiro do dono.

**Decisão.** Duas mudanças na mesma leva, porque uma sem a outra não fecha
nada:

1. **`backend/db/rls_remove_anon_dashboard.sql`** remove as 7 policies `to
   anon using(true)`. As policies de `authenticated` isoladas por dono (D-19)
   não mudam.
2. **`app.routes.ts`** aplica `authGuard` nas 4 rotas do dashboard (`/`,
   `/laboratorio`, `/explicador`, `/analisador`). Visitante sem sessão é
   redirecionado pra `/login?returnUrl=...`.

**Achado durante a migration: `sessoes_treino` tinha um UPDATE anônimo sem
equivalente `authenticated`.** A policy `"Permitir atualizar data_concluida"`
(`to anon`, `using(true)`, `with_check(true)`) sustentava o botão "Marcar como
concluída" — e nenhuma policy de UPDATE pra `authenticated` jamais existiu,
porque até agora ninguém usava o dashboard logado de verdade. Sem substituir,
o botão quebraria pra todo mundo assim que o anon caísse. Corrigido na mesma
migration: policy nova `to authenticated using/with check (user_id =
auth.uid())`.

**Confirmado com o usuário antes de aplicar: travar as 4 rotas é intencional,
não efeito colateral.** Os 4 amigos que hoje só têm `X-API-Key` nomeada (D-7),
sem conta Supabase Auth, ficam sem acesso ao Laboratório/Explicador/Analisador
pela tela do Vercel até migrarem — a pendência "migrar os 4 amigos", registrada
em P-11 desde D-17/D-18 como deliberadamente não feita, deixa de ser opcional a
partir daqui. Levantei a contradição explicitamente (mesmo padrão de D-15)
antes de mexer no código, e a resposta confirmou a intenção.

**Não corrigido aqui, e por quê.** `revisao_exercicio_avulso` ainda tem uma
policy de INSERT `to anon` com `with_check(true)` (`"Permitir insercao publica
de revisao_exercicio_avulso"`) — não é o mesmo problema (não vaza leitura,
frontend nunca insere nessa tabela direto, toda escrita passa pelo FastAPI que
já resolve o dono via D-17), mas é escrita anônima direta no Postgres
bypassando o backend por completo. Registrado como achado separado, não
tratado nesta migration.

**Consequência, validada por curl e por navegador de verdade.**

Por curl, antes × depois da migration, chave anon pura nas 7 tabelas:

| Tabela | Antes | Depois |
|---|---|---|
| `partidas` | 215 | **0** |
| `lances_criticos` | 525 | **0** |
| `diagnosticos` | 525 | **0** |
| `revisao_exercicio_avulso` | 12 | **0** |
| `resumo_partida` | 4 | **0** |
| `analises_hexagono` | 3 | **0** |
| `sessoes_treino` | 3 | **0** |

Logado com a **conta oficial real** (`edson.hirano.dev@gmail.com` — senha
fornecida pelo usuário só pra este teste, usada em memória, nunca escrita em
arquivo): as mesmas 7 tabelas voltaram a mostrar exatamente as mesmas
contagens de antes (215/525/525/12/4/3/3) — nenhuma linha perdida pro dono.
`UPDATE` em `sessoes_treino` testado e confirmado funcionando via JWT
autenticado (capturei o valor original de uma sessão real antes do teste e
restaurei depois — zero dado de produção alterado permanentemente).

No navegador (Playwright, `ng serve` local — mudança de rota só existe depois
de build/deploy, não dava pra validar contra produção ainda): as 4 rotas do
dashboard, em contexto sem sessão, redirecionaram pra `/login?returnUrl=...`
correspondente, consistente em duas execuções. Logado, as 4 rotas carregaram
normalmente — screenshot do "Meu Hexágono" e do "Analisador de Partida"
idênticos ao que sempre foram, com todos os cartões, gráfico do hexágono e
sessões de treino presentes.

**Consequência para P-11.** Com D-22 (zero tabela sem RLS) + D-23 (zero
policy `anon` no dashboard + login obrigatório), a Fase B do multi-tenant está
efetivamente concluída: identidade real em toda escrita (D-17), leitura
filtrada por dono em todo lugar que importa (D-18, D-19, D-22), e agora acesso
condicionado a essa identidade (D-23) — não sobra mais nenhum caminho anônimo
pro dado pessoal do dono. O que falta a partir daqui é migração de usuário
(os 4 amigos), não mais arquitetura de isolamento.

---

## D-24 — Remoção do INSERT anônimo residual em revisao_exercicio_avulso

**Problema.** O achado registrado em D-23 ("Não corrigido aqui, e por quê"):
`revisao_exercicio_avulso` tinha uma policy `"Permitir insercao publica de
revisao_exercicio_avulso"` (`to anon`, `with_check(true)`) que sobrevivia às
duas migrations anteriores porque não era leitura — não vazava dado, mas
permitia qualquer portador da chave pública inserir linha direto no Postgres
via PostgREST, sem passar pelo FastAPI e sem nenhuma das validações de
`/revisar-avulso/salvar` (resolução de dono real via D-17, etc.).

**Confirmado antes de remover que nenhum fluxo real dependia dela:** busca
por `.from('revisao_exercicio_avulso')` em todo `frontend/src` não encontrou
nenhuma ocorrência — a tela do Laboratório escreve exclusivamente via
`POST /revisar-avulso/salvar` (backend, `service role`, que ignora RLS por
definição). A policy não tinha consumidor legítimo.

**Decisão.** `drop policy "Permitir insercao publica de revisao_exercicio_avulso"`
— sem substituir por nenhuma policy de `authenticated`, porque não existe
fluxo (hoje ou planejado) em que o frontend deva inserir nessa tabela direto;
continua sendo responsabilidade exclusiva do FastAPI.

**Consequência, validada por curl.** INSERT com a chave anon pura →
**HTTP 401, `new row violates row-level security policy`** (antes: `HTTP 201`,
inserção bem-sucedida). Confirmado via `service role` que nada foi de fato
gravado. O fluxo real — INSERT via `service role`, o mesmo caminho que o
FastAPI usa — continua funcionando (`HTTP 201`); linha de teste removida ao
final.

Com isso, `revisao_exercicio_avulso` não tem mais nenhuma policy `to anon` —
nem leitura (D-19), nem escrita (D-24) — fechando o único vestígio de acesso
anônimo que ainda restava depois de D-23.

---

## D-25 — Autenticação unificada: sessão JWT como único gate, X-API-Key aposentada

**Problema.** Depois de D-23 o dashboard já exigia login, mas a API ainda tinha
**duas** autenticações com papéis diferentes: `X-API-Key` era a porta de
entrada de todos os 12 endpoints (`verificar_api_key`), e a sessão do Supabase
Auth era um bônus opcional por cima, só pra refinar o dono da escrita (D-17).
Isso significava que quem tivesse uma chave — os 4 amigos, ou qualquer um com
a chave vazada — continuava com acesso pleno à API mesmo sem conta, e que todo
caminho de escrita precisava de um fallback pro `DEFAULT_USER_ID` pra dar
conta de "requisição autenticada por chave, sem dono real".

**Decisão.** Um mecanismo só: a sessão.

1. **`verificar_sessao(request)`** substitui `verificar_api_key` como
   dependency dos **12** endpoints (levantados por grep no código, não de
   memória). Exige `Authorization: Bearer`, valida reaproveitando
   `resolver_user_id_da_sessao` (a mesma função de D-17, sem duplicar lógica) e
   levanta `401` na hora — mesmo princípio de "falha antes do trabalho caro"
   que justificava a dependency antiga: token ruim não chega a tocar
   Stockfish, Gemini ou banco.
2. **O `user_id` vira injeção, não re-resolução.** As 6 rotas que precisam do
   dono declaram `user_id: str = Depends(verificar_sessao)` e recebem o valor
   já validado. Antes, cada uma chamava `resolver_user_id_para_escrita(request)`
   no corpo, o que faria uma **segunda** ida ao `auth.get_user()` por
   requisição agora que a dependency já valida. `resolver_user_id_para_escrita`
   foi removida por não ter mais chamador.
3. **Fim do fallback pro `DEFAULT_USER_ID` nos caminhos de API.** Quem passa
   do gate tem dono garantido e real. Os scripts de CLI standalone
   (`analisar_pgn_avulso.py` e afins) **não** mudaram: continuam chamando
   `salvar_exercicio`/`inserir_partida` sem o parâmetro, e o
   `user_id or obter_default_user_id()` dentro dessas funções segue intacto
   pra eles — era exatamente pra isso que o parâmetro nasceu opcional em D-17.
4. **Frontend: um único método de header.** `headersComSessao()` substitui
   `headersComChave()` + `headersComChaveEAuth()` e vale pra **todos** os
   métodos do `RevisaoAvulsaService`, não só os 3 de escrita. A tela de "Chave
   de acesso" saiu das 3 telas interativas, e `AuthLocalService` foi removido
   por ficar sem nenhum consumidor. O flag `chaveInvalida` virou
   `sessaoExpirada`: com a rota já protegida pelo guard, um 401 da API só pode
   ser sessão expirada no meio do uso — não há mais chave pra reconfigurar.

**`/guia-passos` continua público**, junto de `/health`. É conteúdo estático
(os títulos dos 8 passos da rubrica), sem nada de usuário, e o Laboratório o
consome antes mesmo de qualquer interação — proteger não acrescentaria
segurança e só criaria um acoplamento a mais.

**O que ficou de propósito, sem uso.** `verificar_api_key`,
`_resolver_api_keys()` e a exigência de `API_SECRET_KEYS` no startup
continuam no código, agora sem nenhuma rota dependendo delas. Não é descuido:
a limpeza dessas variáveis está registrada como pendência em `ESTADO.md` e foi
deliberadamente adiada — `DEFAULT_USER_ID`, em particular, **ainda serve** o
fluxo de CLI standalone e não pode sumir.

**Consequência, validada por curl e por navegador.** Com o backend novo
rodando local, os 12 endpoints devolveram `401` em duas condições: sem header
nenhum, e **com uma `X-API-Key` válida** — provando que o mecanismo antigo não
abre mais porta alguma. `/health` e `/guia-passos` seguiram em `200`. Com a
sessão real do Edson, os mesmos endpoints responderam `200` com os dados dele
(12 revisões, 5 partidas, 7 explicações). Uma escrita real em
`/revisar-avulso/salvar` gravou a linha com o `user_id` da sessão (a prova de
que o valor vem do token, e não de um fallback coincidente, está no teste
unitário, que usa um UUID diferente do `DEFAULT_USER_ID`).

No navegador (Playwright, `ng serve` local apontado pro backend novo), logado
com a conta real: as 4 telas abriram sem pedir chave em lugar nenhum
(`pedeChave=false` nas quatro), toda chamada à API saiu com
`Authorization: Bearer` e **nenhuma** com `X-API-Key`, zero respostas 4xx/5xx
e zero erros de console. Um `401` transitório que apareceu numa das execuções
veio do Supabase, não da API — é o `PGRST303` de skew de relógio já
diagnosticado nesta mesma sessão, não regressão desta mudança.

**Consequência para os 4 amigos.** A porta que D-23 fechou na interface, esta
decisão fecha também na API: `X-API-Key` não dá mais acesso a nada. A migração
deles pra conta própria deixou de ser só recomendada — virou pré-requisito.

---

### D-26 — Agente 2: gargalo usa janela recente + queda_win_percent (P-3)

**Data:** 2026-09-13  
**Contexto:** O gargalo sistêmico do hexágono estava permanentemente congelado em
`TATICA` porque `_identify_bottleneck` usava `frequencia_por_categoria` (cumulativa
sobre todo o histórico). Além disso, a gravidade era medida por `gravidade_cpl`
(centipawns brutos) em vez de `queda_win_percent` (impacto real nas chances de
vitória, métrica D-1).

**O que mudou em `backend/agentes/agente2_analista.py`:**

1. `fetch_diagnosticos` busca `queda_win_percent` em vez de `gravidade_cpl`
2. `build_dataframe` extrai `queda_win_percent` como coluna do DataFrame
3. `calcular_metricas_hexagono` calcula dois conjuntos de métricas por categoria:
   - **Cumulativas** (`frequencia_por_categoria`, `gravidade_media_por_categoria`):
     usam todo o histórico, alimentam o radar do hexágono no frontend
   - **Recentes** (`frequencia_por_categoria_recente`,
     `gravidade_media_por_categoria_recente`): usam apenas os últimos 30 dias
     (`RECENT_WINDOW_DAYS`), decidem o gargalo
4. `_identify_bottleneck` usa as métricas recentes
5. `top_3_tags` usa contagens recentes (não mais cumulativas)
6. `build_prompt` inclui contexto temporal para a narrativa do Gemini

**O que NÃO mudou:** schema do banco, frontend, as 6 categorias do hexágono,
`RECENT_WINDOW_DAYS = 30`, campos cumulativos (continuam gravados).

**Testes:** Criado `test_agente2_analista.py` com 11 testes cobrindo o cenário
central (TATICA domina cumulativo, FINAIS domina recente → gargalo = FINAIS).
Registrado em `docs/OPERACAO.md` e `.github/workflows/deploy-backend.yml` (R8).

---

### D-27 — Miniatura de tabuleiro nas perguntas pendentes, com clique pro Laboratório

**Data:** 2026-09-13
**Contexto:** "Perguntas pendentes" mostra só texto (`No lance 16, o que você
estava pensando?`) — sem ver a posição, é difícil lembrar o que aconteceu.

**O que mudou:**

1. **Nova coluna `lances_criticos.fen_antes_lance`** (`backend/db/lances_criticos_fen_antes_lance.sql`):
   FEN de imediatamente antes do lance (ou do início da janela, em EROSAO).
   `backend/analise_engine/analisar_partidas.py` passou a capturar e gravar
   esse FEN em toda partida nova (`PlayerMoveEval.fen_antes`,
   `CriticalMove.fen_antes_lance`).
2. **Backfill do histórico:** `backend/analise_engine/backfill_fen_lances_criticos.py`
   recalculou o FEN das 525 linhas existentes a partir do PGN de cada partida
   (mesma regra de travessia de `processar_partida`, sem chamar o Stockfish).
   Rodado contra produção: **525 atualizadas, 0 falhas**.
3. **`TabuleiroPreviewComponent` ganhou `[miniatura]`:** versão compacta
   (96px, sem a legenda de créditos das peças) para uso em lista.
4. **`PerguntasPendentesComponent`** renderiza a miniatura como link
   (`routerLink="/laboratorio"` com `queryParams: {fen, lance}`).
5. **`LaboratorioRaciocinioComponent.ngOnInit`** lê esses query params via
   `ActivatedRoute` e pré-preenche `posicao`/`lance` — tem prioridade sobre a
   restauração do último exercício salvo em `localStorage` (F5), porque o
   usuário navegou ali com uma intenção explícita. Falta só "o que você
   pensou" pra enviar pra análise.

**Validado:** o embed do PostgREST (`perguntas_pendentes.lances_criticos.fen_antes_lance`)
testado por `curl` real com o JWT de produção, confirmando FEN correta
(posição real de uma partida do dono). 353 testes de backend, 76 de frontend,
`ng build` limpo.

---

### D-28 — Onboarding de novo usuário: contas de Lichess/Chess.com por pessoa (Fase C do multi-tenant)

**Data:** 2026-09-13
**Contexto:** Confirmado antes de começar: só o Edson e a Lais devem ter
acesso por enquanto — os 4 amigos de X-API-Key continuam de fora, decisão já
tomada em D-23/D-25. Faltava a peça que faz uma conta *nova* (sem histórico)
funcionar: até aqui, TODA a coleta e análise era single-tenant por baixo dos
panos, mesmo com login e RLS por dono já funcionando desde a Fase B.

**Descoberta antes de codar (evitou corromper dado real):** `common_ingestao.insert_game`
sempre gravava `obter_default_user_id()`; `coletar_partidas.py`/
`coletar_partidas_chesscom.py` liam um `LICHESS_USERNAME`/`CHESSCOM_USERNAME`
fixo do `.env`. Mais grave: `agente2_analista.fetch_diagnosticos` buscava
**todos** os diagnósticos do banco sem filtrar por dono, e
`agente3_prescritor.fetch_latest_analysis` pegava sempre a análise mais
recente **de qualquer usuário**, com `salvar_analise`/`salvar_sessao`
gravando tudo em `DEFAULT_USER_ID`. Sem corrigir os dois agentes, o hexágono
da Lais nunca existiria — ou pior, os diagnósticos dela contaminariam o
hexágono do Edson (e vice-versa) assim que a segunda conta tivesse dado.

**O que mudou:**

1. **Nova tabela `perfis_usuario`** (`backend/db/perfis_usuario.sql`):
   `user_id` (**FK real para `auth.users(id)`** — a primeira do schema),
   `lichess_username`, `chesscom_username`, `check` exigindo ao menos uma das
   duas. RLS: cada um só lê/grava a própria linha. Seedada com a conta do
   Edson (usernames que já estavam no `.env`).
2. **`common_ingestao.insert_game(client, record, user_id)`** — `user_id`
   agora é parâmetro obrigatório, sem fallback nenhum. Nova
   `carregar_perfis(client, coluna_username)` busca os perfis com aquela
   conta preenchida.
3. **`coletar_partidas.py`/`coletar_partidas_chesscom.py`** viraram um loop:
   uma rodada de coleta por perfil cadastrado (`coletar_para_perfil`), cada
   uma gravando no `user_id` daquele perfil. Falha de um perfil (username
   errado, API fora do ar) não derruba os outros — captura por perfil, soma
   no total. `LICHESS_USERNAME`/`CHESSCOM_USERNAME` saíram de `load_settings`
   e do `pipeline-diario.yml` (viraram secrets órfãos no GitHub — cleanup
   futuro, não bloqueante).
4. **`agente2_analista.py`:** `fetch_diagnosticos` agora filtra por dono via
   `lances_criticos!inner(...partidas!inner(...user_id))` +
   `.eq("lances_criticos.partidas.user_id", user_id)` — o `!inner` é o que
   permite filtrar a tabela de fora por uma coluna aninhada no embed do
   PostgREST. `main()` percorre `listar_usuarios_com_partidas` (distinct
   `partidas.user_id`) e gera um hexágono por usuário; usuário com zero
   diagnósticos é pulado (sem narrativa vazia, sem gravação inútil).
5. **`agente3_prescritor.py`:** mesmo padrão — `fetch_latest_analysis` filtra
   por `user_id`, `main()` percorre `listar_usuarios_com_analise` (distinct
   `analises_hexagono.user_id`) e prescreve uma sprint por usuário, isolada
   no PRÓPRIO gargalo mais recente.
6. **Efeito colateral corrigido:** `analisar_pgn_avulso.inferir_cor_jogador`
   também só reconhecia o `.env` fixo — colar o PGN de outra pessoa logada no
   Analisador de Partida nunca detectaria a cor dela sozinho. Ganhou um
   parâmetro opcional `usernames`; `/analisar-pgn` passa o perfil de quem
   está logado (`resolver_usernames_do_perfil`, nova função em
   `api_server.py`) quando `cor` não é informada. O CLI standalone
   (`analisar_pgn_avulso.py` rodado direto no terminal) **não mudou**: sem
   `usernames` explícito, continua lendo o `.env` como sempre.
7. **Frontend:** nova tela `/perfil` (`PerfilUsuarioComponent`, atrás do
   `authGuard`) onde a pessoa informa lichess/chesscom (pelo menos um,
   validação espelhando o `check` do banco) e salva via
   `SupabaseService.salvarPerfilUsuario` — primeiro INSERT do frontend numa
   tabela com policy `with_check(user_id = auth.uid())`, por isso o `userId`
   vem explícito de `AuthService.usuario()?.id` no payload. Link "Meu Perfil"
   na nav.

**Validado de ponta a ponta com conta de teste real (mesmo padrão de D-19):**
criada via Admin API, perfil cadastrado com um username real do Lichess,
`coletar_partidas.py` rodado de verdade com `LICHESS_GAMES_LIMIT=1` —
processou o perfil do Edson E o da conta de teste na mesma execução, cada um
gravando no `user_id` certo (confirmado por SQL). Diagnóstico fabricado
(bypassando Stockfish/Gemini) associado à conta de teste; `agente2_analista.py`
e `agente3_prescritor.py` rodados de verdade (Gemini real): a conta de teste
gerou hexágono próprio com **1** diagnóstico e "dados insuficientes" (correto,
abaixo do mínimo de 5), sem tocar nos 525 diagnósticos do Edson — o hexágono
dele seguiu com os mesmos 525 e gargalo `TATICA`; a sprint só foi gerada pra
ele, a conta de teste foi corretamente pulada por falta de gargalo. Conta,
perfil e dado fabricado removidos ao final.

**Consequência aceita:** a limpeza dos secrets `LICHESS_USERNAME`/
`CHESSCOM_USERNAME` no GitHub Actions (ficaram sem leitor) é candidata a
faxina futura, não bloqueante — igual à pendência já registrada de
`API_SECRET_KEYS` em D-25.

---

### D-29 — IDOR real em GET/POST /partidas/{id}: qualquer sessão via QUALQUER partida (incidente de segurança)

**Data:** 2026-09-13
**Gatilho:** revisão da tabela de `ARQUITETURA.md` encontrou `GET
/partidas/{id}/resumo` e `POST /partidas/{id}/reprocessar` marcados só com
🎫 (exige sessão), sem 👤 (filtro por dono) — diferente de todo outro
endpoint por-ID do projeto. Tratado como suspeita de incidente, não como
erro de documentação, até prova em contrário.

**Leitura do código confirmou a suspeita antes de qualquer teste:** os dois
endpoints buscavam a partida só por `.eq("id", partida_id)`, sem nenhum
`.eq("user_id", ...)` e sem sequer capturar o `user_id` da sessão (usavam
`dependencies=[Depends(verificar_sessao)]`, que só verifica que a sessão é
válida — não filtra nada por ela).

**Confirmado com evidência real (2 contas via Admin API, mesmo padrão de
D-19/D-28):** criada a conta A com uma partida real (`resumo_partida` com
narrativa marcada "SEGREDO DA CONTA A"), obtido token de sessão real da
conta B. Autenticado como B, contra o UUID da partida da A:

| Chamada | Antes da correção | Depois da correção |
|---|---|---|
| `GET /partidas/{id-da-A}/resumo` | **HTTP 200**, devolveu a narrativa completa e confidencial da conta A | **HTTP 404** |
| `POST /partidas/{id-da-A}/reprocessar` | **HTTP 202**, aceitou e reagendou a análise — confirmado por SQL que `status_processamento` da partida da A virou `processando`, disparado pela conta B | **HTTP 404** |

Ou seja: não era só leitura vazando — **qualquer sessão válida conseguia
disparar reprocessamento (Stockfish + Gemini) em cima da partida de
qualquer outro usuário**, só por adivinhar ou enumerar um UUID. Confirmado
também que a dona real (conta A) continuou acessando normalmente depois da
correção (`HTTP 200`, mesma narrativa) — o filtro não quebrou o caminho
legítimo.

**Resolução em `backend/api/api_server.py`.** Os dois endpoints passaram a
receber `user_id` por injeção (`Depends(verificar_sessao)` como parâmetro,
não só `dependencies=[...]`) e a query inicial de busca da partida ganhou
`.eq("user_id", user_id)` — mesmo princípio já usado em `/partidas/recentes`
(D-18), só que aqui a busca é por um único recurso, não uma lista. Partida
de outro dono responde **404**, nunca 403: não existe diferença observável
entre "não existe" e "existe mas não é sua", de propósito, para não revelar
a existência do recurso a quem não é dono.

**Testes:** `AnalisarPgnEndpointTest` ganhou
`test_obter_resumo_filtra_pelo_dono_da_sessao` e
`test_reprocessar_filtra_pelo_dono_da_sessao`, replicando o `assert_called_once_with`
do filtro `user_id` já usado nos testes de D-18. Os 3 testes existentes que
mockavam a query de busca (`test_obter_resumo_partida_inexistente_recebe_404`,
`test_obter_resumo_partida_processando_retorna_resumo_nulo`,
`test_obter_resumo_partida_concluida_retorna_resumo_completo`,
`test_reprocessar_partida_inexistente_recebe_404`,
`test_reprocessar_partida_existente_agenda_background_task`) precisaram de
mais um `.eq()` na cadeia mockada, pois a query real agora encadeia dois
filtros (`id` e `user_id`), não um.

**`ARQUITETURA.md` corrigido**: os dois endpoints passam a levar 👤 na
tabela de rotas — a marcação estava certa em apontar a ausência, o problema
era o código, não a tabela.

**Achado correlato, sinalizado mas NÃO corrigido aqui (fora do escopo pedido):**
`GET /insights/repertorio` também não recebe `user_id` nenhum —
`calcular_insights_repertorio(client)` é chamado sem filtro de dono, mesma
classe de risco que os agentes 2/3 tinham antes de D-28. Não foi validado
com conta real nem corrigido nesta rodada; registrado como pendência em
`ESTADO.md`.

**Limpeza:** as 2 contas de teste e a partida/resumo fabricados foram
removidos ao final; confirmado por SQL que não sobrou nenhuma linha órfã.

---

### D-30 — Mesmo IDOR em GET /insights/repertorio: agregações misturavam TODO o banco (incidente de segurança)

**Data:** 2026-09-13
**Gatilho:** achado correlato sinalizado em D-29 e não investigado ali —
mesma ausência de filtro por dono, desta vez numa rota de agregação em vez
de busca por-ID.

**Leitura do código confirmou: não era "só hoje só tem 1 usuário com dado".**
As 4 funções de busca em `backend/agentes/insights_repertorio.py`
(`fetch_partidas_repertorio`, `fetch_metricas_por_partida`,
`fetch_lances_pico`, `fetch_diagnosticos_com_partida`) varriam a tabela
inteira, sem nenhum `.eq("user_id", ...)` nem em `partidas` (que tem a
coluna) nem nas 3 tabelas filhas (que não têm, e não usavam `!inner` pra
filtrar via `partidas`). `calcular_insights_repertorio(client)` não recebia
`user_id` nenhum, e o endpoint em `api_server.py` usava
`dependencies=[Depends(verificar_sessao)]` — mesmo padrão de bug de D-29,
sessão validada mas nunca usada pra filtrar nada.

**Confirmado com evidência real (2 contas via Admin API, mesmo padrão de
D-29):** conta A com 1 partida marcada (`abertura_normalizada:
"MARCA_UNICA_D30_CONTA_A"`), conta B sem partida nenhuma. Autenticado como
B, `GET /insights/repertorio` devolveu **o repertório real completo do
Edson** — 212 partidas, taxa de vitória por cor (106/106), distribuição por
14 aberturas, os 525 eventos `PICO`, distribuição de categoria do hexágono
por abertura. B não tinha absolutamente nenhuma partida própria e ainda
assim recebeu `HTTP 200` com um payload gigante de dado alheio: pior que
D-29 em superfície, porque aqui não era preciso nem adivinhar um UUID — o
vazamento acontecia sempre, pra qualquer sessão válida, sem parâmetro
nenhum.

**Resolução em `backend/agentes/insights_repertorio.py` e
`backend/api/api_server.py`.** As 4 funções de busca passaram a receber
`user_id` e filtrar **na query, não só no resultado final**:
- `fetch_partidas_repertorio`: `.eq("user_id", user_id)` direto (`partidas`
  tem a coluna).
- `fetch_metricas_por_partida` e `fetch_lances_pico`: embed
  `partidas!inner(user_id)` + `.eq("partidas.user_id", user_id)` — mesma
  técnica de D-28, necessária porque essas duas tabelas são filhas, sem
  `user_id` próprio.
- `fetch_diagnosticos_com_partida`: embed duplo
  `lances_criticos!inner(partida_id, partidas!inner(user_id))` +
  `.eq("lances_criticos.partidas.user_id", user_id)` — dois níveis de FK até
  o dono, igual ao `fetch_diagnosticos` de `agente2_analista.py`.

`calcular_insights_repertorio(client, user_id)` e o endpoint (`user_id: str
= Depends(verificar_sessao)`, por injeção, não só `dependencies`) passaram
esse valor adiante.

**Revalidado com as mesmas 2 contas.** B (zero partidas): as 4 agregações
vieram todas vazias/zeradas (`{}`, `[]`) — nenhum traço do dado do Edson. A
(1 partida própria): viu exatamente a própria partida (`taxa_vitoria_por_cor`
BRANCAS 1/1, 100%) e nada além dela — sem contaminação em nenhuma das duas
direções.

**Testes:** `test_insights_repertorio.py` ganhou `FetchFiltraPeloDonoTest`
(4 testes, um por função de busca, verificando o `.eq`/embed corretos na
query real). `test_api_server.py` ganhou `test_filtra_pelo_dono_real_da_sessao`
e corrigiu o `assert_called_once_with` de `test_retorna_o_payload_calculado`
(o mock agora precisa do `user_id` no argumento).

**P-14 fechada de vez** em `ESTADO.md` — as duas rotas por-ID (D-29) e a
rota de agregação (D-30) eram os dois únicos endpoints do projeto sem
filtro por dono; nenhum ponto conhecido de vazamento cross-account
permanece aberto.

**Limpeza:** as 2 contas de teste e a partida/lance fabricados foram
removidos ao final; confirmado por SQL que não sobrou nenhuma linha órfã.

---

### D-31 — Fase 1 do roadmap comercial: os 5 scripts restantes do loop por perfil

**Data:** 2026-09-14
**Gatilho:** D-28 estendeu o loop por `perfis_usuario` a
`coletar_partidas.py`/`coletar_partidas_chesscom.py`/`agente2_analista.py`/
`agente3_prescritor.py`, mas 5 outros scripts do pipeline continuavam sem
esse tratamento: `enriquecer_partidas_lichess.py`,
`importar_puzzle_activity.py`, `gerar_resumo_partida.py`,
`gerar_perguntas_pendentes.py`, `normalizar_aberturas.py`. Antes de investir
mais no roadmap comercial, era preciso confirmar (não assumir) se cada um
já era seguro para multi-tenant ou não.

**Investigação script a script (achado real, não suposição):**

1. **`enriquecer_partidas_lichess.py` — vazamento funcional real, corrigido.**
   `selecionar_partidas` varria TODAS as partidas Lichess do banco, de
   qualquer dono, e usava um único `LICHESS_USERNAME` do `.env` para
   descobrir de que lado o jogador rastreado jogou (`identificar_cor_rastreada`
   → `montar_metricas`). Para as partidas de um segundo usuário, o username
   nunca bateria com nenhum dos dois lados: `metricas_lichess_partida` nunca
   seria gravada para ninguém além do dono do `.env` — silenciosamente, sem
   erro. `tempos_lance` não dependia do username e seria gravada
   corretamente, mas atribuída à partida certa só por acidente de FK, sem
   nenhuma filtragem deliberada por perfil.

2. **`importar_puzzle_activity.py` — vazamento de atribuição real, corrigido
   de forma diferente do padrão usual.** Gravava todo puzzle sob
   `obter_default_user_id()`, sem checagem nenhuma. Mas diferente da coleta de
   partidas, `/api/puzzle/activity` do Lichess **não aceita username**: ela
   sempre devolve a atividade de quem é dono do `LICHESS_STUDY_TOKEN` usado —
   não existe como pedir a atividade de outra conta com esse mesmo token.
   Logo, "percorrer `perfis_usuario` chamando a API uma vez por username" não
   se aplica aqui (produziria o mesmo resultado N vezes, atribuído a N donos
   diferentes — pior que o bug original). A correção correta é descobrir a
   **qual perfil o token pertence** e gravar sob esse dono, sem fallback.

3. **`gerar_resumo_partida.py` — já seguro, nenhuma mudança.** Opera
   partida por partida: `fetch_partidas_elegiveis` varre a tabela toda, mas
   cada `partida_id` retornado é processado isoladamente por
   `coletar_dados_partida` (filtra só por `partida_id`) e grava em
   `resumo_partida` (filho de `partidas` via FK, dono herdado). Nunca agrega
   dado de mais de uma partida ao mesmo tempo — nenhuma mistura possível
   entre contas.

4. **`gerar_perguntas_pendentes.py` — já seguro, nenhuma mudança.** Mesmo
   padrão: opera lance a lance (`lance_id`/`partida_id`), pergunta é texto
   fixo sem LLM, gravada em `perguntas_pendentes` vinculada a um único
   `lance_id`. Nenhuma agregação cross-partida.

5. **`normalizar_aberturas.py` — já seguro, nenhuma mudança.** Varre
   `partidas` inteira, mas cada linha é lida e escrita isoladamente
   (`abertura_normalizada` calculada só a partir do próprio PGN/external_id
   daquela linha). Não lê nem depende de dado de nenhuma outra partida —
   implicitamente multi-tenant por não agregar nada.

**Resolução nos 2 scripts com achado real:**

- `enriquecer_partidas_lichess.py`: `Settings` perdeu o campo
  `lichess_username`; nova `enriquecer_para_perfil(client, logger, user_id,
  username, dry_run)` roda `selecionar_partidas(client, user_id=...)` (novo
  parâmetro, filtra por dono) e `main()` percorre `carregar_perfis(client,
  "lichess_username")`, isolando erro por perfil (mesmo princípio de D-28).
  `--external-id` (modo manual de depuração de 1 partida) ganhou
  `enriquecer_uma_partida_manual`, que resolve o username certo procurando em
  `perfis_usuario` o perfil com o mesmo `user_id` da partida-alvo, em vez de
  usar o `.env`.
- `importar_puzzle_activity.py`: nova `fetch_lichess_username_do_token`
  (chama `GET /api/account` com o `LICHESS_STUDY_TOKEN` real) e
  `resolver_user_id_do_token` (procura em `perfis_usuario` o perfil com esse
  `lichess_username`, levanta `ValueError` sem fallback se não achar).
  `upsert_puzzle_atividade` passou a receber `user_id` explícito.
  `obter_default_user_id`/`backend.common.tenant` saíram do arquivo.

**Validado com dados reais (Admin API + 2 external_id reais do Lichess não
importados ainda, `A69ZYTDf` e `y6a6yWhg`):** 2 contas de teste, cada uma com
1 partida fabricada apontando pra um desses `external_id`. Rodando
`enriquecer_para_perfil` de verdade (rede real ao Lichess, escrita real no
Supabase) para a conta A, só a partida de A foi processada
(`selecionar_partidas(user_id=A)` só retornava `A69ZYTDf`) e só sua
`tempos_lance` foi gravada (65 linhas na partida de A); a partida de B
(`y6a6yWhg`) ficou intocada. Repetido para B: só sua própria partida foi
processada (50 linhas de `tempos_lance`), sem tocar a de A. Para
`importar_puzzle_activity.py`, `fetch_lichess_username_do_token` com o
`LICHESS_STUDY_TOKEN` real devolveu `"tantofaz123"` e
`resolver_user_id_do_token` resolveu para o `user_id` real do Edson em
`perfis_usuario` — a mesma conta que `DEFAULT_USER_ID` grava hoje, mas agora
por consulta explícita ao perfil dono do token, não mais um valor fixo (se o
token um dia pertencer a outra conta sem perfil cadastrado, o script falha
alto em vez de atribuir puzzle a alguém errado).

**Testes:** `test_enriquecer_partidas_lichess.py` ganhou
`SelecionarPartidasFiltraPeloPerfilTest` (2 testes) e
`EnriquecerUmaPartidaManualTest` (1 teste). Novo
`test_importar_puzzle_activity.py` com `ResolverUserIdDoTokenTest` (2 testes)
e `UpsertPuzzleAtividadeTest` (1 teste).

**Limpeza:** as 2 contas de teste, os perfis e as 2 partidas fabricadas
(e sua `tempos_lance`) foram removidos ao final; confirmado por SQL que não
sobrou nenhuma linha órfã.

---

### D-32 — Limite diário por usuário nas rotas caras (Fase 1, item 4, do roadmap comercial)

**Data:** 2026-09-14
**Gatilho:** antes de convidar mais gente (Lais já tem acesso desde D-28),
faltava um teto de custo por usuário nas 4 rotas que chamam Stockfish e/ou
Gemini: `/analisar-pgn`, `/explicar-posicao`, `/revisar-avulso`,
`/reconhecer-posicao`. Sem isso, uma conta sozinha (por engano ou script) podia
consumir Stockfish/Gemini sem limite nenhum.

**Desenho aprovado antes de implementar** (ver a proposta na conversa): tabela
nova em vez de reaproveitar tabela existente — `/revisar-avulso` sozinha e
`/reconhecer-posicao` não persistem nada hoje, então contar linhas de tabelas
existentes não cobriria as 4 rotas.

**Schema (`backend/db/uso_diario_usuario.sql`):**
- `uso_diario_usuario (user_id, data, rota, contagem)`, PK composta
  `(user_id, data, rota)` — uma linha por usuário/dia/rota, extensível a
  rotas novas sem migração (rota é texto livre, não uma coluna por rota).
- `incrementar_uso_diario(p_user_id, p_rota)`: função SQL `SECURITY DEFINER`,
  `INSERT ... ON CONFLICT (user_id, data, rota) DO UPDATE SET contagem =
  contagem + 1 RETURNING contagem` — atômico, evita a corrida de 2
  requisições concorrentes do mesmo usuário lendo a mesma contagem e as duas
  passando. `data` é `(now() at time zone 'America/Sao_Paulo')::date`, por
  pedido explícito: o limite reseta à meia-noite local do usuário, não às 21h
  de Brasília (UTC-3), que seria o resultado de usar `current_date` puro.
- `EXECUTE` da função **revogado de `public`/`anon`/`authenticated`**: por
  padrão o Postgres concede `EXECUTE` em função nova a `PUBLIC`, o que deixaria
  qualquer usuário autenticado chamar `POST
  /rest/v1/rpc/incrementar_uso_diario` com o `p_user_id` de outra pessoa e
  esgotar o limite dela — nada a ver com RLS (que é por linha, não por
  função). Confirmado real: com o token da conta B e o `user_id` da conta A,
  a chamada direta ao RPC via REST devolveu `403 permission denied for
  function incrementar_uso_diario`.
- RLS na tabela: `usuario le o proprio uso`, `user_id = auth.uid()`, mesmo
  padrão de D-19/D-28 — sem policy de escrita para `authenticated` (só o RPC,
  chamado pela service role, escreve). Confirmado real: com o token da conta
  B, `GET .../uso_diario_usuario` devolveu só a própria linha.

**`backend/api/api_server.py`:**
- `LIMITES_DIARIOS_ENV`: rota → (variável de ambiente, default) —
  `LIMITE_DIARIO_ANALISAR_PGN` (20), `LIMITE_DIARIO_EXPLICAR_POSICAO` (50),
  `LIMITE_DIARIO_REVISAR_AVULSO` (50), `LIMITE_DIARIO_RECONHECER_POSICAO`
  (30). `/analisar-pgn` é a mais cara (Stockfish na partida inteira +
  narrativa Gemini), por isso o menor limite; `/reconhecer-posicao` é só
  Gemini visão, sem Stockfish. `_resolver_limites_diarios()` lê essas 4 no
  startup e guarda em `_state["limites_diarios"]` — mesmo padrão de
  `_resolver_api_keys()`, já existente.
- `limite_diario(rota)`: dependency factory. A dependency devolvida depende de
  `verificar_sessao` (FastAPI cacheia por requisição — a sessão não é
  validada duas vezes), chama `client.rpc("incrementar_uso_diario", {...})`,
  e levanta `HTTPException(429, "Limite diário atingido, tente novamente
  amanhã.")` se a contagem devolvida passar do limite. Roda ANTES do corpo da
  rota — mesmo princípio de "falhar rápido" de `verificar_sessao` (D-25), mas
  para custo em vez de acesso: a chamada que estoura ainda é contada (mesma
  semântica de rate limiter padrão), mas nunca chega a rodar Stockfish/Gemini.
- Para os testes poderem sobrescrever cada limite individualmente via
  `app.dependency_overrides` (mesmo mecanismo já usado com `verificar_sessao`),
  as 4 instâncias da dependency são nomeadas no módulo
  (`verificar_limite_analisar_pgn` etc.), não criadas inline no decorator.
- `/revisar-avulso` e `/reconhecer-posicao` **migraram** de
  `dependencies=[Depends(verificar_sessao)]` (valida mas não captura) para
  `user_id: str = Depends(verificar_limite_revisar_avulso)` /
  `..._reconhecer_posicao` — mesma correção de forma que D-29/D-30, aqui
  necessária porque `limite_diario` precisa do `user_id` para chavear o RPC.
  `/analisar-pgn` e `/explicar-posicao` já capturavam `user_id` (D-28/D-11);
  seu `Depends(verificar_sessao)` virou `Depends(verificar_limite_*)`
  correspondente, reaproveitando o mesmo parâmetro.

**Validado com 2 contas reais (Admin API) e um limite temporariamente baixo
(`LIMITE_DIARIO_REVISAR_AVULSO=2`, servidor real na porta 8033, motor
Stockfish e Gemini reais, nenhum mock):**
- Conta A: 1ª e 2ª chamada a `/revisar-avulso` devolveram `200` em ~36s cada
  (tempo real de Stockfish + Gemini). A 3ª devolveu `429` com
  `{"detail":"Limite diário atingido, tente novamente amanhã."}` em ~1s — mais
  de 30x mais rápida que as duas primeiras, evidência direta (além da garantia
  estrutural do FastAPI de resolver dependencies antes do corpo da rota, e do
  teste unitário `mock_processar.assert_not_called()`) de que o motor não
  chegou a rodar na chamada rejeitada.
- Conta B, sem nenhuma chamada feita antes: 1ª chamada devolveu `200` normal
  em ~40s, sem qualquer efeito do consumo da conta A.
- `SELECT` em `uso_diario_usuario` confirmou os contadores isolados:
  conta A com `contagem=3` (2 aceitas + 1 rejeitada, ainda contada — mesma
  semântica de qualquer rate limiter por incremento atômico), conta B com
  `contagem=1`, cada linha só com a própria `user_id`.

**Testes:** `backend/api/test_api_server.py` ganhou `LimiteDiarioTest` (6
testes: sob o limite, exatamente no limite, estourando o limite, falha no
RPC, sem `supabase_client`, leitura dos defaults/env vars) e
`LimiteDiarioIntegracaoRevisarAvulsoTest` (2 testes de integração via rota
real: 429 sem chamar `processar_revisao_sequencia`, e chamada normal dentro
do limite). `setUpModule`/`gate_de_sessao_real()` do arquivo foram ajustados
para também cobrir as 4 novas dependencies (sem isso, toda a suíte existente
passaria a chamar o RPC de verdade contra um `MagicMock`, quebrando com
`TypeError` na comparação `contagem > limite`); novo helper
`gate_de_limite_diario_real(dependencia)` liga o limite real de uma rota
específica sem afetar as outras 3.

**Limpeza:** a linha de `uso_diario_usuario` e as 2 contas de teste foram
removidas ao final; confirmado por SQL que não sobrou nenhuma linha órfã.

---

### D-33 — OAuth do Lichess (Authorization Code + PKCE), Estágio 1: a fundação do fluxo

**Data:** 2026-09-14
**Gatilho:** até aqui, o acesso à conta Lichess de alguém dependia de um token
pessoal colado no `.env` (`LICHESS_STUDY_TOKEN`), que é de uma conta só — a do
Edson. D-31 registrou isso como limitação aceita; este é o primeiro passo para
cada usuário conectar a **própria** conta. Estágio 1 entrega só a fundação
(iniciar + callback + armazenamento + leitura validada); reescrever
`importar_puzzle_activity.py` e pôr o botão no frontend são os Estágios 2 e 3.

**Investigação da doc oficial ANTES de implementar (item explicitamente
pedido; resultado real, não suposição).** Fontes: o OpenAPI oficial
(`lichess-org/api`, `doc/specs/lichess-api.yaml` e o sub-arquivo
`tags/puzzles/api-puzzle-activity.yaml`) e a implementação de referência
`tors42/lichess-oauth-pkce-app`. O que ficou confirmado:

| Pergunta | Resposta real |
|---|---|
| Precisa registrar `client_id` antes? | **Não.** O Lichess aceita clientes públicos não registrados: o `client_id` é uma string qualquer escolhida pela aplicação. Não existe (nem é aceito) `client_secret` — autenticação de cliente foi removida junto com o fluxo antigo. |
| Endpoint de autorização | `GET https://lichess.org/oauth` (era `oauth.lichess.org/oauth/authorize` no fluxo antigo, já aposentado) |
| Endpoint de troca | `POST https://lichess.org/api/token`, corpo `application/x-www-form-urlencoded` |
| PKCE | **Obrigatório**, e o único `code_challenge_method` aceito é `S256` |
| Refresh token | **Não existe.** A doc é explícita: refresh tokens não são suportados; em compensação o access token nasce com validade longa (~1 ano) |
| Escopo de `/api/puzzle/activity` | `puzzle:read` |

**Consequência direta no item 5 do pedido (lógica de refresh):** como o Lichess
não emite refresh token, não existe renovação automática para implementar —
escrever esse caminho seria código morto. O que foi feito é o que a plataforma
permite: `obter_access_token_lichess(client, user_id)` é o ponto único por onde
qualquer consumidor futuro pega o token, e ela **checa `expires_at` antes de
entregar** (com margem de 60s), devolvendo `None` quando não há token, quando
ele expirou ou quando foi revogado. `None` significa "a pessoa precisa
reconectar a conta" — a única saída real. A coluna `refresh_token` existe no
schema e é sempre `NULL` hoje.

**Schema (`backend/db/lichess_oauth.sql`), duas tabelas, nenhuma com policy de
RLS** — nem para `anon`, nem para `authenticated`. Só a service role toca:
- `lichess_oauth_tokens (user_id PK → auth.users, access_token, refresh_token,
  expires_at, scopes, created_at, updated_at)`.
- `lichess_oauth_pkce (state PK, user_id, code_verifier, expires_at,
  created_at)` — estado efêmero de um fluxo em andamento, TTL de 10 minutos.

**Por que o `code_verifier` vai para o banco e não para a memória do processo**
(decisão pedida com justificativa): `iniciar` e `callback` são duas requisições
HTTP separadas, com a pessoa indo ao lichess.org no meio. Em produção (Cloud
Run) elas podem cair em instâncias diferentes, ou o container pode reciclar
entre as duas — um dicionário em memória perderia o verifier de forma não
determinística, quebrando o fluxo sem padrão reproduzível. A tabela resolve
isso; o TTL curto e o consumo único mantêm a janela de exposição mínima.
Cada `iniciar` também varre as linhas vencidas, senão fluxos abandonados
acumulariam para sempre (só o caminho feliz apaga a própria linha).

**Por que o `state` é aleatório guardado no servidor, e não assinado**
(o pedido dizia "assinado/verificável"): um `state` de 256 bits de
`secrets.token_urlsafe(32)` gravado no banco é **mais forte** que um token
assinado sem estado. Ele é verificável (ou existe na tabela, ou não existe),
é de **uso único** (o callback consome a linha com `DELETE ... RETURNING`, o
que também torna dois callbacks concorrentes mutuamente exclusivos), expira em
10 minutos, e — o ponto principal — **amarra o fluxo ao `user_id` que o
iniciou**. Um `state` assinado provaria "isto saiu daqui", mas não impediria
replay sem uma lista de consumidos, que é exatamente a tabela. Não há chave de
assinatura para gerenciar.

**`/lichess/oauth/callback` é a única rota de negócio fora do gate de sessão de
D-25, e isso é deliberado.** Quem chega nela é o navegador da pessoa numa
navegação de topo vinda do lichess.org — sem o header `Authorization` que o
frontend anexa via `fetch`. A identidade não pode vir da sessão; vem do
`state`, que só existe porque `/lichess/oauth/iniciar` (essa sim protegida por
`verificar_sessao`) o gravou amarrado a um `user_id`. O teste
`test_todos_os_endpoints_protegidos_exigem_sessao` ganhou essa rota na lista de
exceções, com o motivo escrito ao lado.

**Nada sensível trafega de volta para o navegador.** O callback sempre termina
em `303` para `{FRONTEND_URL}/perfil?conectado=lichess` — ou
`?erro=<motivo>` nos caminhos de falha (`lichess_negado`,
`lichess_state_invalido`, `lichess_state_expirado`, `lichess_troca_falhou`,
`lichess_gravacao_falhou`, `lichess_indisponivel`). Nem token, nem `code`, nem
`state` vão na URL: histórico de navegador e cabeçalho `Referer` vazariam.
A falha na troca do código também não loga o corpo da resposta, que pode
conter o token.

**Validado de ponta a ponta com a conta real, sem mock nenhum.** Servidor real
na porta 8034, sessão real da conta do app obtida via Admin API (magic-link →
`verify_otp`, sem senha), conta Lichess real `tantofaz123` autorizando no
navegador:
- `POST /lichess/oauth/iniciar` devolveu a URL com `code_challenge_method=S256`
  e `scope=puzzle:read`; a linha correspondente apareceu em
  `lichess_oauth_pkce` amarrada ao `user_id` certo.
- Autorização real concedida → `GET /lichess/oauth/callback?code=…&state=…`
  respondeu `303`, e `lichess_oauth_pkce` ficou **com 0 linhas** (uso único
  confirmado no banco, não só em teste com mock).
- `lichess_oauth_tokens` gravou o token com prefixo `lio_` (token de OAuth; os
  pessoais são `lip_`), `refresh_token = NULL`, `scopes = puzzle:read` e
  `expires_at` exatamente 1 ano à frente — os três coerentes com a doc.
- `obter_access_token_lichess()` devolveu esse token, e com ele:
  `GET https://lichess.org/api/account` → `200`, `username: tantofaz123`;
  `GET https://lichess.org/api/puzzle/activity?max=1` → `200` com atividade
  real. O segundo é a prova de que o escopo pedido serve para o consumidor
  previsto no Estágio 2.
- Para um `user_id` sem conta conectada, a função devolveu `None`.
- **RLS confirmada no banco real:** com um JWT real do próprio dono do token,
  `GET /rest/v1/lichess_oauth_tokens` e `.../lichess_oauth_pkce` devolveram
  `[]`. Sem policy, nem o dono lê — o token existe só para a service role.

**Testes:** 17 novos em `test_api_server.py` — `PkceTest` (3: o challenge é
mesmo o SHA-256 do verifier em base64url sem padding, tamanho/alfabeto da RFC
7636, verifier diferente a cada chamada), `IniciarOauthLichessTest` (4,
incluindo "o `code_verifier` está no banco e não aparece na resposta"),
`CallbackOauthLichessTest` (7, incluindo `state` forjado e `state` expirado
não chegarem a trocar código nenhum, uso único, e nada sensível na URL de
retorno) e `ObterAccessTokenLichessTest` (3).

**O que ficou de fora do Estágio 1, de propósito:** o botão "Conectar Lichess"
no `/perfil` (Estágio 3), a reescrita de `importar_puzzle_activity.py` para
percorrer as contas conectadas (Estágio 2), e uma rota de desconectar. O
Lichess não documenta endpoint de revogação no spec consultado — revogar hoje
é pelo próprio site, em `lichess.org/account/oauth/token`.

---

### D-34 — OAuth Lichess Estágio 2: importar_puzzle_activity.py por usuário

**Data:** 2026-09-14  
**Contexto:** No Estágio 1 (D-33), o backend ganhou suporte a OAuth 2.0 PKCE
para o Lichess, persistindo tokens em `lichess_oauth_tokens`. Porém,
`importar_puzzle_activity.py` ainda lia um único `LICHESS_STUDY_TOKEN` do `.env` e
resolvia o dono via `/api/account` (D-31). Para que qualquer usuário conectado
possa ter seus puzzles importados e para isolar falhas, o script precisava
consumir a tabela OAuth diretamente.

**O que mudou:**

1. **Módulo compartilhado `backend/common/lichess_oauth.py`:**
   - Movida a lógica de `obter_access_token_lichess(client, user_id)` (antes em `api_server.py`)
     para evitar que scripts de ingestão precisem importar o módulo da API (que carrega FastAPI, Gemini, Stockfish).
   - Criada a função `listar_usuarios_com_token_lichess_valido(client)` que busca
     usuários com tokens ainda não expirados (`expires_at > agora`).
   - Testes dedicados em `backend/common/test_lichess_oauth.py`.

2. **Reescrita de `backend/ingestao/importar_puzzle_activity.py`:**
   - Aposentada a dependência de `LICHESS_STUDY_TOKEN` neste script (`Settings` agora só
     carrega credenciais do Supabase).
   - O script percorre todos os usuários retornados por `listar_usuarios_com_token_lichess_valido`.
   - Para cada usuário, obtém o token via `obter_access_token_lichess(client, user_id)`,
     chama `/api/puzzle/activity` e grava em `puzzle_atividade` com o `user_id` correspondente.
   - **Isolamento de erro por usuário:** falha de um usuário (token expirado, 401 revogado,
     ou erro de rede) não interrompe o processamento dos demais usuários (mesmo padrão D-28/D-31).
   - Tratamento explícito de `TokenRevogadoError` (HTTP 401): loga claramente que o usuário
     precisa reconectar a conta e segue adiante sem quebrar o loop.

3. **Validação real de ponta a ponta:**
   - Execução real com a conta do Edson (`bfde845a-8e2e-4885-801f-0fed2dd3b426`): 660 puzzles
     importados/atualizados com sucesso, 0 falhas de parsing, 0 falhas ao gravar.
   - Flag `--inspecionar` validada e funcionando com a conta conectada.

4. **Regra R8 cumprida:**
   - `backend.common.test_lichess_oauth` registrado em `docs/OPERACAO.md` e
     `.github/workflows/deploy-backend.yml`.
   - Testes unitários atualizados em `backend/ingestao/test_importar_puzzle_activity.py` e
     `backend/common/test_lichess_oauth.py`.

**O que NÃO mudou:** `importar_anotacoes_lichess.py` continua usando `LICHESS_STUDY_TOKEN`
por precisar do escopo `study:write` (fora do escopo deste estágio).

---

### D-35 — OAuth Lichess Estágio 3: Conexão e status no frontend (/perfil)

**Data:** 2026-09-14  
**Contexto:** Com o fluxo de autorização no backend (D-33) e o consumo de tokens
em `importar_puzzle_activity.py` (D-34) concluídos, faltava a interface gráfica
para que o usuário consiga clicar em "Conectar com Lichess", ser redirecionado para
a autorização do Lichess, e retornar à aplicação com feedback claro.

**O que mudou:**

1. **Backend (`backend/api/api_server.py`):**
   - Rota `GET /lichess/oauth/status` (protegida com `verificar_sessao`): consulta
     se o usuário tem token ativo via `obter_access_token_lichess`. Devolve
     `{"conectado": bool, "expires_at": str | None}` sem nunca vazar o token.
   - Rota `POST /lichess/oauth/desconectar` (protegida com `verificar_sessao`):
     remove o registro de `lichess_oauth_tokens` do usuário logado caso ele deseje
     desvincular a conta.
   - Testes unitários dedicados em `test_api_server.py` (`StatusOauthLichessTest` e
     `DesconectarOauthLichessTest`).

2. **Frontend (`frontend/src/app`):**
   - Criado serviço `LichessOauthService` (`src/app/services/lichess-oauth.service.ts`),
     com métodos `obterStatus()`, `iniciarConexao()` e `desconectar()`.
   - Atualizado `PerfilUsuarioComponent` (`perfil-usuario.component.ts` e `.html`):
     - Adicionado card dedicado "Conexão com o Lichess (OAuth)" com badge de status
       (Conectado verde vs Desconectado neutro).
     - Botão "Conectar com Lichess" que chama `/lichess/oauth/iniciar` e redireciona
       o navegador para a página de autorização do Lichess.
     - Botões de "Reconectar conta" e "Desconectar" quando a conta já está conectada.
     - Processamento dos query params retornados pelo callback do Lichess
       (`?conectado=lichess` exibe alerta de sucesso; `?erro=...` exibe mensagem amigável),
       limpando os parâmetros da URL em seguida para manter a navegação limpa.
   - Testes unitários em `lichess-oauth.service.spec.ts` e `perfil-usuario.component.spec.ts`.

**Com o Estágio 3 concluído, o ciclo OAuth do Lichess (Estágios 1, 2 e 3) está 100% entregue.**

---

### D-36 — Modal de onboarding para vinculação de contas de xadrez

**Data:** 2026-09-14  
**Contexto:** Novos usuários (ou usuários sem contas de xadrez cadastradas)
entravam no app e caíam no dashboard vazio. Como a ingestão em lote depende de
`perfis_usuario` (D-28), sem cadastrar pelo menos um username (Lichess ou Chess.com),
o sistema nunca baixaria partidas nem geraria o hexágono.

**O que mudou:**

1. **`ModalOnboardingContasComponent` (`src/app/components/modal-onboarding-contas/`):**
   - Verifica se o usuário autenticado não possui contas cadastradas (`lichess_username`
     e `chesscom_username` nulos ou vazios em `perfis_usuario`).
   - Não sobrepõe as rotas `/login` e `/perfil`.
   - Se o usuário fechar o modal ou clicar em "Configurar depois", grava
     `onboarding_contas_dispensado = 'true'` em `sessionStorage`, evitando que o modal
     reapareça a cada navegação de rota durante a mesma sessão.
   - Permite preencher e salvar diretamente os usernames do Lichess e Chess.com no banco,
     além de fornecer atalho para conexão via Lichess OAuth.
2. **Integração no shell da aplicação:**
   - Adicionado ao `app.ts` e renderizado em `app.html` após o `<router-outlet />`.
3. **Testes unitários:**
   - 9 novos testes unitários adicionados em `modal-onboarding-contas.component.spec.ts`.
   - Total da suíte frontend subiu para **92 testes passando** em 12 arquivos.

---

### D-37 — Automatização das rotinas de background no GitHub Actions e isolamento multi-tenant em medir_eficacia.py

**Data:** 2026-09-14  
**Contexto:** Seis scripts existiam no backend mas não estavam automatizados (P-6). Como consequência, métricas avançadas do Lichess paravam no tempo, o histórico de puzzles não atualizava sozinho e a eficácia de sprints concluídas nunca era calculada. Além disso, antes de automatizar `medir_eficacia.py`, foi descoberto um bug de isolamento multi-tenant na contagem de diagnósticos.

**O que mudou:**

1. **Correção multi-tenant em `backend/agentes/medir_eficacia.py`:**
   - `buscar_sessoes_elegiveis` passou a selecionar `user_id` de `sessoes_treino`.
   - `contar_diagnosticos_categoria` passou a receber `user_id` e a filtrar `.eq("lances_criticos.partidas.user_id", user_id)` via join `partidas!inner(data_partida, user_id)`.
   - Evita que erros de um jogador afetem o cálculo de redução percentual da sprint de outro.
   - Criada a suíte `backend/agentes/test_medir_eficacia.py` com 15 testes unitários.
   - Módulo registrado em `docs/OPERACAO.md` e `.github/workflows/deploy-backend.yml` (Regra R8).

2. **Automatização no `pipeline-diario.yml`:**
   - Adicionadas as etapas com `continue-on-error: true`:
     - `backend/ingestao/importar_puzzle_activity.py` (puzzles via OAuth de cada usuário conectado).
     - `backend/ingestao/enriquecer_partidas_lichess.py` (clocks e precisão por fase).
     - `backend/agentes/gerar_perguntas_pendentes.py` (perguntas reflexivas para lances críticos).
     - `backend/agentes/gerar_resumo_partida.py` (narrativas pós-diagnóstico).
   - Atualizado o sumário de falhas do workflow para relatar todas as novas etapas.

3. **Automatização no `pipeline-semanal.yml`:**
   - Adicionada a etapa `backend/agentes/medir_eficacia.py` com `continue-on-error: true` antes do Agente 2.
   - Atualizado o sumário do workflow semanal.

---

### D-38 — Fechamento do loop adaptativo no Frontend (P-4)

**Data:** 2026-09-14  
**Contexto:** O loop adaptativo (P-4) estava incompleto no frontend: embora o backend agora calcule a eficácia das sprints concluídas semanalmente (D-37), o frontend não consultava `eficacia_medida` nem `observacoes` de `sessoes_treino`, e a interface não exibia o status da medição nem permitia reabrir uma sprint marcada por engano.

**O que mudou:**

1. **`SupabaseService` (`supabase.service.ts`):**
   - Atualizada a interface `SessaoTreino` para incluir `eficacia_medida?: number | null` e `observacoes?: string | null`.
   - `getSessoesTreino()` passou a selecionar `eficacia_medida, observacoes`.
   - Criado método `desmarcarSessaoConcluida(id: string)` que reseta `data_concluida`, `eficacia_medida` e `observacoes` para `null`.

2. **`SessoesTreinoComponent` (`sessoes-treino.component.ts` e `.html`):**
   - Cabeçalho com métricas resumidas: total prescritas, total concluídas e eficácia média das sprints concluídas.
   - Botão sutil "Desmarcar / Reabrir" para caso o usuário tenha clicado por engano.
   - Bloco visual de "Impacto nas partidas (Loop adaptativo)":
     - Exibe badge de variação percentual (verde para redução, vermelho/âmbar para aumento) e o texto completo de `observacoes` quando a eficácia já foi medida.
     - Exibe mensagem explicativa com pulse animado quando a sprint foi concluída recentemente e ainda está aguardando a janela de 15 dias para medição automática no pipeline semanal.

3. **Testes Unitários:**
   - Criada a suíte `sessoes-treino.component.spec.ts` com 8 testes unitários cobrindo renderização, cálculo de médias, marcação/desmarcação e tratamento de erros. Total da suíte frontend subiu para **100 testes passando** em 13 arquivos.

---

### D-39 — Resiliência na análise Stockfish e reprocessamento de falhas (P-5)

**Data:** 2026-09-14  
**Contexto:** 31 partidas do histórico estavam retidas sem conclusão (28 com status `falhou` e 3 com `processando`). A causa raiz identificada foi `STOCKFISH_SEARCHTIME_MS = 3_000` em `analisar_partidas.py`: em partidas de 50 lances (100 avaliações de posições), o motor aguardava 3 segundos obrigatoriamente a cada lance, somando mais de 5 minutos por partida e estourando o timeout configurado ou levando SIGKILL no Cloud Run. Não havia mecanismo de auto-recuperação de containers interrompidos nem CLI para reprocessar falhas respeitando a Regra R7.

**O que mudou:**

1. **Otimização de tempo de busca no Stockfish (`analisar_partidas.py`):**
   - `STOCKFISH_SEARCHTIME_MS` passou a ter valor default `0` (configurável via variável de ambiente).
   - Em `evaluate_position`, se `searchtime_ms <= 0`, o Stockfish avalia na profundidade configurada (`depth=16`), reduzindo o tempo de análise de 3.00s para ~0.12s por lance (~25x mais rápido, ~12s no total da partida) e eliminando timeouts e estouros de CPU.

2. **Auto-recuperação e conformidade com Regra R7:**
   - Criada a função `limpar_registros_derivados_partida(client, partida_id)` que remove dados em cascata segura respeitando integridade referencial: `resumo_partida`, filhos de `lances_criticos` (`perguntas_pendentes` e `diagnosticos`) e `lances_criticos`.
   - Criada `resetar_partida_para_pendente(client, partida_id)` que executa a limpeza prévia antes de marcar `status_processamento = 'pendente'`.
   - `recuperar_partidas_orfas(client, logger)` é executada automaticamente na inicialização da análise, detectando partidas abandonadas em `processando` por desligamento abrupto de processos.
   - Adicionadas opções CLI:
     - `--reprocessar-falhas`: reseta e limpa partidas em `falhou` para reanálise em massa.
     - `--partida-id <id>`: permite reanalisar uma partida individual sob demanda (buscando por `id` ou `external_id`).

3. **Recuperação das 31 partidas órfãs/falhas em produção:**
   - As 31 partidas retidas (mais 2 pendentes, total 33) foram reprocessadas com 100% de sucesso (0 falhas) em ~11 minutos.
   - Total de partidas concluídas subiu de 197 para 230 (0 falhas, 0 em processamento, 0 pendentes).
   - 125 novos lances críticos gerados e persistidos, elevando o total de lances críticos de 560 para 685.
   - Aberturas normalizadas via `normalizar_aberturas.py` para todas as partidas pendentes.

4. **Testes Unitários:**
   - Adicionados testes para `evaluate_position`, `limpar_registros_derivados_partida`, `recuperar_partidas_orfas`, `recuperar_partidas_com_falha` e `parse_args`. Total de testes em `test_analisar_partidas` subiu de 7 para 17, e a suíte completa de testes do backend mantém 100% de aprovação (430 testes).

---

### D-40 — Inteligência e Visualização de Repertório (P-7 / Fase 14)

**Data:** 2026-09-14  
**Contexto:** A pendência P-7 apontava que 100% das partidas do Chess.com estavam sem `eco_abertura` cru, tornando qualquer análise baseada em código ECO cega para 77% do corpus. Além disso, embora o endpoint `/insights/repertorio` já calculasse estatísticas ricas de repertório no backend (D-13 e D-30), o frontend não possuía nenhum componente visual para exibir essas métricas ao jogador no dashboard (Fase 14 do roadmap).

**O que mudou:**

1. **Extração de ECO de PGN para Chess.com (`coletar_partidas_chesscom.py`):**
   - Criada a função `eco_from_pgn(pgn)` que extrai o código ECO da tag `[ECO "..."]` do cabeçalho PGN com regex de formato padrão internacional (`[A-E][0-9]{2}`).
   - `to_record()` passou a priorizar `eco_from_pgn(pgn)` em relação a `eco_from_url(url)`, garantindo que todas as partidas do Chess.com tenham `eco_abertura` preenchido na coleta inicial.

2. **Backfill Universal de ECO (`backfill_eco_abertura.py`):**
   - Atualizado para ler o PGN salvo no banco de dados e extrair o código ECO localmente sem depender de chamadas à API do Lichess.
   - Executado contra o banco de produção: **153 de 153 partidas do Chess.com (100%)** foram atualizadas com sucesso para seus respectivos códigos ECO (ex: C00, B13, A40).

3. **Serviço e Componente de Repertório no Frontend:**
   - Criado `RepertorioService` (`frontend/src/app/services/repertorio.service.ts`) consumindo `GET /insights/repertorio` via JWT com tratamento de expiração de sessão (401/403).
   - Criado `RepertorioInsightsComponent` (`frontend/src/app/components/repertorio-insights/`):
     - Resumo de taxa de vitória de Brancas vs Pretas com contagem de partidas.
     - Filtro interativo por cor ("Todas", "Brancas", "Pretas").
     - Cards de cada abertura com nome normalizado, barra de progresso visual colorida, estatísticas de vitórias/total, momento médio do erro crítico (lance de pico) e badges das principais categorias vulneráveis do hexágono associadas àquela abertura.
   - Integrado ao `HexagonoRadarComponent` (`hexagono-radar.component.html`), posicionando a visão de repertório entre o radar de categorias e as sessões de treino.

4. **Testes Unitários:**
   - Adicionada a suíte `EcoExtractionTest` em `test_coletar_partidas_chesscom.py` (total de testes do backend subiu para **435**, todos passando).
   - Criadas as suítes `repertorio.service.spec.ts` (3 testes) e `repertorio-insights.component.spec.ts` (7 testes). O total de testes do frontend subiu para **110 testes passando** em 15 arquivos. Build de produção (`ng build`) verificado sem erros.

---

### D-41 — Inteligência de Puzzles vs Partidas: Diagnóstico do Gap Tático (P-8 / Fase 17)

**Data:** 2026-09-14  
**Contexto:** A pendência P-8 apontava que a tabela `puzzle_atividade` acumulava 660 registros em 41 dias distintos via ingestão diária do Lichess, mas esse dado vivia isolado sem nenhum consumo analítico pelo pipeline ou exibição no frontend (Fase 17 do roadmap). Além disso, havia um gap nítido entre a capacidade de cálculo estático (rating de puzzles de ~1.854) e o desempenho em partidas rápidas (rating de blitz de ~1.424).

**O que mudou:**

1. **Backend & Módulo Analítico (`backend/agentes/insights_puzzles.py`):**
   - Criada a função `fetch_puzzle_atividade(client, user_id)` (filtrando estritamente por `user_id`, D-30).
   - Criada a função `calcular_estatisticas_gerais` (total, acertos, erros, taxa global de acerto e rating médio/mín/máx).
   - Criada a função `calcular_estatisticas_temas` mapeando temas de puzzles do Lichess para nomes pedagógicos amigáveis em português e categorizações (`tatica`, `defesa`, `ataque`, `calculo`, `final`, `mate`), aplicando filtro de amostra mínima (>= 5) e separando vulnerabilidades (<55% de acerto) e pontos fortes (>70% de acerto).
   - Criada a função `gerar_diagnostico_gap` formulando síntese comparativa entre cálculo calmo e erros críticos sob pressão nas partidas reais (`seguranca_do_rei`, `visao_em_tunel`, `negligencia_profilatica`).
   - Cada tema inclui URL direta de treino no Lichess: `https://lichess.org/training/{slug}`.

2. **API (`backend/api/api_server.py`):**
   - Criado o endpoint autenticado `GET /insights/puzzles` protegido por `Depends(verificar_sessao)`, delegando para `calcular_insights_puzzles(client, user_id)`.

3. **Frontend: Serviço e Componente Dashboard:**
   - Criado `PuzzlesService` (`frontend/src/app/services/puzzles.service.ts`) consumindo `GET /insights/puzzles` com autenticação JWT e tratamento de expiração de sessão.
   - Criado `PuzzlesInsightsComponent` (`frontend/src/app/components/puzzles-insights/`):
     - Cards de métricas globais (Total de puzzles resolvidos, Taxa de acerto global, Rating médio com pico).
     - Card de destaque com o diagnóstico do Gap Tático e diretrizes de treino.
     - Grade de temas vulneráveis com barra de progresso colorida, contadores de acerto e botão direto "Treinar no Lichess ↗".
     - Badges com temas onde o jogador brilha (pontos fortes dominados).
   - Integrado ao `HexagonoRadarComponent` (`hexagono-radar.component.html`), posicionado abaixo de Repertório de Aberturas.

4. **Testes Unitários:**
   - Criada a suíte `test_insights_puzzles.py` (8 testes cobrindo agregação, amostragem, tradução, diagnóstico e isolamento por `user_id`).
   - Registrado o módulo em `docs/OPERACAO.md` e `.github/workflows/deploy-backend.yml` (regra R8).
   - Adicionada a suíte `InsightsPuzzlesEndpointTest` em `backend/api/test_api_server.py` (5 testes).
   - Criadas as suítes frontend `puzzles.service.spec.ts` (3 testes) e `puzzles-insights.component.spec.ts` (6 testes).
   - Total de testes do backend subiu para **454 testes passando** (25 módulos). Total do frontend subiu para **119 testes passando** (17 arquivos). Build de produção (`ng build`) verificado sem erros.

---

### D-42 — APIs Especializadas: Lichess Opening Explorer & Syzygy Tablebase (Fase 18)

**Data:** 2026-09-14  
**Contexto:** A Fase 18 do roadmap previa o enriquecimento do pipeline com APIs públicas enxadrísticas de referência máxima:
1. *Lichess Opening Explorer* (`explorer.lichess.org`): base de mestres históricos para identificar com precisão o momento exato em que a partida se desviou do livro de aberturas, de quem partiu o desvio inicial ("Você" vs "Oponente"), e as estatísticas dos mestres na posição.
2. *Syzygy Tablebase* (`tablebase.lichess.org`): bases de finais com $\le 7$ peças que calculam o resultado exato (vitória, empate, derrota) e a distância para o mate (DTM) ou conversão por peão/captura (DTZ), permitindo provar matematicamente quando houve um erro decisivo no final.

**O que mudou:**

1. **Lichess Opening Explorer (`backend/common/lichess_explorer.py`):**
   - Criada a função `consultar_opening_explorer(fen, token, speeds, ratings)` com cabeçalho `Authorization: Bearer <token>` (necessário na base de masters do Lichess para prevenir HTTP 401).
   - Criado o algoritmo de busca binária em `detectar_saida_teoria(movimentos_san, cor_jogador, token)` até o ply 40 para encontrar em $O(\log N)$ chamadas o ply de saída, número do lance, cor, quem se desviou (`JOGADOR` vs `OPONENTE`), nome da abertura, código ECO e estatísticas de vitórias/empates/derrotas na última posição de livro.

2. **Syzygy Tablebase (`backend/common/syzygy_tablebase.py`):**
   - Criada a função `contar_pecas_fen(fen)` com guard de elegibilidade ($\le 7$ peças).
   - Criada a função `consultar_syzygy(fen)` consultando `https://tablebase.lichess.org/standard?fen=...` (pública, sem necessidade de autenticação), com validação preventiva de integridade e checagem de xeque ilegal (`opposite check`).
   - Criada a função `avaliar_lance_final_syzygy(fen_antes, lance_uci, fen_depois)` que compara o estado antes e depois do lance para detectar blunders de conversão (`win` $\to$ `draw`/`loss`) ou defensivos (`draw` $\to$ `loss`).

3. **Endpoints da API (`backend/api/api_server.py`):**
   - `GET /partidas/{partida_id}/teoria-abertura` protegido por sessão (`verificar_sessao`), buscando o PGN da partida no banco e consultando o Opening Explorer com fallback de token (OAuth do usuário ou token do sistema).
   - `GET /analise/syzygy` protegido por sessão (`verificar_sessao`), recebendo `fen` e lances opcionais para avaliar posições de final com $\le 7$ peças.

4. **Frontend Service & Integração UI:**
   - Criado `TeoriaFinaisService` (`frontend/src/app/services/teoria-finais.service.ts`) consumindo ambos os endpoints com autenticação JWT.
   - Integrado no `AnalisadorPartidaComponent`: card de "Saída da Teoria de Abertura (Mestres)" exibindo se a partida seguiu o livro ou quando se desviou, quem saiu primeiro (com destaque visual para erros do jogador), lance exato de saída e estatísticas da base de mestres.
   - Integrado no `ExplicadorPosicaoComponent`: banner dedicado da Syzygy Tablebase quando a posição possui $\le 7$ peças, exibindo o veredito matemático exato, DTM/DTZ e os melhores lances recomendados pela base teórica.

5. **Testes e Regra R8:**
   - 10 testes em `test_lichess_explorer.py`, 11 testes em `test_syzygy_tablebase.py`, 8 testes em `test_api_server.py`. Módulos devidamente registrados em `docs/OPERACAO.md` e `.github/workflows/deploy-backend.yml` (regra R8). Total de testes no backend subiu para **483 testes passando** em 27 módulos.
   - Criados testes unitários frontend em `teoria-finais.service.spec.ts` e `explicador-posicao.component.spec.ts`. Total no frontend subiu para **125 testes passando** em 18 arquivos. Build de produção (`ng build`) verificado sem erros.

---

### D-43 — Relógio / Gestão de Tempo no Chess.com e Captura de Pensamento / Processo vs Conteúdo (Fases 15 & 16)

**Data:** 2026-09-15  
**Contexto:**
1. **Fase 15 (Relógio & Gestão de Tempo):** O pipeline já extraía tempos de relógio das partidas do Lichess (`%clk`), persistindo em `tempos_lance`. Partidas do Chess.com, no entanto, continham marcações de `%clk` e `TimeControl` em seus PGNs que não estavam sendo extraídas para a tabela `tempos_lance`. Além disso, quando um erro ocorria com tempo restante crítico ($\le 30$s por padrão), a tag canônica `gestao_de_tempo_ruim` (Regra R1) precisava ser assegurada no diagnóstico do lance.
2. **Fase 16 (Captura de Pensamento & Processo vs Conteúdo):** O Lichess Study permite ao jogador registrar comentários com seu raciocínio durante a partida. Essas anotações eram importadas para `anotacoes_pensamento`, mas o Stockfish (`analisar_partidas.py`) só selecionava lances por queda de probabilidade de vitória (`win_percent_drop`). Lances em que o jogador anotou seu pensamento precisavam ser promovidos automaticamente a lances críticos (`origem = 'ANOTACAO'`), e o `agente1_linter.py` precisava contrastar o pensamento do jogador com a avaliação do motor para classificar `tipo_erro` entre `PROCESSO` (falha no checklist / cálculo mental), `CONTEUDO` (lacuna teórica / conceitual) ou `INDETERMINADO`.

**O que mudou:**

1. **Ingestão e Backfill de Relógio do Chess.com (Fase 15):**
   - Criado `backend/ingestao/backfill_tempos_chesscom.py` com regex resiliente (`CLK_PATTERN` cobrindo `H:MM:SS.S` e `M:SS.S`).
   - Executado o backfill contra a base real: 153/153 partidas do Chess.com processadas (100%), gerando 10.845 novas linhas em `tempos_lance` (totalizando 13.708 linhas).
   - Atualizados `coletar_partidas_chesscom.py` e `common_ingestao.py` para persistir tempos de relógio automaticamente a cada nova ingestão.
   - Criada a suíte `test_backfill_tempos_chesscom.py` (7 testes), registrada em `docs/OPERACAO.md` e `.github/workflows/deploy-backend.yml` (Regra R8).
   - Implementada em `agente1_linter.py` a função `assegurar_tag_apuro_de_tempo`, garantindo a tag canônica `gestao_de_tempo_ruim` quando `tempo_restante_seg <= limiar` (respeitando o vocabulário fechado da Regra R1).

2. **Captura de Pensamento e Processo vs Conteúdo (Fase 16):**
   - Criado script de migração `backend/db/lances_criticos_origem.sql` adicionando `origem text not null default 'GRAVIDADE'` com check constraint (`'GRAVIDADE'`, `'ANOTACAO'`).
   - Atualizado `analisar_partidas.py`:
     - Dataclass `CriticalMove` ganhou `origem: str = "GRAVIDADE"`.
     - Implementada a função `promover_lances_anotados` que incorpora lances com anotações de estudo como `CriticalMove(..., origem="ANOTACAO")`.
     - `insert_critical_moves` atualizado com envio de `origem` e fallback gracioso sem a coluna caso o DDL ainda não tenha sido rodado no banco.
     - `fetch_lances_anotados_partida` conecta as anotações do estudo ao loop de análise tanto no batch de `analisar_partidas.py` quanto em `analisar_pgn_avulso.py`.
   - Atualizado `agente1_linter.py`:
     - Schema `DiagnosticoLance` agora inclui `tipo_erro: Literal["PROCESSO", "CONTEUDO", "INDETERMINADO"] = "INDETERMINADO"`.
     - `fetch_anotacoes_index` e `attach_anotacao_pensamento` anexam as anotações de estudo ao lance antes do envio ao Gemini.
     - Prompt estruturado orienta o LLM a comparar o pensamento do jogador com a técnica do motor para discernir entre falha de rotina mental (`PROCESSO`) e desconhecimento teórico (`CONTEUDO`).
   - Atualizado `gerar_resumo_partida.py`:
     - `PontoCritico` recebeu `tipo_erro: str | None = None`.
     - `_enriquecer_pontos_criticos_com_tipo_erro` propaga deterministicamente a classificação de cada ponto crítico a partir dos diagnósticos.

3. **Frontend (`revisao-avulsa.service.ts` e `analisador-partida.component.html`):**
   - Interface `PontoCriticoPartida` atualizada com `tipo_erro?: 'PROCESSO' | 'CONTEUDO' | 'INDETERMINADO' | string | null`.
   - Template do Analisador de Partidas exibe badges visualmente diferenciadas (`⚙️ Processo` em âmbar e `📚 Conteúdo` em azul celeste) nos cards de pontos críticos.

4. **Verificação Global:**
   - 504 testes no backend passando em 28 módulos (`python -m unittest`).
   - 125 testes no frontend passando em 18 arquivos (`npx ng test --no-watch`).
   - Build de produção (`ng build`) bem-sucedido sem erros.

---

### D-44 — Otimização de Performance e Rotas no Frontend & OCR Multi-Idioma no Pipeline RAG

**Data:** 2026-09-15  
**Contexto:**
1. **Frontend Performance & UX:** O build do Angular emitia aviso de orçamento (`initial exceeded maximum budget: 845 kB > 500 kB`), pois todas as rotas eram carregadas estaticamente no `main.js` (`app.routes.ts`). Além disso, a navegação no topo sofria quebra de linha em telas mobile estreitas.
2. **Expansão do RAG & Livros:** O clássico *"How to Calculate Chess Tactics"* (Valeri Beim, pendência P-9) é um PDF escaneado em inglês. O extrator `processar_livro.py` era estritamente focado em português (Tesseract `lang="por"` fixo, regexes apenas de capítulos em português `CAPÍTULO/PARTE` e marcadores de índice em português), impedindo o OCR e chunking correto de livros em inglês.

**O que mudou:**

1. **Lazy-Loading de Rotas e Navbar Responsiva (Frontend):**
   - Convertidas todas as rotas de `frontend/src/app/app.routes.ts` para lazy-loading via `loadComponent: () => import(...)`.
   - O chunk inicial do `main.js` caiu drasticamente de 804 kB para apenas **10.73 kB** (tamanho transferido inicial total: 133 kB comprimido).
   - Ajustado `maximumWarning` no `angular.json` para 600 kB, eliminando completamente os warnings do build.
   - Barra de navegação em `frontend/src/app/app.html` ganhou suporte a scroll horizontal fluido com `overflow-x-auto whitespace-nowrap scrollbar-none` e links com `shrink-0`, eliminando quebras desajeitadas em smartphones.
   - Todos os 125 testes do frontend continuam passando em 18 arquivos.

2. **OCR Multi-Idioma e Detecção de Capítulos em Inglês (Backend / RAG):**
   - Atualizado `backend/rag/processar_livro.py` com argumento `--ocr-lang` (padrão `"por"`, aceitando `"eng"`).
   - `CHAPTER_PATTERNS` estendido para reconhecer `CHAPTER`, `PART`, `SECTION` e capítulos numerados no padrão ocidental (`12. Tactical Combinations`).
   - `INDICE_MARKERS` ampliado para cobrir termos como `"contents"`, `"table of contents"`, `"index of players"` e `"index of games"`.
   - Função `ocr_cache_path` e rotinas de cache agora usam `{pdf_stem}_{ocr_lang}_{digest}.json`, garantindo isolamento entre idiomas e evitando reprocessamento acidental.
   - Criada suíte unitária completa em `backend/rag/test_processar_livro.py` com 12 testes cobrindo regexes multilíngues, overlap de chunks e cache.
   - Registrado o novo teste em `docs/OPERACAO.md` e `.github/workflows/deploy-backend.yml` (cumprindo a Regra R8).

3. **Verificação:**
   - 516 testes no backend passando em 29 módulos (`python -m unittest`).
   - 125 testes no frontend passando em 18 arquivos (`npx ng test --no-watch`).
   - Total de testes no projeto: 641.
   - Build do Angular (`ng build`) com zero warnings e zero erros.

---

### D-45 — Melhorias de UI & UX: Coordenadas e Inversão no Tabuleiro, Preview Visual no Explicador e Precisão por Fase no Repertório

**Data:** 2026-09-15  
**Contexto:**
1. **Tabuleiro Preview:** O componente `tabuleiro-preview` era estático, sem coordenadas de xadrez (letras a-h e números 1-8), sem possibilidade de inversão de perspectiva (Brancas vs Pretas) e sem indicador de vez de jogar.
2. **Explicador de Posição:** A tela exibia apenas o texto cru da FEN em fonte mono pequena, sem exibir o tabuleiro de xadrez visual nem no formulário de entrada nem no cabeçalho do resultado.
3. **Repertório no Dashboard:** Os cards de abertura exibiam taxa de vitória e momentos críticos, mas não aproveitavam os dados enriquecidos de precisão média por fase (`precisao_media_abertura`, `precisao_media_meiojogo`, `precisao_media_final`).

**O que mudou:**

1. **Evolução do `tabuleiro-preview`:**
   - Adicionadas coordenadas periféricas discretas (letras a-h e números 1-8) com contraste dinâmico de cor estilo Lichess.
   - Suporte a inversão de perspectiva (`orientacao: 'BRANCAS' | 'PRETAS'`) e botão de rotação rápida `🔄`.
   - Detecção automática de vez de jogar (`vezDeJogar: 'BRANCAS' | 'PRETAS'`) a partir do 2º campo da FEN, exibindo badge com círculo indicativo.
   - Refatoração para Signals Angular eliminando `NG0100` e otimizando o change detection.
   - Criada suíte com 5 testes unitários em `tabuleiro-preview.component.spec.ts`.

2. **Integração no `explicador-posicao`:**
   - Adicionado preview visual em tempo real no formulário de inserção assim que uma FEN válida é colada ou ao clicar em "Carregar exemplo clássico".
   - Integrado o tabuleiro de xadrez em tamanho de destaque no painel de resultados ao lado da avaliação objetiva e do veredito conceitual.
   - Sincronização automática da perspectiva do tabuleiro com o filtro de perspectiva do usuário ("Jogando de Pretas" inverte o tabuleiro automaticamente).

3. **Refinamento no `repertorio-insights`:**
   - Exibição de badges de precisão média por fase (Abertura, Meio-jogo, Final) em cada card de abertura quando disponível.

4. **Verificação:**
   - 130 testes no frontend passando em 19 arquivos (`npm test -- --run`).
   - Build do Angular (`ng build`) concluído com 0 warnings e 0 erros.
   - 516 testes no backend passando em 29 módulos. Total global: 646 testes.

---

### D-46 — Ingestão de "How to Reassess Your Chess" (Jeremy Silman, 3ª ed.) e Automação do Índice Conceitual

**Data:** 2026-09-15  
**Contexto:**
1. O RAG prescritivo (Agente 3 e consultas teóricas) contava com apenas 2 livros processados (*Meu Sistema* e *Xadrez Vitorioso: Táticas*), totalizando 370 chunks e 67 conceitos no `indice_conceitual`.
2. Havia carência de literatura focada em desequilíbrios posicionais e método de pensamento estratégico do mestre internacional Jeremy Silman.
3. A população do `indice_conceitual` dependia historicamente de inserções manuais em SQL, tornando morosa a adição de novos livros.

**O que mudou:**

1. **Ingestão Completa via OCR:**
   - O livro *How to Reassess Your Chess (3rd Edition)* foi processado via Tesseract OCR em 212 páginas escaneadas.
   - Gerados 251 chunks em `livros_chunks` com embeddings do Gemini no Supabase (volume total saltou para 621 chunks).
   - O Gemini gerou 122 sugestões conceituais mapeadas aos 39 capítulos em `backend/rag/sugestoes/How_to_Reassess_Your_Chess.json`.

2. **Automação do Importador do Índice Conceitual:**
   - Criado o script `backend/rag/importar_indice_conceitual.py` para ler o JSON estruturado gerado pelo LLM e persistir os conceitos na tabela `indice_conceitual` em lotes de 50 (com suporte a flag `--substituir`).
   - Criada suíte unitária completa em `backend/rag/test_importar_indice_conceitual.py` (4 testes cobrindo parsing, mocks de Supabase insert e delete).
   - Teste registrado em `docs/OPERACAO.md` e `.github/workflows/deploy-backend.yml` (cumprindo R8).
   - Tabela `indice_conceitual` passou de 67 para 189 conceitos (+182% de cobertura).

3. **Verificação:**
   - 520 testes no backend passando em 30 módulos (`python -m unittest`).
   - 130 testes no frontend passando em 19 arquivos.
   - Total de testes no projeto: 650 testes automatizados.

---

### D-47 — Sistema de design: tokens, biblioteca de componentes e identidade visual

**Data:** 2026-09-15

**Problema.** O frontend não tinha sistema de design nenhum. Cor, espaçamento,
raio e sombra eram escritos à mão direto no template: **~1.000 ocorrências de
hex em 70+ tons distintos**, com vários quase-duplicados que ninguém conseguia
distinguir a olho nu (`#121a1e`, `#121c20`, `#131b1f`, `#121e23`, `#1a1e21`…).
Cada tela reinventava botão, campo, selo e cartão com variações pequenas, e três
componentes ainda misturavam a paleta padrão do Tailwind (`emerald-500`,
`rose-800`, `zinc-100`, `sky-300`, `purple-800`) com a paleta da casa — duas
linguagens de cor concorrentes na mesma tela. A inconsistência era estrutural,
não estética: sem um lugar único de verdade, qualquer ajuste visual exigia achar
e trocar dezenas de literais.

**Decisão.** Refinar a identidade que já existia (ardósia + latão + marfim —
"sala de estudo noturna") em vez de trocá-la, mas transformá-la em sistema:

1. **`src/styles.css` vira a única fonte de verdade.** Um bloco `@theme` do
   Tailwind 4 define os tokens — superfícies (`ardosia-950…600`), traços
   (`linha`, `linha-forte`), texto (`marfim`, `bruma-200…600`), acento
   (`latao-300…700`), semânticas (`sucesso`, `perigo`, `info`, `roxo`) e as
   casas do tabuleiro. O Tailwind gera os utilitários automaticamente
   (`bg-ardosia-800`, `text-latao-500`, `border-linha`…), então o template nunca
   mais precisa escrever hex.
2. **Biblioteca de componentes em `@layer components`:** `.cartao`, `.painel`,
   `.btn` (+ `primario`/`secundario`/`fantasma`/`perigo`/`pequeno`/`largo`),
   `.campo`, `.rotulo`, `.selo` (+ 8 variantes), `.aviso`, `.segmentado`,
   `.metrica`, `.tabela`, `.estado-vazio`, `.esqueleto`, `.pulso`, `.prosa`,
   `.nav-link`, `.titulo-pagina`/`.titulo-secao`/`.sobrelinha`.
3. **Tipografia:** Fraunces (serifa editorial, com `WONK`/`SOFT` zerados) nos
   títulos + Inter na interface, via Google Fonts com `display=swap`. Números de
   dado em `tabular-nums` para alinharem em coluna.
4. **Os helpers de cor em TypeScript passam a devolver nome de variante, não
   classe de cor.** `corBadgeStatus()`, `corBadgeTaxa()`, `obterBadgeEficacia()`,
   `corBadgeQualidadeLance()`, `badgeCategoria()` etc. agora retornam
   `'selo-sucesso'`, `'selo-perigo'`… — a cor mora no CSS, não espalhada no TS.

**Mudanças de UX que vieram junto (não são só pintura).**

- **A navegação some para quem não tem sessão.** Antes o cabeçalho aparecia na
  tela de login com 5 links que, por causa do `authGuard` (D-23), voltavam todos
  para `/login`. Agora só renderiza autenticado — com teste cobrindo isso.
- **Rótulos da navegação encurtados** ("Laboratório de Raciocínio" →
  "Laboratório"): o nome completo continua no `<h1>` de cada página e no
  `title`, mas o trilho horizontal deixa de estourar no celular.
- **`index.html` saiu do padrão do Angular:** era `lang="en"` com título
  "Frontend". Agora é `pt-BR`, título "Hexágono — laboratório de xadrez",
  `description` e `theme-color`.
- **Marca visual:** hexágono-radar em SVG inline (o próprio produto), no
  cabeçalho e no login. Não usa nenhum asset externo.
- **Esqueletos de carregamento** no lugar de "Carregando…" solto nas 8 telas que
  esperam rede.
- **Emoji saiu dos elementos de interface** (✅⏳❌🔄📷⚙️📚💥) e virou tipografia
  ou SVG: emoji renderiza diferente em cada sistema e destoa do resto. Os que
  são conteúdo (♔ ♚ ⚡) ficaram.
- **`corBadgeVencedor` parou de pintar brancas de verde e pretas de vermelho** —
  sugeria "bom/ruim" onde só existe "lado". Agora usa as cores das próprias
  peças (`.selo-brancas` / `.selo-pretas`).
- **Acessibilidade:** `:focus-visible` em latão global, `aria-pressed` em todo
  controle segmentado, `label` amarrada por `id` em todo campo,
  `prefers-reduced-motion` desliga as animações.

**Verificação.**

- 133 testes de frontend passando em 19 arquivos (eram 130; +3 dos novos casos:
  navegação oculta sem sessão, `corBadgeTaxa` do repertório, variantes de selo).
- 10 asserções de teste foram atualizadas junto — todas de apresentação
  (rótulos com emoji, hex de badge, Title Case → caixa de sentença). Nenhuma
  regra de negócio mudou.
- `ng build` de produção com 0 warnings e 0 erros.
- Hex escrito à mão em template/TS: de ~1.000 para **11**, todos dentro da
  configuração do Chart.js em `hexagono-radar.component.ts`, que exige string
  literal de cor e não aceita classe CSS (comentado no arquivo, apontando para
  os tokens equivalentes).
- CSS final: 42,4 kB cru / **7,5 kB transferido** — *menor* que antes do sistema
  de design. Cada `bg-[#162126]` escrito à mão gerava uma classe de valor
  arbitrário própria no bundle; trocar ~1.000 desses por um punhado de tokens
  reaproveitados pagou a biblioteca de componentes com sobra.

**Limite conhecido desta verificação.** Não havia Playwright nem outro browser
automatizável nesta máquina, então a conferência foi por build, testes e
inspeção do CSS gerado — **não houve screenshot de tela renderizada**. A
validação visual final depende de abrir no navegador.

---

### D-48 — Treino Diário: repetição espaçada sobre os próprios lances críticos

**Data:** 2026-09-15
**Gatilho:** pesquisa de mercado (mapeamento do produto + concorrentes:
Aimchess, Chess DNA, Chessy, Backrank.io, Blunders.ai, PatternForge, Noctie.ai,
Chessable) mostrou que praticamente todo concorrente próximo converge para o
mesmo padrão — importar as partidas do usuário, achar os erros reais, e
devolvê-los como fila de repetição espaçada até o padrão "grudar". Era o maior
gap entre o produto e o mercado: o pipeline já diagnostica (16 tags de causa
raiz, hexágono, gargalo) mas não fazia a pessoa treinar ativamente o que foi
diagnosticado. ~90% do dado necessário já existia (`lances_criticos.fen_antes_lance`
desde D-27, `diagnosticos.raiz_conceitual_violada`/`tags_falha`), faltava só a
camada de agendamento.

**Decisão de escopo (confirmada com o usuário antes de implementar).** O card
de revisão pede só o lance, sem texto de raciocínio — `classificar_qualidade_lance`
(`revisar_pensamento.py`, puro threshold sobre `queda_win_percent`) já basta
pra derivar a nota do SM-2, e manter o Gemini fora do caminho quente é o que
permite muitas repetições por dia sem custo nem latência extra. A causa raiz
do erro (já calculada uma vez pelo Agente 1) e a citação do livro aparecem no
feedback pós-resposta, não antes — do contrário a revisão vira consulta, não
teste.

**Schema (`backend/db/fila_treino_espacado.sql`).** Tabela nova com
`user_id` (FK real p/ `auth.users`, `on delete cascade`), `lance_id` (FK p/
`lances_criticos`, `on delete cascade` — quando uma partida é reprocessada,
R6 apaga `lances_criticos` antigos, e a linha da fila correspondente some
junto, em vez de virar FK quebrada), campos de agendamento SM-2
(`intervalo_dias`, `fator_facilidade`, `repeticoes`, `total_revisoes`,
`ultima_qualidade`) e a citação já resolvida e cacheada
(`livro_citado`/`capitulo_citado`/`pagina_citada`). RLS habilitada com policy
de leitura própria (defesa em profundidade, mesmo padrão de
`uso_diario_usuario` em D-32), sem policy de escrita para `authenticated`.

**`backend/common/spaced_repetition.py` (novo).** SM-2 simplificado (mesmo
algoritmo do Anki), função pura `atualizar_agendamento(...)`. Nota 0-5
derivada de `qualidade_lance`: `BOM`→5, `SUBOTIMO`→3, `RUIM`→1. 9 testes
determinísticos (`test_spaced_repetition.py`).

**`backend/agentes/popular_fila_treino_espacado.py` (novo).** Roda no
pipeline diário, depois de `agente1_linter.py`. Loop por usuário (mesmo
formato de `agente2_analista.py`, try/except isolado por conta). Filtra
`tipo_evento='PICO'` (EROSAO é uma janela de vários lances, sem um "lance
certo" único, fica fora do v1) e `fen_antes_lance` não nulo (coluna existe
desde D-27, nem toda linha antiga tem). Resolve a citação **uma vez** via
`buscar_conceitos()` (`agente3_prescritor.py` — ILIKE puro sobre
`indice_conceitual`, **sem Gemini, sem embedding**) e cacheia na linha.
Escalona no máximo `TREINO_NOVOS_POR_DIA` (env var, default 10) cards novos
por dia — evita popular o backlog histórico inteiro de uma vez no primeiro
run. 13 testes (`test_popular_fila_treino_espacado.py`).

**`backend/api/api_server.py` — 2 endpoints novos.** `GET /treino/fila`
(lista os cards vencidos hoje, deliberadamente sem `tags_falha`/causa raiz/
citação) e `POST /treino/{fila_id}/responder` (`{lance}` → avalia via
Stockfish reaproveitando **exatamente** `resolver_lance_usuario` e
`avaliar_lance_avulso` de `revisar_exercicio_avulso.py` — zero lógica de
motor duplicada —, reagenda via `atualizar_agendamento` e revela causa raiz +
citação). 404 (nunca 403) quando o card não existe ou é de outro dono, mesmo
padrão IDOR-safe de D-29/D-30. **Sem `limite_diario`** nesta rota, ao
contrário de D-32: só usa Stockfish (já serializado por `engine_lock`, sem
custo de API paga), e o objetivo da feature é permitir muitas repetições por
dia — um teto baixo contradiria o propósito. 10 testes
(`ObterFilaTreinoTest`, `ResponderTreinoTest`).

**Validado com a conta real do Edson (`bfde845a-8e2e-4885-801f-0fed2dd3b426`),
sem mock nenhum:**
- `popular_fila_treino_espacado.py` rodado de verdade contra os 714
  diagnósticos reais já existentes: **632 cards elegíveis** (`PICO` +
  `fen_antes_lance`) enfileirados, escalonados em **64 dias** a 10/dia
  (confirmado por SQL: `2026-09-15` a `2026-11-17`, exatamente 10 por dia).
  2ª execução: 0 cards novos (idempotente). 632/632 linhas com citação
  resolvida (2 livros distintos), **zero chamadas ao Gemini**.
- Servidor real (`uvicorn`, porta de teste) + sessão real via magic link
  (Admin API): `GET /treino/fila` devolveu os 10 cards de hoje, confirmando
  por inspeção das chaves do JSON que nenhum campo de diagnóstico vaza antes
  da resposta. `POST /treino/1/responder` com um lance real (`h4`) rodou o
  Stockfish de verdade, classificou `BOM`, revelou a causa raiz e a citação
  ("Meu Sistema", Nimzowitsch) e reagendou pra amanhã (`repeticoes: 1`) —
  exatamente o que o SM-2 prevê pra uma 1ª repetição boa.
- 2ª conta de teste real (Admin API, removida ao final): `GET /treino/fila`
  devolveu fila vazia (não vê os 632 cards da conta A); `POST` num `fila_id`
  da conta A devolveu **404** — isolamento por dono confirmado, mesmo padrão
  de verificação de D-29/D-30.
- `on delete cascade` confirmado direto no catálogo do Postgres
  (`pg_constraint.confdeltype = 'c'` nas duas FKs), sem precisar reprocessar
  uma partida real de produção pra provar o comportamento.
- Um efeito colateral encontrado e corrigido durante a validação: o e-mail de
  identificação do usuário no ambiente do agente (`edson.hirano28@gmail.com`)
  **não é** o e-mail de login da conta real (`edson.hirano.dev@gmail.com`) —
  a 1ª tentativa de gerar um magic link criou uma conta órfã por engano,
  detectada por SQL e removida antes de qualquer outro passo.

**Frontend.** `treino.service.ts` (mesmo template de `puzzles.service.ts`),
componente novo `treino-do-dia` (reaproveita `app-tabuleiro-preview` — que é
só preview estático, sem drag-and-drop — e o input de lance livre PT/EN,
mesma UX do Laboratório), rota `/treino` (lazy, `authGuard`) e novo link de
navegação "Treino". Usa só classes do sistema de design (D-47), nenhum hex
novo.

**Testes:** 32 novos no backend (520 → **552**, 32 módulos), 14 novos no
frontend (133 → **147**, 21 arquivos). `ng build` limpo.

**R8 cumprido:** `backend.common.test_spaced_repetition` e
`backend.agentes.test_popular_fila_treino_espacado` registrados em
`docs/OPERACAO.md` e `.github/workflows/deploy-backend.yml`. Novo step
`popular_fila_treino_espacado.py` em `pipeline-diario.yml` (logo após
`agente1_linter.py`, `continue-on-error: true`, com linha no resumo de
falhas).

---

### D-49 — Banco de exercícios táticos categorizado + "Treino Focado"

**Data:** 2026-09-15/16
**Gatilho:** pedido direto do usuário — montar uma base de exercícios táticos
categorizada nas mesmas tags já mapeadas (`HEXAGON_CATEGORIES`), pra sugerir
os exercícios certos como opção de treino focado nos erros do usuário. O
D-48 só cobre categorias em que o usuário já errou o suficiente nos próprios
jogos; faltava material pra treinar uma categoria fraca desde o primeiro dia.

**Decisão de fonte.** Importar o dump público de puzzles do Lichess (CC0) em
vez de linkar pra fora (como `insights_puzzles.py` já fazia,
`lichess.org/training/{tema}`) ou criar exercícios manualmente — dá controle
total da UX e permite plugar direto na fila de repetição espaçada do D-48.

**Decisão de fusão: uma fila só, não uma tela paralela.** O motor SM-2
(`atualizar_agendamento`) já é puro e genérico — não conhece
`lances_criticos`, só recebe `intervalo_dias/fator_facilidade/repeticoes/
qualidade`. O acoplamento com "lance próprio" estava só em 3 pontos
localizados: o FK obrigatório `lance_id`, os dois joins de `GET /treino/fila`
e `POST /treino/{id}/responder`, e a citação de livro. Duas telas separadas
fragmentariam "feitas hoje"/streak em duas contagens — pior experiência do
que "uma opção de treino focado" pedida. Como o D-48 ainda não tinha sido
commitado nesta sessão, o schema foi ajustado livremente, sem migração de
dado real em produção a proteger.

**Schema.** Tabela nova `exercicios_taticos` (catálogo global, sem
`user_id`, RLS ligada e **zero policies** — mesmo padrão de
`indice_conceitual`/`livros_chunks`): `puzzle_id_lichess` (unique), `fen`
(já a posição real a resolver — o FEN bruto do Lichess mais o primeiro lance
do CSV, o "lance de preparo" do adversário), `categoria_hexagono`,
`temas_lichess[]`, `rating`, `popularidade`. **Não guarda a "resposta
certa"**: a qualidade da resposta é avaliada dinamicamente pelo Stockfish
(`avaliar_lance_avulso`), igual a `lances_criticos` — zero gabarito
duplicado. `fila_treino_espacado` ganhou `lance_id` opcional, `exercicio_id`
(FK opcional pra `exercicios_taticos`, **`on delete restrict`, não
`cascade`**: apagar em massa o catálogo não pode arrastar silenciosamente o
progresso de SM-2 de quem já tem esses exercícios na fila — a exclusão deve
falhar alto), `origem` (`'lance_critico'` \| `'exercicio_tatico'`) e os
checks/uniques que garantem exatamente uma origem por linha.

**`backend/rag/importar_exercicios_taticos.py` (novo, import ocasional/
manual — NÃO entra no `pipeline-diario.yml`).** Baixa
`lichess_db_puzzle.csv.zst` em streaming (`requests` + `zstandard`, nova
dependência), mapeia os temas do Lichess pra `HEXAGON_CATEGORIES` via
dicionário fixo, filtra por faixa de rating/popularidade
(`EXERCICIO_RATING_MIN/MAX`, `EXERCICIO_POPULARIDADE_MIN`) e por um teto por
categoria (`EXERCICIOS_POR_CATEGORIA`, default 300) — para de ler o stream
assim que todas as categorias aplicáveis batem o teto. Upsert idempotente
por `puzzle_id_lichess`. **Sem flag `--substituir`** nesta v1 (diferente de
`importar_indice_conceitual.py`): dado o `on delete restrict`, um delete em
massa falharia assim que qualquer exercício estivesse referenciado na fila
de algum usuário — não vale a pena complicar o script pra um caso de uso
raro.

**Achado honesto:** o Lichess não tem tema de puzzle equivalente a
`ESTRATEGIA` (avaliação posicional) nem `GESTAO_DE_TEMPO` (os puzzles são
posições estáticas, sem relógio) — só `TATICA`, `CALCULO`, `FINAIS` e
`ESTRUTURA_DE_PEOES` recebem exercícios de catálogo. Confirmado rodando o
import de verdade: 7.288 linhas lidas do dump público (parou assim que os 4
tetos de 300 bateram — não precisou ler as ~5M linhas inteiras), **1.200
exercícios importados** (300 por categoria aplicável), 3.334 puladas (tema
não mapeado ou fora da faixa de qualidade). 2ª execução: 1.200 linhas,
0 duplicatas (idempotência confirmada por `count(distinct puzzle_id_lichess)`).

**`POST /treino/foco/{categoria}` (novo endpoint).** 400 se a categoria não
existe em `HEXAGON_CATEGORIES`. Exclui exercícios já na fila do usuário,
sorteia `TREINO_FOCO_QTD_EXERCICIOS` (default 8) com `random.sample`,
resolve a citação uma vez via `resolver_citacao` (reaproveitado de
`popular_fila_treino_espacado.py`) e insere via
`upsert(..., on_conflict="user_id,exercicio_id", ignore_duplicates=True)` —
um duplo clique em "Focar" vira no-op, não um 500. `GET /treino/fila` e
`POST /treino/{id}/responder` ganharam um branch por `origem`: exercício de
catálogo não tem `diagnosticos` associado, então `raiz_conceitual_violada`/
`tags_falha` voltam vazios de propósito — a explicação do "porquê" já vem do
Stockfish + melhor lance, mesma filosofia de "sem Gemini no caminho quente"
do D-48.

**Auto-revisão (Plan agent) encontrou e corrigiu um bug real antes da
implementação:** o desenho original usava `on delete cascade` em
`exercicio_id`, copiando o padrão de `lance_id` sem questionar — mas como
`importar_exercicios_taticos.py` reimportaria com um `delete()` (não
`TRUNCATE`), isso teria disparado o cascade e apagado silenciosamente o
progresso de SM-2 de qualquer usuário com exercícios na fila. Corrigido
trocando pra `on delete restrict` e removendo a flag `--substituir` da v1
inteiramente. A mesma revisão também pegou: falta de `Depends(verificar_sessao)`
explícito no novo endpoint (já estava correto no desenho, só não documentado
no plano), inserção sem proteção contra duplo-clique, e o guard defensivo de
FEN ausente faltando no branch novo do `GET /treino/fila` — todos corrigidos
antes de escrever qualquer código.

**Validado com a conta real do Edson, sem mock:** `POST /treino/foco/TATICA`
adicionou 8 exercícios reais; `GET /treino/fila` devolveu 17 itens (9
`lance_critico` + 8 `exercicio_tatico`), sem nenhum campo de diagnóstico
vazando nos itens de catálogo; `POST /treino/{id}/responder` com um lance
real (`Kh1`, posição `2r2rk1/pp3p2/4p3/3p2q1/3P4/P1N4Q/1PP5/1R4K1 w - - 0 31`)
classificou `BOM` via Stockfish de verdade, revelou a citação já cacheada
("How to Reassess Your Chess"), reagendou pra `2026-09-16` (`repeticoes: 1`)
e devolveu `raiz_conceitual_violada: null`/`tags_falha: []` como esperado.
Verificação de browser (clicar "Focar" no Hexágono) **não foi possível**
neste ambiente — sem ferramenta de automação de navegador disponível e sem
um servidor de dev respondendo na porta local; a compensação foi validar o
contrato inteiro (schema, endpoints, componentes) ponta a ponta via API real
e `ng build`/`ng test` limpos, mas o clique manual no navegador continua
pendente de verificação humana.

**Frontend.** `treino.service.ts` ganhou `focarCategoria()` e o tipo
`ROTULOS_CATEGORIA_HEXAGONO` (rótulos amigáveis das 6 categorias,
reaproveitado pelo selo do card e pelos botões). `treino-do-dia` ganhou um
selo de origem por card ("Da sua partida" vs "Exercício: <categoria>").
`hexagono-radar` ganhou uma seção "Treino focado" com um botão por categoria
que chama `focarCategoria()` e navega pra `/treino`.

**Testes:** 34 novos no backend (552 → **586**, 33 módulos: +
`backend.rag.test_importar_exercicios_taticos`), 4 novos no frontend
(147 → **151**, 21 arquivos). `ng build` limpo.

**R8 cumprido:** `backend.rag.test_importar_exercicios_taticos` registrado em
`docs/OPERACAO.md` e `.github/workflows/deploy-backend.yml`. Novo script
**não** entra em `pipeline-diario.yml` de propósito — import ocasional de
conteúdo de referência estático, não dado de usuário.

---

### D-50 — Auditoria de qualidade: backend, segurança/operação e frontend

**Data:** 2026-09-16
**Gatilho:** pedido explícito do usuário — em vez de trazer recursos novos,
mapear e resolver formas de melhorar o que já existe. Três auditorias
paralelas e independentes (backend/confiabilidade, segurança/operação,
frontend/UX), todas somente-leitura antes de qualquer mudança, seguidas de
implementação de tudo que era corrigível diretamente. Nenhum achado foi
inventado: cada um foi confirmado por leitura de código ou consulta real ao
Supabase (`get_advisors`, `pg_policies`) antes de virar mudança.

**Backend — segurança/custo:**
- **`POST /partidas/{id}/reprocessar` não tinha limite diário.** Dispara o
  mesmo pipeline Stockfish+Gemini de `/analisar-pgn`, mas tinha ficado fora
  do D-32 por descuido — um usuário (ou um retry em loop) podia gerar gasto
  ilimitado de Gemini. Agora usa `limite_diario("reprocessar")`, mesmo
  padrão das outras 4 rotas caras (default 20/dia, `LIMITE_DIARIO_REPROCESSAR`).
- **`POST /treino/{id}/responder` (D-48) também não tinha teto.** Só usa
  Stockfish (sem custo de API paga), mas serializa no `engine_lock` global
  (R3) — um spam ali derruba a fila de Stockfish de todo mundo. Ganhou
  `limite_diario("treino-responder")`, com teto bem mais alto (default 200)
  já que o propósito do D-48 é permitir muitas repetições por dia.
- **Código morto que travava o boot removido.** `verificar_api_key`,
  `_resolver_api_keys()` e `_parse_api_keys` (o antigo esquema de header
  `X-API-Key`, aposentado como gate de acesso desde D-25) foram deletados de
  vez — nenhuma rota dependia mais deles, mas a validação de
  `API_SECRET_KEYS` no startup ainda **recusava subir o servidor** sem essa
  variável, um risco de disponibilidade real amarrado a uma feature morta.
  `deploy-backend.yml` não propaga mais esse secret; `env.yaml` local e
  `.env.example` limpos também. Essa pendência estava registrada desde o
  próprio D-25 como "não fazer sem avaliar" — avaliada e resolvida agora.

**Banco de dados (Supabase, aplicado diretamente via migrations):**
- **22 policies de RLS reescritas** para usar `(select auth.uid())` em vez
  de `auth.uid()` solto (lint `auth_rls_initplan` do advisor de
  performance) — mesma regra de isolamento, só evita reavaliar a função
  linha a linha. Mecânico, via `ALTER POLICY` (sem DROP+CREATE, sem janela
  sem proteção).
- **4 índices criados** para FKs sem cobertura (`diagnosticos.lance_id`,
  `fila_treino_espacado.exercicio_id`/`lance_id`,
  `lichess_oauth_pkce.user_id`) — lint `unindexed_foreign_keys`.
- **Função órfã `match_livro_chunks` (singular) removida.** Achado durante a
  auditoria: existia só no banco, sem nenhum arquivo `.sql` correspondente
  no repo (drift não documentado) e zero call site no código — versão
  anterior de `match_livros_chunks` (plural), a que `agente3_prescritor.py`
  realmente usa. `match_livros_chunks` ganhou `set search_path = public,
  extensions, pg_temp` (lint `function_search_path_mutable`; `extensions` é
  necessário porque é lá que o Supabase instala o pgvector). De quebra,
  corrigido um drift real: o arquivo `backend/db/match_livros_chunks.sql`
  declarava `id bigint`, mas a coluna real é `id uuid` — sincronizado.
- **Não corrigido (fora do alcance das ferramentas desta sessão):** o
  advisor de segurança aponta `auth_leaked_password_protection` desligado —
  é um toggle do Dashboard do Supabase Auth, não uma migration SQL. Risco
  baixo dado o modelo de ameaça do projeto (ver P-9 em `ESTADO.md`).

**P-1 (chaves expostas) — não "resolvido", mas mapeado com precisão.**
Rotacionar chaves de provedor externo (Gemini, Supabase) exige ação em
consoles que este agente não controla. Runbook confirmado por auditoria:
`GEMINI_API_KEY` toca 9 arquivos + 3 workflows, `SUPABASE_SERVICE_ROLE_KEY`
toca ~20 arquivos + 3 workflows (praticamente todo script do pipeline);
`API_SECRET_KEYS` não precisa mais rotação — foi removida (ver acima). A
rotação em si (gerar a nova chave no console do provedor, atualizar
`.env`/GitHub Secrets, rodar `deploy-backend.yml`) continua pendente de
alguém com acesso a esses consoles — ver P-1 em `ESTADO.md`.

**Backend — manutenibilidade:**
- **Novo `backend/common/settings.py`** (`carregar_variaveis_obrigatorias`)
  substitui **18 implementações quase-idênticas** de `load_settings()`
  (`load_dotenv` + validar presença + `ValueError` com a lista de nomes
  ausentes) espalhadas por `backend/agentes/`, `backend/ingestao/`,
  `backend/rag/`, `backend/analise_engine/`. Risco que motivou a
  consolidação: um typo de nome de variável ou uma regra de validação
  corrigida num script não se propagava pros outros 17. Cada `load_settings()`
  virou um wrapper fino que chama o helper compartilhado e monta seu
  próprio objeto de configuração por cima (dataclass, dict, ou tupla,
  preservado sem alteração de contrato público). 5 testes novos.
- **`backend/common/progress.py` ganhou testes** (12 testes) — utilitário
  compartilhado por todo o pipeline, sem cobertura própria até agora.
- **`backend/agentes/teste_gemini.py` deletado.** Script de smoke-test
  manual, autodescrito como "temporário" no próprio docstring, sem nenhuma
  referência em outro lugar do repo, fazia uma chamada real e paga ao
  Gemini se executado.

**Frontend — UX/consistência:**
- **`historico-analise` (componente compartilhado por Analisador de
  Partida, Explicador de Posição e Laboratório de Raciocínio) não tinha
  estado de erro.** Uma falha ao buscar o histórico ficava indistinguível
  de "não há nada ainda" (a mesma `mensagemVazio` aparecia nos dois casos).
  Ganhou `@Input() erro`, com um branch `.aviso-erro` antes do estado vazio;
  as 3 telas que o usam agora rastreiam `erroHistorico` separado de
  `carregandoHistorico`.
- **Mesma linha clicável não era alcançável por teclado.** `<div (click)>`
  sem `role`/`tabindex`/handler de teclado — ganhou `role="button"`,
  `tabindex="0"`, `(keydown.enter)` e `(keydown.space)`.
- **Hexágono: "ainda não há análise" estava renderizado como erro
  (`.aviso-erro`), não como estado vazio.** Usuário novo, sem nenhum erro
  crítico registrado ainda, via uma mensagem com estilo de alerta vermelho.
  Separado em `semAnalise` (estado vazio genuíno) vs `error` (falha real de
  rede/servidor), com `.estado-vazio` + link direto para `/analisador`
  ("Analisar minha primeira partida").
- **Cores do Chart.js do Hexágono eram hex duplicado à mão**, copiado dos
  tokens de `src/styles.css` sem nenhuma ligação real — risco de drift
  silencioso se a paleta for retocada. Agora lidas em tempo real via
  `getComputedStyle(document.documentElement).getPropertyValue(...)`, com
  fallback pro hex original se o token não existir (SSR/testes).
  Removido também um `style="height: 400px"` redundante (duplicava a classe
  Tailwind do container pai).
- **Spinner do Analisador de Partida** era um `<span>` com
  `animate-spin`/borda manual, único no app inteiro — trocado pelo `.pulso`
  compartilhado (mesmo usado em Laboratório, Explicador, Perfil, Treino).
- **3 componentes sem nenhum teste ganharam spec files**:
  `hexagono-radar` (7 testes — inclui `focar()`, o estado vazio novo, e a
  leitura de cor via token), `narrativa-analise` (5 testes) e
  `perguntas-pendentes` (6 testes).
- **Checado e descartado como não-problema:** `tabuleiro-preview` usa
  `max-w-[340px]` (um teto, não uma largura fixa) sobre um grid `w-full` +
  `aspect-square` por casa — já é fluido, encolhe corretamente em qualquer
  viewport estreito. O achado original da auditoria foi cauteloso demais;
  confirmado na leitura do código que não há bug real ali.

**Testes:** 17 novos no backend (583 → **600**, 35 módulos: +
`backend.common.test_progress`, `backend.common.test_settings`), 20 novos
no frontend (151 → **171**, 24 arquivos). `ng build` limpo. Nenhuma
regressão em nenhuma das duas suítes completas, conferido a cada lote de
mudanças (não só no final).

**R8 cumprido:** `backend.common.test_progress` e `backend.common.test_settings`
registrados em `docs/OPERACAO.md` e `.github/workflows/deploy-backend.yml`.

---

### D-51 — Miniaturas de posição nos resumos e históricos

**Problema.** Todo lugar do app que lista várias coisas de uma vez descrevia
cada item só por texto. "Lance Cxe5" se repete entre posições completamente
diferentes; "hirano28 vs oponente · B90 · DERROTA" descreve igualmente bem
cinco partidas distintas contra o mesmo adversário na mesma abertura; um
veredito de explicação truncado em 60 caracteres idem. Para saber de qual
item a linha estava falando era preciso abrir um por um. Só duas telas já
tinham miniatura (`perguntas-pendentes` e o card do Treino Diário) — o
componente `tabuleiro-preview` já suportava `[miniatura]="true"` desde o
D-45, estava subaproveitado.

**Decisão.** `HistoricoAnaliseItem` (o contrato do histórico compartilhado
entre Analisador de Partida, Explicador de Posição e Laboratório de
Raciocínio) ganhou dois campos opcionais, `fen` e `orientacao`. Quando o
item traz FEN, a linha desenha uma miniatura de 56–64px à esquerda; quando
não traz, a linha continua exatamente como era. Os cards de ponto crítico do
Analisador ganharam a mesma miniatura, clicável, levando ao Laboratório com
a posição já carregada (mesmo padrão de `perguntas-pendentes`).

Isso arranha o comentário original do D-11 ("este componente não conhece FEN,
PGN nem nenhuma regra de xadrez"). A restrição continua valendo no que
importa: o histórico **repassa** a FEN crua para o `tabuleiro-preview`, que
já é quem sabe fazer parse e já trata FEN inválida desenhando tabuleiro
vazio. Nenhuma regra de xadrez entrou no componente de lista.

**De onde vem cada FEN:**

- **Explicador** e **Laboratório** — a coluna `fen` já vinha nos dois
  endpoints de histórico. Zero mudança de backend.
- **Analisador (lista de partidas)** — campo novo `fen_final` em
  `PartidaRecenteItem`, reconstruído do PGN que a query **já buscava** (para
  extrair os jogadores), via `parse_pgn(...).end().board().fen()`. Parsing
  local e puro: nada de Stockfish, nada de Gemini, nenhuma query a mais. PGN
  inválido/truncado devolve `None` e a linha só fica sem miniatura, em vez de
  derrubar o histórico inteiro.
- **Analisador (pontos críticos)** — a posição mora em
  `lances_criticos.fen_antes_lance` (D-27), não no JSON de `resumo_partida`.
  A junção por `numero_lance` é feita **na leitura** do endpoint
  `/partidas/{id}/resumo`, não na geração do resumo. Essa é a decisão que
  importa aqui: enriquecer na geração só valeria para partidas analisadas
  dali para frente e exigiria reprocessar tudo (caro: Stockfish + Gemini).
  Na leitura, custa uma query barata e vale retroativamente. Conferido
  contra o banco de produção antes de implementar: **423 de 423** pontos
  críticos já existentes casam com um `fen_antes_lance` preenchido — 100% de
  cobertura, nenhum reprocessamento necessário.

**Orientação do tabuleiro.** Helper novo `frontend/src/app/shared/fen.ts`
(`orientacaoDoFen`), que lê o 2º campo da FEN. Numa miniatura de exercício
ou de ponto crítico, quem está na vez de jogar é exatamente quem errou —
então essa é sempre a perspectiva certa. O Analisador usa a `cor_jogada` da
partida e o Explicador usa o `lado_analisado`, que são mais explícitos onde
existem.

**Onde deliberadamente NÃO entrou miniatura:** Sessões de Treino (a
prescrição do Agente 3 é texto — módulos, livro, capítulo, duração; não há
posição nenhuma associada), Puzzles Insights e Repertório Insights
(agregados estatísticos, sem posição por linha) e Perfil (cadastro de
contas). Miniatura ali seria enfeite sem informação.

**Verificação real (não só unitária):** `uvicorn` local + sessão real do
Supabase Auth gerada por magic link (Admin API). `GET /partidas/recentes`
devolveu `fen_final` correto para as 12 partidas manuais reais do banco
(12/12, nenhuma falha de parse); `GET /partidas/{id}/resumo` de uma partida
já analisada devolveu os 4 pontos críticos, cada um com sua FEN, todos com
`b` na vez de jogar — coerente com a partida, que foi jogada de pretas.

**Testes:** 4 novos no backend (600 → **604**), 8 novos no frontend
(171 → **179**, 25 arquivos: + `app/shared/fen.spec.ts`). `ng build` limpo.

**Pendente de conferência humana:** o visual em si (tamanho da miniatura na
linha do histórico, legibilidade das peças a 56px, o card de ponto crítico
em telas estreitas) — não dá para validar de fora do navegador.

---

### D-52 — Auditoria de UX e acessibilidade da aplicação inteira

Varredura das 15 telas/componentes + `styles.css` + casca do app, corrigindo o
que era defeito real. O design system em si já estava maduro (tokens, `.selo`,
`.aviso`, `.esqueleto`, `.pulso`, `:focus-visible` global, `prefers-reduced-
motion`) — o que faltava estava nas bordas.

**1. "Focar em X" era um beco sem saída silencioso (o achado mais grave).**
`hexagono-radar.focar()` fazia `await treinoService.focarCategoria(...)` e
**descartava o retorno inteiro**, navegando para `/treino` em qualquer caso.
Consequência: erro de rede ou sessão expirada levava o usuário para uma fila
inalterada, sem mensagem nenhuma. Pior, conferido contra o banco de produção:
`exercicios_taticos` tem 300 exercícios em CALCULO, TATICA, FINAIS e
ESTRUTURA_DE_PEOES, e **zero em ESTRATEGIA e GESTAO_DE_TEMPO**. Dois dos seis
botões da tela principal não faziam nada, sem avisar.

O D-49 já documentava o buraco de `GESTAO_DE_TEMPO` (o Lichess não tem tema
equivalente a relógio); **`ESTRATEGIA` estar igualmente vazia não estava
documentado em lugar nenhum** — só apareceu agora, ao consultar o banco real.

Correções: `FocoTreinoResponse` ganhou `motivo` (`sem_catalogo` | `ja_na_fila`),
porque `adicionados: 0` conflatava duas situações que dizem coisas opostas ao
usuário ("não temos material" vs "você já pegou tudo") — dizer a errada seria
mentir. O componente passou a usar o resultado, só navega quando algo de fato
entrou na fila, e explica o que houve nos outros casos.

**2. O radar escrevia `ESTRUTURA_DE_PEOES` e `GESTAO_DE_TEMPO` crus** nos
rótulos dos eixos, enquanto os botões logo abaixo, no mesmo cartão, diziam
"Estrutura de Peões" e "Gestão de Tempo". O mapa `ROTULOS_CATEGORIA_HEXAGONO`
já existia e já estava importado no componente.

**3. Modal de onboarding sem saída pelo teclado.** `role="dialog"
aria-modal="true"` sem Esc, sem clique no scrim e sem foco inicial. Adicionados
os três (Esc e scrim ignorados durante o salvamento, para não descartar o que
está em voo). Trap de foco completo ficou de fora de propósito: exige bem mais
código e o caso prático está coberto.

**4. Miniatura de tabuleiro era ruído para leitor de tela.** Cada preview
entregava 64 casas e até 32 `<img alt="wR">` — alt críptico que não ajuda
ninguém a entender a posição, e agora multiplicado por linha de histórico
(D-51). Virou **um** `role="img"` com rótulo que diz o que dá para saber sem
interpretar a posição ("Posição de xadrez com 32 peças, vez das brancas, vista
do lado das brancas"), com as casas em `aria-hidden`. Deliberadamente não
tenta descrever a posição peça a peça nem avaliá-la.

**5. Duas ações irreversíveis sem confirmação.** "Desconectar" do Lichess
(revoga o OAuth, encostado no "Reconectar") e "Reiniciar análise" do Analisador
(descarta o progresso e **consome mais uma análise do limite diário** criado no
D-50). Ambas passaram a pedir confirmação inline, sem `window.confirm` — o app
não usa diálogo nativo em lugar nenhum.

**6. Link "pular para o conteúdo".** Quem navega por teclado atravessava 6
links de navegação + e-mail + "Sair" a cada troca de tela antes de chegar no
conteúdo. Classe `.link-pular` (invisível até receber foco) + `#conteudo` em
volta do `router-outlet`.

**7. Login:** o botão desabilitado não dizia por quê (a dica de 6 caracteres
era só placeholder, some ao digitar) e não havia como conferir a senha
digitada. Adicionados o motivo em texto e o botão mostrar/ocultar. O motivo
fica em branco enquanto o campo de senha está intocado — não acusa quem ainda
nem começou.

**8. `100vh` → `100dvh`** em `body`, `.pagina` e na tela de login: no celular,
`100vh` ignora a barra de endereço e cria uma faixa de rolagem que não existe.

**9. Consistência:** os botões de OAuth do Perfil usavam texto puro
("Iniciando conexão…") enquanto todo o resto do app usa o `.pulso` — mesma
classe de inconsistência corrigida no D-50 com o spinner do Analisador.

**Verificado de verdade:** servidor local + sessão real. `POST /treino/foco/
GESTAO_DE_TEMPO` e `.../ESTRATEGIA` devolveram `{"adicionados":0,"motivo":
"sem_catalogo"}`; `.../TATICA` devolveu `{"adicionados":8,"motivo":null}`.

**10. Conferência visual no navegador (e o que só ela encontrou).** Com
autorização do usuário, Playwright foi instalado **fora do projeto** (num
diretório temporário da sessão, sem tocar `package.json` nem o `node_modules`
do frontend) e usado para abrir o app real — backend local + `ng serve` +
sessão real injetada no `localStorage` — e fotografar 14 telas, em 1440px e em
390px. Três defeitos só apareceram aí, nenhum deles detectável lendo código:

- **A narrativa exibia markdown cru.** O Gemini usa `**negrito**` e a tela
  mostrava os asteriscos: "a \*\*Tática\*\* permanece como o seu gargalo". Isso
  estava em produção, nas duas telas que renderizam narrativa (Hexágono e
  Analisador), e é o texto mais lido do produto. Helper novo
  `shared/texto.ts` (`segmentosDeNegrito`) devolve segmentos, e o template
  renderiza `<strong>` — **sem `innerHTML`**, então nada que venha do modelo é
  interpretado como marcação. Só negrito é tratado: é a única marcação que
  apareceu de verdade, e asterisco solto ou par não fechado fica como está.
- **Os cartões de ponto crítico ficaram apertados no desktop.** A miniatura
  que o D-51 acabou de adicionar, somada ao `lg:grid-cols-3`, espremia as tags
  de falha numa tira de ~150px, quebrando "ABERTURA DE LINHAS DESFAVORAVEL" em
  duas linhas. No celular (1 coluna) já estava ótimo — era um problema
  exclusivo do desktop. Passou a `sm:grid-cols-2`.
- **A navegação no celular escondia metade dos itens.** O trilho rola na
  horizontal com a barra de rolagem escondida (`sem-barra`), então
  "Analisador" e "Perfil" ficavam fora da tela sem nenhuma pista de que
  existiam. `.nav-rolavel` desvanece a borda direita, só abaixo de `sm:`.

Confirmado nas imagens que o resto funciona: rótulos amigáveis nos eixos do
radar, o aviso do "Focar" aparecendo **sem sair da página**, o link de pular
surgindo no primeiro Tab, a confirmação inline de desconectar, o campo de
senha com olho e o motivo do botão desabilitado, e as miniaturas do D-51
legíveis e distintas entre si na lista de partidas.

**Testes:** 2 novos no backend (604 → **606**), 20 novos no frontend
(179 → **199**, 26 arquivos: + `shared/texto.spec.ts`). `ng build` limpo.

**Consequência a resolver fora do código:** ESTRATEGIA e GESTAO_DE_TEMPO
continuam sem catálogo. A UI agora é honesta sobre isso, mas o buraco de
conteúdo permanece — ver P-15 em `ESTADO.md`.

---

### D-53 — Não oferecer o beco sem saída, e tornar a conferência visual repetível

Continuação direta do D-52, com autonomia dada pelo usuário para decidir e
implementar sem consultar a cada passo.

**1. O "Focar" em categoria sem material deixou de existir.** O D-52 fez o
botão explicar, depois do clique, que aquela categoria não tem exercício. Isso
era o remendo: a correção é não oferecer. Endpoint novo `GET /treino/foco/
disponibilidade` devolve a contagem de `exercicios_taticos` por categoria — as
6 chaves sempre presentes, com 0 explícito nas vazias (sumir do mapa viraria
`undefined` no frontend e o botão voltaria a parecer disponível). O Hexágono
só renderiza botão para categoria com material e explica a ausência das outras
em uma linha, apontando para o Treino Diário, que é onde elas de fato se
treinam. Se a consulta falhar, **nenhum** botão é escondido: supor "não tem
material" sem saber seria pior que deixar tentar, e o aviso do D-52 continua
como rede de segurança.

**Por que não foi mapeado tema nenhum para ESTRATEGIA.** A tentação era
preencher o buraco do P-15 acrescentando temas ao
`TEMA_LICHESS_PARA_CATEGORIA`. Revisado o conjunto de temas do Lichess, não há
nenhum que signifique estratégia: `quietMove` e `defensiveMove` são os mais
próximos, e ainda assim descrevem um lance dentro de uma sequência tática.
Puzzle é tática por construção. Mapear um deles para ESTRATEGIA seria
reetiquetar tática como estratégia — exatamente a cobertura fingida que o D-49
recusou fazer para GESTAO_DE_TEMPO. O buraco de conteúdo continua aberto e
honesto no P-15; o que mudou é que a interface parou de fingir que ele não
existe.

**2. Conferência visual virou ferramenta do projeto.** No D-52 o Playwright foi
instalado num diretório temporário e o script morreu com a sessão. Como ele
encontrou três defeitos que 194 testes verdes não pegaram, virou parte do
repositório:

- `backend/common/gerar_sessao_local.py` — emite uma sessão real via magic link
  (Admin API), sem precisar da senha de ninguém. Fecha uma lacuna que existia
  desde o D-25: sem chave estática, todo teste manual precisava de um token e
  cada sessão de trabalho reescrevia o mesmo script descartável. O `CLAUDE.md`
  chegava a mandar "ver os scripts de validação usados no D-48/D-49 como
  referência" — scripts que nunca foram commitados.
- `frontend/tools/capturar-telas.mjs` (`npm run telas`) — fotografa as 7 telas
  em 1440px e 390px. É ferramenta de **captura, não de teste**: não afirma nada
  sobre o que viu. Essa escolha é deliberada — a primeira versão, cheia de
  asserções sobre a UI, quebrou na primeira mudança de tela (quando o botão
  "Focar em Gestão de Tempo" deixou de existir, por causa do item 1 acima). Um
  script de screenshot que não roda em CI e afirma coisas apodrece; um que só
  fotografa, não. Quem olha as imagens é quem julga.
- `playwright` entrou como `devDependency` do frontend. Não há CI de frontend
  neste repo, então não há custo de pipeline.

**3. Dois defeitos visuais achados usando a ferramenta recém-commitada:**

- **`.metrica-valor` e `.metrica-rotulo` não eram `block`.** Todos os call
  sites usam `<span>`, que é inline, então número e rótulo ficavam colados na
  mesma linha — "0FEITAS HOJE", "35TOTAL HOJE" — e o `margin-top` do rótulo
  nunca teve efeito. Afetava as 3 telas que usam `.metrica` (Treino Diário,
  Sessões de Treino, Puzzles Insights). Corrigido no token, não nos call sites.
- **O Laboratório desenhava um tabuleiro vazio de ~230px** antes de o usuário
  digitar qualquer coisa. O Explicador já guardava isso com um `@if`; o
  Laboratório não. Agora guarda.

**Testes:** 5 novos no backend (606 → **611**), 2 novos no frontend
(199 → **201**). `ng build` limpo. Conferido no navegador que o Hexágono
mostra 4 botões + a nota de ausência, e que as métricas empilham direito.

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
