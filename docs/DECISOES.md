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

**4. Mais três achados, já usando a ferramenta commitada:**

- **O cabeçalho `sticky` encobria qualquer âncora.** Rolar até um elemento o
  deixava embaixo do cabeçalho — inclusive o link "pular para o conteúdo"
  criado no D-52, que portanto nascia quebrado. Corrigido com
  `scroll-padding-top` no `html`, com as alturas **medidas** no navegador (60px
  desktop, 100px no celular, onde a navegação quebra em duas linhas) em vez de
  chutadas. Conferido depois: o conteúdo passa a começar exatamente onde o
  cabeçalho termina, nas duas larguras.
- **As Sessões de Treino cresciam sem limite.** As 5 sessões vinham todas
  expandidas, com os 3 módulos e as descrições inteiras — 6188px só dessa
  seção, e o Agente 3 acrescenta uma sessão por semana, para sempre. Agora só a
  mais recente (a prescrição vigente, que é o que o usuário veio ver) abre
  sozinha; as demais mostram "3 módulos · 50 min" e um "Ver plano". A seção caiu
  para 3238px.
- **Perguntas Pendentes abria as 6 respostas de uma vez**, no topo do
  dashboard: 4054px de textareas vazias antes do radar, lendo como uma lista de
  tarefas. Agora só a primeira abre o campo; as outras mostram enunciado,
  miniatura e um "Responder esta". O enunciado de todas continua visível de
  propósito — a intenção é dar para escolher qual responder, não esconder o que
  está pendente. 4054px → 2814px, e um único botão primário em vez de seis.
- **Cartões de tema desalinhados** em Puzzles Insights: um nome de duas linhas
  ("Cálculo Profundo (4+ lances)") empurrava a barra de progresso para baixo e
  desalinhava a linha inteira. O título agora reserva as duas linhas.

O padrão dos três últimos é o mesmo e vale registrar: **o dashboard acumulava
tudo expandido**. Sessões, perguntas e histórico crescem com o uso, e nenhum
deles tinha teto. Expandir só o item vigente e resumir o resto manteve toda a
informação acessível sem transformar a home em metros de rolagem.

**Testes:** 5 novos no backend (606 → **611**), 7 novos no frontend
(199 → **206**). `ng build` limpo. Conferido no navegador que o Hexágono
mostra 4 botões + a nota de ausência, que as métricas empilham direito, que o
link de pular aterrissa abaixo do cabeçalho e que as sessões antigas abrem e
fecham.

---

### D-54 — A sessão de treino passa a ser executada, não só prescrita

O Agente 3 prescreve uma sprint de treino por semana desde o D-19, com
módulos citando livro, capítulo e página. Em 16/09/2026, uma consulta ao
banco mostrou o resultado disso:

| Prescritas | Concluídas | Eficácia medida |
|---|---|---|
| 5 | **0** | **0** |

`medir_eficacia.py` (D-37) só olha sessões com `data_concluida` preenchida.
Como nenhuma jamais foi concluída, **o agente que mede se o treino funcionou
nunca teve o que medir**: o loop adaptativo, que é o argumento central do
produto, nunca fechou uma única vez desde que foi construído.

A causa não era falta de vontade do usuário. A sessão era um texto com um
botão de "marcar como concluída" — não havia nada para *fazer* dentro dela, e
declarar conclusão de uma leitura que ninguém verifica é um gesto vazio.

**A sessão agora executa.** Nova tela `/sessao/:id` com os blocos em ordem:

- **blocos de estudo**, que são os módulos do Agente 3 tal como estavam
  (livro/capítulo/página preservados), concluídos ao marcar como lido —
  leitura o sistema não tem como verificar, e fingir que tem seria pior;
- **um bloco de prática**, que **não vem do LLM**: é montado pelo backend a
  partir da categoria do gargalo, com exercícios reais do catálogo, e fecha
  sozinho quando eles são respondidos no Treino Diário.

É esse segundo bloco que dá à sessão um fim objetivo em vez de um "eu acho
que terminei". E quando o último bloco fecha, `data_concluida` é gravada
**automaticamente** — que é exatamente o dado que o `medir_eficacia.py`
esperava. Verificado ponta a ponta contra o banco real: sessão iniciada, 3
blocos de estudo marcados, 12 exercícios respondidos via Stockfish, e a
sessão fechou sozinha. O contador saiu de 5/0/0 para 5/**1**/0 — a primeira
sessão concluída da história do produto, e a primeira elegível à medição.

**Decisões de desenho que valem registro:**

- **Nenhuma coluna de categoria foi criada.** `diagnostico_gargalo` já guarda
  `"CATEGORIA: título"` e `medir_eficacia.categoria_do_diagnostico()` já
  parseia esse formato. Derivar em tempo de leitura fez as 5 sessões antigas
  funcionarem na tela nova sem backfill nenhum — mesmo raciocínio do D-51.
- **A conclusão automática mora num GET**, o que é incomum e é deliberado:
  quem fecha o último bloco é `POST /treino/{id}/responder`, que não sabe
  (nem deveria saber) que aquele card pertence a uma sessão. Descobrir no
  próximo carregamento é o que faz a sessão terminar sozinha.
- **O bloco de prática não é marcável à mão.** Deixá-lo marcável devolveria
  exatamente o "eu acho que terminei" que esta decisão veio remover.
- **O botão manual continua existindo**, rebaixado a link secundário com o
  texto "Já fiz fora do app". Nem todo estudo acontece aqui, e remover a
  saída seria trocar um problema por outro.
- **`iniciar` é idempotente.** Sem isso, cada visita à tela empilharia mais
  uma dúzia de exercícios na fila do dia.
- **Categoria sem catálogo não trava a sessão**: o bloco nasce concluído e a
  tela explica a ausência. A honestidade fica no texto, não num bloqueio.

**Dois defeitos achados só por rodar**, com a suíte inteira verde:

1. `GET /treino/foco/disponibilidade` (D-53) contava as linhas do catálogo em
   Python, e o PostgREST corta a resposta em 1000 linhas. Com 1200 exercícios
   no banco, o endpoint reportava **120 e 280 onde havia 300 e 300** — errado
   em silêncio, sem erro nenhum, e piorando a cada exercício importado. Agora
   é `count="exact"` por categoria.
2. O bloco de prática dizia "Prática: **nenhum exercícios** de Tática" antes
   de a sessão começar — erro de concordância e, pior, mentira: o catálogo
   tinha material, a sessão é que não fora aberta.

**Testes:** 17 novos no backend (611 → **628**), 10 novos no frontend
(206 → **216**).

---

### D-55 — Exercícios "ache o melhor lance" de partidas OTB reais, e o fim do P-15

Pergunta do usuário: para tática dá para reutilizar os puzzles do Lichess,
mas e o treino de achar o melhor lance quando não há tática — quando o lance
certo é defensivo, posicional, ou só empata? Existe base para isso?

Existe, e não é o dump de puzzles. O Lichess publica um **banco de
broadcasts**: 1.235.275 partidas OTB reais de torneio em PGN. Baixei um mês e
inspecionei antes de escrever qualquer parser (AGENTS.md §2.3). Cada lance
traz `[%eval]`, `[%clk]` e a anotação do próprio Lichess:

```
24... b4?? { [%eval 2.24] } { Blunder. bxc4 was best. } { [%clk 0:34:44] }
```

Ou seja: para todo lance em que um titulado errou, já temos a posição, o
lance jogado, **qual era o melhor** e **quanto relógio restava**.

**O filtro central é exigir que o melhor lance seja quieto** — sem captura,
sem xeque, sem promoção. É ele que faz a posição ser posicional ou defensiva
em vez de tática disfarçada, e portanto material honesto para `ESTRATEGIA`.
Somado a isso: severidade `Mistake`/`Blunder` (imprecisão de GM raramente tem
resposta única o bastante), posição ainda indefinida antes do erro
(|avaliação| ≤ 300cp — "ache o melhor lance" numa partida ganha treina
conversão, que é outra habilidade), e queda ≥ 150cp.

**Isto encerra o P-15, inclusive a metade que o D-49 declarou impossível.** O
D-49 estava certo sobre puzzles: posição de puzzle é estática, não tem
relógio, logo não serve para `GESTAO_DE_TEMPO`. Broadcast tem relógio. Quando
o erro acontece com pouco tempo (≤ 120s), a categoria é gestão de tempo — e é
a única aqui que aceita lance não-quieto, porque errar com dois minutos é
falha de relógio seja qual for a natureza do lance. Esses cards são
**cronometrados com o mesmo tempo que o jogador original tinha**.

**O cronômetro conta de verdade.** Estourá-lo rebaixa a nota do SM-2 para a
de uma resposta "difícil": o fator de facilidade cai e aperta todos os
intervalos seguintes. `qualidade_lance` fica intacto — o lance pode ter sido
ótimo E ter demorado demais, e são dois julgamentos diferentes, cada um com
seu campo. Sem essa penalidade o cronômetro seria enfeite numa categoria cuja
falha medida É o tempo.

**Continuamos sem guardar a resposta certa**, mesmo tendo ela de graça na
anotação. Quem avalia é o Stockfish na hora, como no D-49. Isso resolve
sozinho a objeção mais séria a este formato — posição posicional costuma ter
vários lances defensáveis, e cobrar um só seria injusto: como medimos queda
de avaliação em vez de comparar com um gabarito, qualquer lance que não perca
nada passa como BOM.

**Licença é diferente e importa:** puzzles são CC0, broadcasts são **CC BY-SA
4.0**. Exige atribuição, então a procedência é gravada e exibida na tela —
depois da resposta, nunca antes (antes seria contexto que o jogador original
não tinha). É também o que transforma o exercício de volta em partida:
"GM Moranda, Wojciech × CM Klepek, Witold — Adolf Anderssen 2026".

**Um achado de qualidade que só apareceu rodando de verdade.** A primeira
execução trouxe 1200 exercícios em ~1100 partidas, todos do **mesmo dia**, de
opens juvenis ("Youth U14", "Open C"). Tecnicamente OTB, mas longe de
"partida real conhecida" — o ponto é aprender com quem joga bem. Acrescentei
o filtro `POSICIONAL_EXIGIR_TITULO`, apaguei o lote e reimportei: 1200
exercícios de **616 partidas em 69 torneios distintos**, com GM/IM/WGM.

**Tabela nova, e não uma coluna `fonte` em `exercicios_taticos`:** estes
exercícios são por construção os que **não** são táticos. Guardá-los numa
tabela chamada "exercicios_taticos" seria a mesma mentira silenciosa que o
D-49 recusou ao deixar ESTRATEGIA vazia. Além disso a procedência só faz
sentido aqui e viraria coluna nula na outra.

**Estado do catálogo depois do import** (16/09/2026): as 6 categorias do
Hexágono têm material pela primeira vez — TATICA 300, CALCULO 300,
ESTRATEGIA 300, GESTAO_DE_TEMPO 300, FINAIS 600, ESTRUTURA_DE_PEOES 600.

**Testes:** 47 novos no backend para o importador + 12 nos endpoints
(628 → **687**), 7 novos no frontend (216 → **223**).

---

### D-56 — A fila ganha teto e a sessão ganha caminho reto até ela

O D-55 acrescentou 1200 exercícios a um sistema onde o gargalo não era falta
de material. A fila cresce **10 cards por dia** (D-48), venha alguém
respondê-los ou não, e o que não é respondido vira atraso acumulado. Hoje são
19 vencidos e 9 atrasados sobre 632 agendados até novembro; em um mês parado,
são centenas — e uma tela que abre com centenas de cards é a forma mais
eficiente de fazer alguém desistir.

Pior: o bloco de prática do D-54 caía no fim dessa mesma fila. O botão "Ir
para os exercícios" da sessão levava a uma tela onde os 12 cards dela ficavam
atrás de dezenas de outros vencidos. A sessão tinha começo e fim, mas nenhum
caminho reto entre os dois — exatamente o que ela veio resolver.

**Duas mudanças, uma para cada metade do problema:**

1. `GET /treino/fila?sessao_id=<uuid>` devolve só os exercícios daquela
   sessão que ainda não foram respondidos. Dentro da sessão o critério não é
   "venceu hoje" e sim "ainda não respondido": um card respondido agora é
   reagendado para amanhã e sumiria da sessão no meio dela.
2. `TREINO_TETO_FILA` (default 20) limita quantos cards a tela mostra de uma
   vez.

**O teto corta a exibição, nunca o agendamento.** Os cards cortados continuam
vencidos e aparecem conforme os outros são respondidos. E a resposta carrega
`vencidos_total` com o número real, que a tela exibe ("Mostrando 20 de 47"):
esconder o tamanho do atraso seria trocar um problema de usabilidade por uma
mentira por omissão, e a diferença entre as duas coisas é justamente o que
separa um produto honesto de um que só parece organizado.

**Testes:** 4 novos no backend, 6 no frontend.

---

### D-57 — Cadência: o diagnóstico para de esconder o efeito do relógio

A ressalva mais séria do produto estava documentada no `ESTADO.md` e invisível
na tela: **74% do corpus analisado é blitz de 3 a 5 minutos**, e não existia
coluna de cadência em `partidas` — não dava nem para filtrar. A tag mais
frequente ser `calculo_tatico_deficiente` podia significar "calcula mal" ou
"joga rápido demais", e não havia como distinguir. Um produto que se propõe a
dizer onde você é fraco não pode entregar esse diagnóstico sem a ressalva.

`partidas` ganhou `cadencia`, `tempo_base_segundos` e `incremento_segundos`,
derivadas do header `TimeControl` do PGN pelos cortes do Lichess sobre
`base + 40 * incremento`. Adotar a convenção de uma plataforma conhecida, em
vez de inventar faixas, mantém o vocabulário familiar e comparável com as
estatísticas que o usuário já vê lá.

**Não existe fallback, e isso é o principal.** `parse_time_control` (do
backfill de tempos) chuta 300s quando falta o header, e faz bem: lá o chute é
melhor que não calcular nada. Aqui seria pior que admitir — uma partida sem
header viraria "blitz" e contaminaria exatamente a estatística que a coluna
veio limpar. `DESCONHECIDA` é um valor legítimo e frequente.

**Backfill real do acervo:** 240 partidas classificadas — 142 blitz, 30
rápidas, **68 sem cadência registrada** (28% do corpus; parte das partidas do
Lichess vem sem o header). Nenhuma bullet, nenhuma clássica.

A classificação passou a acontecer em `common_ingestao.insert_game`, por onde
os dois coletores passam, e em `analisar_pgn_avulso.inserir_partida` — num
lugar só cada, para que nenhuma partida nova volte a nascer sem ritmo.

**A ressalva agora aparece no Hexágono**, acima do diagnóstico e não depois
dele: "59,2% das 240 partidas analisadas são Blitz. O diagnóstico abaixo
mistura a sua habilidade com o efeito do relógio." Só aparece quando uma
cadência de fato passa de 50% do corpus — abaixo disso viraria ruído em toda
visita.

**O que isto ainda NÃO faz**, e é o próximo passo natural: filtrar o próprio
Hexágono por cadência. Hoje a coluna existe, está preenchida e a contaminação
está visível; separar "o gargalo do Edson em clássicas" de "o gargalo do Edson
em blitz" exige mexer no Agente 2 e decidir o que fazer com as análises já
gravadas — decisão maior, que merece a sua própria entrada.

**Testes:** 20 novos em `backend/common/test_cadencia.py` + 4 no endpoint de
composição + 4 no frontend.

---

### D-58 — Amostragem por reservatório no catálogo posicional

A primeira importação do D-55 aceitava os primeiros N exercícios de cada
categoria e parava de ler assim que todas batiam o teto. O efeito só apareceu
ao olhar os dados: **1200 exercícios tirados de um único dia**, de meia dúzia
de torneios. Aumentar o teto não resolveria, porque o viés não estava no
tamanho da amostra e sim em *onde no arquivo* a leitura parava.

Agora o import lê o mês inteiro e sorteia com o algoritmo clássico de
reservatório (Vitter R): enquanto cabe, guarda; depois, o k-ésimo candidato
entra com probabilidade N/k. Custa ~10 minutos por mês pedido, e devolve
material espalhado por todos os torneios daquele mês, sem nunca carregar o
mês inteiro em memória.

O teste que importa não verifica o tamanho da amostra — verifica que ela
**alcança o fim do arquivo**: com 5 vagas e 1000 candidatos, em 40 rodadas a
amostra tem que tocar a segunda metade quase sempre.

**Resultado medido**, reimportando sobre 3 meses (125.974 partidas lidas):
a variedade foi de **69 para 510 torneios distintos** e de 616 para 1.764
partidas, com 451 exercícios envolvendo um GM. O catálogo posicional passou de
1.200 para 2.381 exercícios.

**Testes:** 5 novos.

---

### D-59 — Limpeza conservadora dos títulos de capítulo

Sujeira de OCR vinda dos livros digitalizados aparecia na tela como citação de
fonte: `Fonte: Meu Sistema · | OJOGO CONTRA A. A PEÇA C CRAVADA · pág. 127`.
Eram 7 linhas de `indice_conceitual` em 3 títulos distintos — pouca coisa, mas
visível ao usuário toda vez que uma sessão de treino cita a fonte.

`limpar_titulo_capitulo()` passa a rodar no import e tira a sujeira das
**pontas**: barras verticais que eram bordas de tabela, vírgulas de quebra de
linha, aspas tipográficas, espaço repetido.

**Deliberadamente não mexe no miolo.** "OJOGO" continuaria passando, e é
proposital: adivinhar onde cabe um espaço estragaria títulos legítimos, e
errar em silêncio num dado que vai para a tela é pior que deixar passar. Os
três títulos existentes foram corrigidos à mão no banco, incluindo o que o
limpador genérico não alcança.

**Testes:** 6 novos.

---

### D-60 — Reconciliação "de/para" entre a documentação e o projeto real

Auditoria de todos os 10 documentos de conhecimento (`AGENTS.md`, `CLAUDE.md` e
os 8 de `docs/`) contra o código, o banco de produção e os workflows, em
16/09/2026. Não houve mudança de comportamento do sistema: só de documento.

**Por que fazer isso como trabalho próprio.** Os documentos foram atualizados a
cada entrega, mas sempre pela ponta que a entrega tocava. O que apodrece é o
resto — a afirmação de outra seção que a entrega tornou falsa sem ninguém
reler. Esse tipo de erro não aparece em teste nenhum e só custa caro quando um
agente age sobre ele.

**Os três achados que eram perigosos, não só velhos:**

1. **`ESTADO.md` §6 mandava garantir policy de RLS para `anon`.** O comentário
   era verdade no D-16 e virou o oposto no D-23/D-24, que removeram todas as
   policies `to anon` justamente porque elas vazavam dado pessoal (P-13). Um
   agente seguindo a instrução recriaria o vazamento achando que corrigia
   RLS. Substituído pela regra atual mais uma query que falha alto: o schema
   inteiro tem que devolver zero policies de `anon`.
2. **`ESTADO.md` §5 dizia que a autenticação é "por múltiplas chaves
   nomeadas".** O `X-API-Key` foi aposentado no D-25 e removido do código numa
   auditoria pós-D-49. `ARQUITETURA.md` e `OPERACAO.md` já diziam isso; só o
   documento de estado ficou para trás, e é o que um agente lê primeiro para
   saber o que existe.
3. **`AGENTS.md` afirmava "não é multiusuário".** Factualmente errado desde o
   D-28: o pipeline percorre `perfis_usuario`, as tabelas raiz têm RLS por dono
   e as rotas tiram o `user_id` da sessão sem fallback. A frase convidava a
   simplificações que seriam vazamento no segundo cadastro.

**Outros ajustes:** `ROADMAP_EVOLUCAO.md` ganhou um aviso no topo — as Fases 12
a 18 foram todas entregues, e o documento lido de cima parecia um plano
pendente; `GUIA_DO_PROJETO.md` não mencionava `/treino` nem as sessões, isto é,
o guia do dono não falava da parte que ele usa todo dia; `ARQUITETURA.md` não
tinha a rota `/sessao/:id` nem 4 componentes; `OPERACAO.md` §7 não listava 8
variáveis de ambiente que o código lê; `BANCO.md` §3 não tinha os enumerados de
`cadencia`, `origem` e `severidade`.

**Uma decisão de forma:** a lista nominal de módulos de teste que `ESTADO.md`
mantinha foi **removida**, não corrigida. Ela dizia "35 módulos" quando já eram
37 — um terceiro lugar para manter à mão, fadado a divergir dos dois que a R8
já exige. No lugar ficou o par de comandos que compara disco e CI; o número
certo se descobre, não se memoriza.

**Achado lateral, registrado para não virar falso alarme:** `current_date` do
Postgres é UTC, mas a API decide o "hoje" da fila em `America/Sao_Paulo`
(`_hoje_local()`). Entre 21h e meia-noite de Brasília as duas discordam em um
dia, e a query de verificação parece acusar cards que a tela não mostra. Não é
defeito da fila — a query da seção 6 do `ESTADO.md` passou a medir no fuso
certo.

---

### D-61 — A automação passa a avisar quando quebra, e o deploy passa a provar o que subiu

**O incidente.** Em 15/09/2026 o commit `53f19d2` fixou `numpy==2.5.2`, que
exige Python ≥ 3.12. Os três workflows e o `Dockerfile` pinavam 3.11. Desde
então **toda** execução de CI morria no passo *Instalar dependências Python*,
antes de rodar um teste sequer. Passou despercebido por dois dias porque o venv
local é 3.12.6: os 726 testes rodavam verdes aqui enquanto nada subia lá.

O estrago, medido antes da correção:

- backend de produção congelado no commit `9ae7e6a` (D-49) — **D-50 a D-59
  estavam no git e nunca foram ao ar**;
- **frontend e backend divergentes em produção**: a Vercel publica a cada push
  e já servia a rota `/sessao/:id`, enquanto o backend respondia 404 em
  `/sessoes/{id}/execucao` e `/partidas/composicao`. A tela existia e quebrava;
- **nenhuma partida coletada desde 15/09 23:20**;
- o pipeline semanal falharia na segunda seguinte pelo mesmo motivo.

**A correção de fundo foi alinhar os quatro lugares em 3.12**, não rebaixar o
`numpy`: produção deve rodar o que foi testado, e não uma combinação que
ninguém exercita. As 18 dependências fixadas estão instaladas nessas versões
exatas sob 3.12.6 com a suíte verde — prova empírica melhor que um dry-run de
resolvedor.

**Mas o defeito não foi o pin.** Foi ninguém ter percebido. Os três workflows
já escreviam um resumo detalhado no `GITHUB_STEP_SUMMARY` — que só existe para
quem abre a página do run. **Alerta que exige alguém ir olhar não é alerta.**

Cada workflow ganhou um passo final que abre uma issue rotulada
`falha-automacao`, ou comenta na que já estiver aberta. Issue em vez de e-mail
ou webhook: não exige secret novo nem serviço externo, e fica aberta até alguém
fechar — sobrevive a não ser lida na hora.

Duas sutilezas que `if: failure()` sozinho não cobriria:

1. **Falha parcial silenciosa.** No pipeline diário quase toda etapa de coleta
   tem `continue-on-error: true`. É a decisão certa (a queda do Chess.com não
   pode matar a coleta do Lichess), mas cria um job verde que coletou zero
   partida. A condição do alerta testa o `outcome` de cada etapa, não só o
   status do job.
2. **Health check que não prova nada.** `/health` responder 200 não diz que o
   commit subiu — responde 200 igual numa revisão antiga, e foi exatamente
   assim que o backend ficou dois dias parado com o check verde. O passo agora
   compara a imagem que o Cloud Run está **de fato servindo** com a tag deste
   commit, e falha alto quando divergem.

**Lição de método, registrada porque foi minha:** relatei "726 testes OK, build
limpo" como se fosse verificação de entrega. Era verificação **local**. Entre o
teste verde e o usuário existem CI, deploy e produção, e nenhum dos três tinha
sido olhado. O `CLAUDE.md` deste repositório já pedia "prefira verificar de
verdade"; verificar de verdade inclui perguntar se o que passou chegou.

---

### D-62 — A coleta do Lichess para de reconstruir o PGN e passa a pedir o oficial

**O sintoma que abriu a investigação** foi estatístico, não um erro: `cadencia`
`DESCONHECIDA` em **67 de 67** partidas do Lichess, contra **0 de 161** do
Chess.com. 100% de um lado e 0% do outro não é ruído de dado faltante — é
sistema.

**A causa.** `fetch_games()` pedia só `opening=true`. Sem `pgnInJson`, o NDJSON
vem sem a chave `pgn`, e `build_pgn()` caía no ramo de reconstrução: montava um
PGN de seis cabeçalhos a partir da lista de lances. `TimeControl` não era um
deles. O dado nunca faltou na fonte — a resposta já trazia
`clock: {initial, increment}` e `speed`; nós é que pedíamos menos do que
precisávamos e jogávamos o resto fora.

Isso derrubou uma afirmação que o `ESTADO.md` repetia como se fosse
característica do acervo: "não há nenhuma partida clássica". **Havia três.**
Elas estavam escondidas atrás da nossa própria ingestão.

**A correção** é pedir `pgnInJson`, `tags` e `clocks`. `build_pgn()` não mudou
uma linha: ele já preferia `game["pgn"]` quando existisse, e a reconstrução
volta a ser o fallback que sempre deveria ter sido. As três colunas de cadência
passam a ser preenchidas na coleta, como o Chess.com já fazia, reusando
`campos_de_cadencia()` do D-57. `evals` ficou de fora de propósito: engordaria
todo PGN com uma avaliação que ninguém lê hoje.

**O backfill precisou ser outro script.** `backfill_cadencia.py` lê o
`TimeControl` do PGN guardado, e aqui o PGN guardado *era* o problema — rodá-lo
devolveria DESCONHECIDA de novo, corretamente. `backfill_pgn_lichess.py`
rebusca o PGN na fonte (endpoint de exportação por IDs, até 300 por chamada).

**A trava de segurança e o que ela revelou.** Regravar o PGN de partidas já
analisadas é perigoso: `lances_criticos.numero_lance` aponta para aquela
numeração. Por isso o script compara a sequência de lances antes de gravar, e
foi essa comparação que expôs um segundo defeito, mais sério que o primeiro —
`build_pgn()` tinha um `break` silencioso ao topar com SAN que não parseava:

- `F031uGaP` foi gravada com **zero lances** e virou `falhou` no Stockfish;
- `wSfk0zwh` foi gravada com **um lance** e passou por `concluido`, isto é,
  entrou na estatística do produto como partida analisada.

As duas são `variant: fromPosition` — partem de um FEN próprio, e a
reconstrução sempre começava da posição inicial padrão. O `d4` gravado é um
lance **diferente** do `d4` jogado. Daí os três vereditos do classificador:
`igual` (85 casos, troca só acrescenta cabeçalho), `truncado` (prefixo: a
numeração existente continua válida) e `posicao_errada` (divergência com causa
conhecida). Só `divergente` — divergência sem explicação — segue recusada.

Nos dois casos recuperados o script apaga `lances_criticos` e devolve a partida
para `pendente` (R7). Reanalisadas, as duas foram recusadas pelo motor com
"variante não padrão: From Position" — o comportamento correto. **O ganho não é
ter mais partidas analisadas, é uma partida errada ter deixado de se passar por
certa.**

**Resultado medido**, no corpus inteiro: `DESCONHECIDA` 68 → 1 (a única
restante é um PGN colado à mão, sem fonte para rebuscar); `RAPIDA` 30 → 78;
`CLASSICA` 0 → 3; `BLITZ` 142 → 187.

Duas ressalvas sobre como ler isso, porque o produto é multiusuário e o
Hexágono filtra por dono:

- **as 3 clássicas são do `Gazola`**, o segundo perfil. O dono principal
  continua com zero partida clássica, então a ressalva de sempre sobre o
  diagnóstico dele segue de pé;
- a tela dele passou de "59% blitz" para **72,3%**, não 69,5% — este último é
  o número do banco somado, que não descreve jogador nenhum.

Em ambas as leituras o viés **aumentou**. A correção não melhorou o retrato do
corpus, tornou-o honesto, e é esse o ponto.

**Um item do plano que a investigação recusou.** Eu havia listado "o
enriquecimento do Lichess cobre 18 de 67 partidas" como lacuna a corrigir nesta
fase. Investigado: `players.<cor>.analysis` só existe para partidas que foram
analisadas no servidor do Lichess, e pedir `evals`/`accuracy` não muda isso —
numa amostra real de 30 partidas, 15 têm e 15 não têm. É limite da fonte, não
do nosso pedido. Fica registrado como tal em vez de virar tarefa que não tem
como ser concluída.

**Testes:** 24 novos (750 no total).

---

### D-63 — O Hexágono ganha recorte por cadência, e "From Position" volta a ser analisável

Dois itens do planejamento de 17/09 (C1 e M1), feitos juntos porque são sobre a
mesma coisa: **a confiabilidade do diagnóstico**. Não adianta acelerar aquisição
enquanto o número central do produto mistura cadências.

**C1 — a trava de variante era larga demais.** `validate_standard_game()`
rejeitava qualquer `Variant` que não fosse "standard". Mas "From Position" é
xadrez com as regras de sempre a partir de uma posição própria: python-chess
lê `[FEN]`/`[SetUp]` em `game.board()`, a numeração vem de
`board.fullmove_number` e o motor avalia qualquer FEN legal — **nenhuma outra
linha do analisador precisou mudar**. A trava virou lista de permissão
(`VARIANTES_ANALISAVEIS = {"standard", "from position"}`); Crazyhouse, Atomic,
Antichess e companhia continuam recusadas porque mudam as regras, e Chess960
tem a própria checagem.

Isso nunca tinha aparecido porque, antes do D-62, a reconstrução do PGN
**apagava o header `Variant`** — essas partidas eram analisadas em silêncio a
partir da posição inicial errada. O D-62 as desmascarou como `falhou`; o D-63
as torna analisáveis de verdade. O teste que importa não é "passa na
validação": é o motor receber o FEN do cabeçalho na primeira avaliação, e não
um FEN começado por `rnbqkbnr`.

**M1 — o recorte por cadência, e três decisões de desenho.**

1. **Dentro do mesmo jsonb, não em linhas novas.** `metricas.por_cadencia`
   guarda um hexágono completo por cadência, com **exatamente o shape** do
   objeto de primeiro nível (menos `frequencia_tags_por_eco`, informativo e
   pesado). Consequências: zero migração; o Agente 3 e a medição de eficácia
   continuam lendo uma linha só e não enxergam mudança; a tela reaproveita o
   mesmo render para o total e para qualquer recorte; e **as 5 análises
   gravadas antes não precisam de backfill** — o componente trata a ausência
   da chave como "só o total existe" e nem mostra o seletor. Alternativa
   recusada: uma linha por `(user, cadencia)`, que obrigaria a reescrever
   todos os leitores para um ganho nenhum.

2. **O gargalo de primeiro nível continua sendo o de TODAS as partidas.** É
   ele que o Agente 3 lê para prescrever e que `medir_eficacia.py`
   acompanha. Fazer a prescrição seguir uma cadência é decisão de produto
   ("você quer treinar para qual cadência?"), não de cálculo — e a cadeia
   diagnóstico → sprint → eficácia ainda nem fechou uma vez com dado real. O
   recorte **informa; ainda não prescreve.** Quando o gargalo do recorte
   diverge do do conjunto, a tela diz isso ao lado do radar, com a ressalva
   explícita de que a sprint abaixo segue o conjunto. Esse aviso é o achado
   que o recorte existe para expor.

3. **Mínimo de 3 partidas distintas para uma cadência ganhar bloco**
   (`CADENCIA_MIN_PARTIDAS`). Uma ou duas partidas não sustentam hexágono
   nenhum, e "Cadência desconhecida · 1 partida" viraria chip permanente no
   seletor para quem colou um PGN à mão. Diagnóstico sem cadência conta no
   total e em bloco nenhum.

O narrador (Gemini) passa a receber `gargalo_por_cadencia` e a instrução de
dizer explicitamente quando ele muda de uma cadência para outra — "é a
informação mais útil para o jogador, porque separa erro de entendimento de
erro sob pressão de relógio" — e de **não forçar diferença** quando é igual.

**A ressalva do D-57 vira ação.** O aviso "72% das partidas são blitz" agora
termina num botão: *Ver o Hexágono só de Blitz*. Em vez de só alertar que o
diagnóstico está contaminado, a tela oferece o hexágono descontaminado. O
botão some quando o recorte já é o da dominante.

**Resultado medido (17/09/2026, primeira execução).** Dono principal: gargalo
do conjunto **TATICA**; em blitz **TATICA** (176 partidas); em rápidas
**CALCULO** (67 partidas). **O gargalo muda com a cadência** — a hipótese do
D-57 deixou de ser hipótese. A leitura que os dados sugerem: sob relógio curto
o erro dominante é tático puro; com mais tempo, o que sobra são iniciativa,
segurança do rei e profilaxia — as tags de CALCULO. A sprint em vigor segue
TATICA, pelo desenho acima; se o objetivo do jogador for jogar rápidas, o alvo
certo hoje seria outro. É a primeira vez que o produto consegue dizer isso.

**Incidente na mesma execução.** As duas análises foram gravadas **sem
narrativa**: o Gemini respondeu `429 RESOURCE_EXHAUSTED` — teto mensal de
gastos do projeto estourado (ver `ESTADO.md` §0). Nada no cálculo depende do
modelo, então hexágono, gargalo e recorte estão corretos; a tela mostra
"Nenhuma narrativa textual disponível", que é o estado honesto. Decidi
**manter** as linhas em vez de apagá-las e voltar à narrativa de 14/09: os
números novos são mais corretos (748 diagnósticos, cadências pós-D-62) e a
ausência da narrativa é a consequência visível de um problema que só o dono do
console do Google resolve.

**Testes:** 4 no analisador, 9 no Agente 2, 9 no componente.

---

### D-64 — A fila para de crescer no ritmo da ingestão, e a pergunta sem resposta possível some

Dois itens do planejamento de 17/09 (M2 e M3). Nenhum dos dois consome Gemini.

**M2 — a válvula que faltava na fila de treino.** Até aqui todo card novo era
agendado a partir de `hoje`: cada execução do pipeline jogava mais 10 cards
vencidos por cima dos que já estavam atrasados. A fila crescia no ritmo da
**ingestão**, não no do consumo. Medido antes de mexer: 657 cards, **655 nunca
respondidos**, 2 respondidos na vida do recurso, 61 dias de horizonte.

Duas regras substituem isso:

1. **Material novo vai para o fim da fila** (`primeiro_dia_livre`): começa no
   dia seguinte ao último já agendado para um card ainda não respondido. Só
   contam os nunca respondidos — um card que já foi revisado e volta em 30 dias
   pelo SM-2 é trabalho previsto, não backlog, e deixá-lo empurrar o material
   novo adiaria a fila para sempre.
2. **Horizonte de `TREINO_HORIZONTE_DIAS`** (60): nada é agendado além disso. O
   que não cabe **não se perde** — o script reconsulta os diagnósticos
   elegíveis a cada execução e os pega quando a fila drenar.

Por que um teto e não "agenda tudo, só que longe": prometer trabalho para daqui
a seis meses é ficção. Até lá o diagnóstico envelheceu, o jogador mudou, e a
fila vira um número que só serve para intimidar.

Verificado em dado real na mesma hora: o dono principal recebeu **0 cards**
("fila cheia até 2026-11-18") em vez de mais 4 vencidos hoje; o segundo perfil,
com fila curta, recebeu 3 normalmente. A válvula é por usuário, como tem de
ser.

**M3 — perguntas pendentes ganham prazo de validade.** 6 pendentes, **todas de
partidas de 10 dias atrás**, **nenhuma respondida desde que o recurso existe** —
e permanentes no topo do dashboard, acima do próprio diagnóstico.

O diagnóstico honesto: a pergunta é sempre "no lance 16, o que você estava
pensando?". Ela só tem resposta enquanto o jogador lembra do momento. Depois
disso não é tarefa pendente, é entulho que finge ser tarefa.

A régua é a data da **partida**, não a da pergunta — perguntar hoje sobre um
jogo de três meses atrás nasce morto do mesmo jeito. Por isso um único
`PERGUNTA_VALIDADE_DIAS` (14) governa as duas pontas: não gerar, e expirar. O
status vira `EXPIRADA` em vez de a linha ser apagada, porque "existiu e não foi
respondida" é justamente o dado interessante sobre o recurso. A tela lista só
`PENDENTE`, então elas somem de lá sozinhas.

Data ilegível ou ausente **mantém** a pergunta viva: sumir com ela por causa de
um campo que não conseguimos ler seria pior que deixar uma pergunta velha na
tela. As 6 atuais estão em 10 dias — sobrevivem mais 4.

**Na tela**, só a primeira pergunta renderiza; o resto fica atrás de "Ver as
outras N". Seis cartões com miniatura de tabuleiro ocupavam quase metade da
altura da página acima do radar. Uma pergunta por vez lê como convite; seis,
como cobrança. O selo continua contando **todas** — esconder o resto não pode
esconder o tamanho do que está pendente.

**Achado lateral registrado:** `gerar_perguntas_pendentes.py` **não** usa LLM —
o texto é template fixo, "para nunca vazar dica do erro". A suspeita de que o
recurso queimava Gemini à toa estava errada; o custo dele era atenção, não
cota.

**Testes:** 11 no backend, 5 no componente. Dois testes do D-53 foram ajustados
para expandir a lista antes de afirmar sobre a segunda pergunta.

---

### D-65 — Importar as próprias partidas sob demanda: de até 7 dias para minutos

Item F1 do planejamento de 17/09, e o maior bloqueio de mercado que a varredura
achou. Até aqui o primeiro valor do produto dependia de **dois crons**: a coleta
das 6h e o Agente 2 de segunda-feira. Um usuário que se cadastrasse numa
terça-feira à tarde esperava **até 7 dias** para ver um Hexágono — e o estado
vazio da tela só oferecia "cole um PGN", que resolve uma partida, não o
diagnóstico.

`POST /perfis/importar` responde **202** e roda em `BackgroundTasks`, o mesmo
padrão de `/analisar-pgn`: o trabalho leva minutos e segurar a resposta só
produziria timeout. Ele faz o pipeline diário inteiro para uma pessoa só —
coleta, Stockfish, Agente 1, Agente 2 — disparado por ela.

**Três economias deliberadas**, porque esta é a rota mais cara que existe:

1. **Teto de `IMPORTACAO_MAX_PARTIDAS`** (10) partidas por execução. 10 bastam
   para o Agente 2 achar um gargalo (ele exige 5 diagnósticos numa categoria)
   sem transformar um clique em dezenas de chamadas pagas.
2. **Sem gerar resumo por partida.** `executar_pipeline_partida` ganhou
   `gerar_resumo=False`. A narrativa por partida é a parte mais cara em Gemini
   e a menos urgente — só é lida quando alguém abre AQUELA partida no
   Analisador. O pipeline diário as gera depois, no seu ritmo.
3. **Limite diário de 3** (`LIMITE_DIARIO_IMPORTAR_PARTIDAS`), o menor de todos
   em `LIMITES_DIARIOS_ENV`. A rota serve ao onboarding, não ao uso repetido.

**O achado que mudou o desenho da autenticação.** A API de partidas do Lichess
responde **404 sem `Authorization`** — verificado em 17/09/2026, com e sem
token, lado a lado. E o Cloud Run **não tem `LICHESS_TOKEN`**: o D-20 manda só
4 variáveis para produção. Então a importação usa **o token OAuth do próprio
usuário** (`obter_access_token_lichess`, D-33), com a env var como reserva. É o
desenho correto para multiusuário de qualquer forma — cada importação corre sob
a credencial de quem pediu, não sob uma chave compartilhada. Chess.com não pede
credencial nenhuma e funciona sempre.

Quando o usuário tem Lichess cadastrado mas nenhum token, isso é **dito na
resposta**, não escondido no log: sem essa frase ele veria só partidas do
Chess.com chegando e não teria como saber por quê.

**`GET /perfis/importacao` não tem tabela de job.** O progresso é lido do
próprio dado sendo produzido (`partidas.status_processamento`, diagnósticos,
hexágono). Uma tabela de controle poderia divergir do que de fato aconteceu;
estas contagens não têm como. `pronto` exige **ter o Hexágono**, não apenas ter
terminado de processar — "pronto" é ter o que o usuário veio ver.

**O limite conhecido desse desenho, e como a tela lida com ele:** durante a
COLETA ainda não existe partida pendente, então `em_andamento` é falso embora
nada tenha terminado. Para um usuário novo — o alvo do recurso — esse é
justamente o primeiro minuto. A tela trata `partidas == 0` como "Buscando suas
partidas…" antes de olhar `em_andamento`, e a frase do último caso
("Preparando o seu diagnóstico…") é verdadeira tanto coletando quanto
calculando. Afirmar a fase errada seria pior que falar de forma mais geral.

**Verificado com a conta real**, e o método importa: como o dono principal já
tem todas as partidas coletadas, a importação vira quase um no-op que ainda
assim exercita o caminho inteiro — custo de **uma** chamada de Gemini. Resultado
medido: 202 com `fontes: ["chesscom","lichess"]`, coleta das duas plataformas
sem erro, e uma `analises_hexagono` nova com narrativa de 2.074 caracteres. De
quebra, essa execução devolveu a narrativa que o estouro de cota do D-63 tinha
deixado vazia.

**Testes:** 9 nos endpoints, 6 no componente. O teste do estado vazio foi
atualizado: "Analisar minha primeira partida" deixou de ser a única saída e
virou a alternativa ("Colar um PGN").

### D-66 — Os eventos de erosão ganham formato de treino: "Refazer o trecho"

**Data:** 17/09/2026

**Contexto.** Desde o D-27 o pipeline detecta dois tipos de lance crítico. O
`PICO` é um lance: houve um erro isolado grande, existe um "lance certo", e
treiná-lo é mostrar a posição e pedir o lance — foi isso que o D-48 fez. A
`EROSAO` é outra coisa: uma janela de 8 lances do jogador em que a posição
escorregou **sem nenhum erro isolado grande o bastante para virar pico**.

Por não haver um lance certo a pedir, o D-48 a deixou de fora explicitamente
("EROSAO é uma janela de vários lances, sem um único 'lance certo' bem definido
pro formato de drill, fica fora do v1"). Ela ficou fora também do D-49 e do
D-55. Em 17/09/2026 eram **106 eventos** — todos com `fen_antes_lance`,
`numero_lance_fim` e diagnóstico prontos, todos parados. O detector trabalhava,
o Agente 1 diagnosticava, e nada daquilo virava treino.

**Decisão: o formato é refazer a janela.** Se a erosão é uma sequência, treiná-la
é jogar a sequência de novo. O jogador recomeça na posição onde a janela abriu e
joga os mesmos 8 lances contra o motor; no fim, mede-se a **mesma coisa que
detectou o evento** — a queda líquida de win% entre o começo e o fim da janela.
`detectar_erosao` calcula `janela[0].win_percent_before − janela[-1].win_percent_after`,
e o drill calcula exatamente isso, com a mesma função de conversão e a mesma
perspectiva de cor. Nenhum gabarito foi inventado: o instrumento que criou o
card é o instrumento que dá a nota.

**O adversário joga no rating do adversário real.** Stockfish inteiro
transformaria toda tentativa em derrota e, via SM-2, prenderia o card na nota
mínima para sempre — um drill impossível de vencer não ensina, só pune. Um motor
fraco demais daria um "você segurou" que não significa nada. A referência certa
é quem estava do outro lado naquele dia: `UCI_Elo` recebe o `rating_oponente` da
partida (105 dos 106 eventos têm), com o `rating_proprio` como segunda opção e
1600 como último recurso. A força volta ao máximo num `finally`, porque o motor
é uma instância só compartilhada por todas as requisições (R3): sair de lá com
`UCI_LimitStrength` ligado envenenaria a próxima análise de partida com um
número errado, sem aparecer como erro em lugar nenhum.

**Nenhuma avaliação aparece durante o trecho.** Isso é o desenho, não uma
omissão: erosão é justamente o que se perde sem perceber. Dizer "-4%" a cada
lance transformaria a janela em oito exercícios táticos com placar, e o drill
deixaria de medir aquilo que nomeia. A curva inteira — quanto cada lance custou
— aparece de uma vez no fim, que é quando ela vira informação útil: dá para ver
em que ponto a posição começou a escorregar.

**A nota.** `BOM` abaixo de `EROSAO_THRESHOLD_PERCENT` (15%, o mesmo limiar que
define o evento): segurar a janela abaixo dele significa que, pelo instrumento
que gerou este card, não houve erosão desta vez. Entre o limiar e a queda
original, `SUBOTIMO` (errou de novo, errou menos). Repetir ou piorar, `RUIM`. O
alvo absoluto é deliberado — um critério só relativo ("caiu menos que da outra
vez") deixaria o card sem nenhuma forma de se formar.

**Sem origem nova no schema.** O D-49 e o D-55 acrescentaram origens
(`exercicio_tatico`, `exercicio_posicional`) porque apontavam para tabelas
novas. Aqui não: um card de erosão continua sendo `origem = 'lance_critico'`
com `lance_id` preenchido, e o que muda o formato é `lances_criticos.tipo_evento`,
que já existe. Uma quarta origem guardaria em duas colunas um fato que só uma
delas conhece. A única coluna nova é `progresso_trecho` (jsonb): os SAN já
jogados e as leituras de win%. **A posição corrente nunca vem do cliente** — é
reconstruída pelo replay desse histórico sobre `fen_antes_lance`, e o cliente só
manda o texto do lance. Ao fechar a janela a coluna volta a `null`: guardar a
linha jogada faria a próxima repetição virar leitura do próprio gabarito.

**Cota diária própria.** Um card de pico é uma decisão; um de erosão são 8
lances com resposta do motor a cada um — umas oito vezes o trabalho.
Enfileirá-los por ordem de chegada faria um dia valer oito vezes outro, que é o
mesmo erro do D-64 (medir a fila em linhas em vez de em esforço) numa escala
diferente. `TREINO_TRECHOS_POR_DIA` (default 2) dá cota própria a eles e o resto
do dia é completado com picos. Em 0, o recurso fica desligado sem deploy.

**Dois achados durante a implementação:**

1. **O mate teria recebido o pior veredito possível.** Numa posição de xeque-mate
   o Stockfish devolve `{'type': 'mate', 'value': 0}`, e zero não tem sinal:
   `evaluation_to_cp` lê isso como +10000, ou seja, vantagem das **brancas**,
   seja quem for o matado. Quem desse mate de pretas no meio do trecho receberia
   win% ≈ 0 e um `RUIM` catastrófico pelo melhor lance possível. `processar_partida`
   nunca cruzou com o caso porque para no lance anterior ao mate
   (`if board.is_checkmate(): break`). A correção não é perguntar melhor ao
   motor: é não perguntar. Posição terminal o tabuleiro já resolve — mate a
   favor é 100, contra é 0, empate é 50.

2. **O aviso de "trecho reiniciado" sumia da tela.** Quando o progresso fica
   inconsistente, o servidor devolve 409 e zera o trecho; o componente mostrava
   o aviso e em seguida chamava `carregarFila()`, que começa com
   `erro.set(null)`. O resultado seria o trecho voltando ao começo sem nada
   explicando por quê. O aviso passou a ser posto **depois** da recarga.

**Verificado em produção, com partida real do dono dos dados.** Card 760,
janela dos lances 23–30, adversário de 1988 no Lichess. Os 8 lances jogados
contra a API real, ~27s no total (~3,4s por lance: duas avaliações e uma escolha
de lance, em profundidade 16). Nenhum campo de avaliação vazou nas 7 respostas
intermediárias — verificado por asserção no roteiro, não por leitura. Veredito
`BOM` com **−2,37%** de queda líquida contra os **84,7%** que o mesmo trecho
custou na partida; SM-2 reagendou para o dia seguinte com `ultima_qualidade = 5`
e `progresso_trecho` de volta a `null`. Confirmado também que `/responder` num
card de erosão devolve 400 apontando para `/trecho` e vice-versa, e que o motor
compartilhado continuou em força total depois do drill.

**Testes:** 37 na aritmética do trecho, 13 no passo contra o motor (com Stockfish
falso), 17 nos endpoints e na fila, 6 no componente — 861 backend, 268 frontend.

---

### D-67 — Consulta ao vivo: ajuda para pensar durante uma partida em andamento

**Data:** 17/09/2026

**Contexto.** Tudo que o produto faz até aqui olha a partida **depois** que ela
acabou: detecta o erro, diagnostica, agenda o treino. O que nunca chega ao
sistema é o momento da dúvida em si — "não tenho plano", "não sei se abro o
centro" — e o que o jogador estava pensando quando travou. O dono do projeto
pediu uma tela para espelhar, lance a lance, uma partida que ele joga contra um
bot no Lichess ou no Chess.com, e pedir análise quando travar, com ou sem um
texto explicando o raciocínio.

**Decisão: a consulta ensina a pensar antes de dar o lance.** A resposta vem em
três camadas, abertas em ordem na tela:

1. **Pensar** — leitura da posição, comentário sobre o raciocínio do jogador,
   perguntas para se fazer e planos descritos em palavras. **Nenhum lance.**
2. **Ideias** — os candidatos do Stockfish, cada um com a ideia por trás, em
   **ordem alfabética**: a ordem do motor revelaria qual é o melhor.
3. **Motor** — melhor lance, avaliação e linhas, só com clique explícito.

Um oráculo que devolve o lance resolve a partida e não ensina nada; o que se quer
treinar é decidir sozinho. A ocultação é pedagógica, feita na tela: as três
camadas chegam juntas numa única resposta, porque uma chamada ao Gemini por
camada triplicaria o custo e a espera de quem está com o relógio correndo.

**Exclusiva do dono, fechada por padrão.** A feature é de um usuário só por
decisão dele. Numa ferramenta que devolve análise de motor para uma posição de
partida em andamento, abrir para todos seria entregar ajuda externa em partida
contra humanos, que Lichess e Chess.com proíbem. A liberação é uma lista de ids
em `CONSULTA_AO_VIVO_USUARIOS` (Variable do repositório, levada ao Cloud Run
pelo deploy); **ausente ou vazia, ninguém acessa** — esquecer de configurar não
pode abrir a feature. Para os demais a rota responde **404**, e essa checagem
vem antes do limite diário na assinatura, para uma chamada barrada não consumir
cota. O espelhamento é manual e o módulo não fala com a API de nenhum site.

**O servidor recebe lances, não a posição.** Reconstruir a partida dá o número
do lance, recusa a consulta quando a vez é do adversário ("espelhe o lance dele
primeiro") ou a partida acabou, e guarda `lances_san` inteiro — que é o que vai
permitir casar a consulta com a partida real quando a coleta a trouxer (F5.3).

**Três freios de gasto e de uso.** Um teto por partida (`CONSULTA_MAX_POR_PARTIDA`,
3), que obriga a escolher os momentos de dúvida de verdade — consultar a cada
lance seria jogar com o motor do lado; um limite diário (15); e no máximo uma
correção por consulta quando o modelo viola as regras, caindo depois num
fallback determinístico que só afirma o que o tabuleiro prova.

**A regra "sem lance na camada 1" é verificada, não só pedida.** O prompt
proíbe, e a resposta passa por `detectar_lances_inventados` (herdado do
Explicador) com conjunto de permitidos **vazio** — qualquer lance ali é
violação, mesmo legal. O detector herdado só conhecia notação inglesa, e em
português "Cf3" passaria direto; ganhou um padrão para C/B/T/D/R.

**Tabuleiro próprio, com `chess.js`.** O produto só tinha o `tabuleiro-preview`,
estático. O `tabuleiro-interativo` reaproveita o mesmo visual e joga por clique
(peça, depois casa, com escolha de promoção); a legalidade vem do `chess.js`
(BSD-2). A `chessground`, do próprio Lichess, foi descartada por ser GPL-3 —
incompatível com o plano de cobrar pelo produto. O lance também pode ser
digitado em português ou inglês ("R" é tentado como Rei primeiro, a mesma ordem
do backend), e um PGN ou FEN colado alcança o site sem clicar lance por lance.

**Achado durante a verificação: o Explicador estava travado em produção desde
14/09.** A consulta reaproveita `analisar_posicao_com_engine`, e a primeira
chamada real ficou pendurada por mais de 3 minutos. A causa não era da feature:
a função repassava `searchtime=0` ao Stockfish, que nesse caso busca sem fim —
e o default de `STOCKFISH_SEARCHTIME_MS` virou 0 no commit `1c221c6`, de 14/09.
Toda chamada ao Explicador travava **segurando o `engine_lock`**, levando junto
Treino, trecho e Laboratório. A última explicação gravada é de 11/09.
`evaluate_position` sempre teve a guarda; aqui ela faltava, e o dublê de teste
aceitava qualquer `searchtime`. Corrigido num commit separado (`1e47cbf`), com
um teste cujo dublê falha com zero. Depois da correção: 0,6 s com o motor real.

**Verificado com a conta do dono, servidor local, uma chamada ao Gemini.**
Partida italiana até o lance 11, raciocínio preenchido. Resposta em 11,2 s,
gerada pelo modelo; a camada 1 veio sem nenhum lance, comentou o receio do
jogador de abrir o centro e propôs três planos em palavras; as ideias vieram em
ordem alfabética (a4, Bc2, Nf1) e o motor apontou Nf1. Confirmados também: 401
sem sessão, 400 na vez do adversário e em lance ilegal, 429 ao passar do teto da
partida, e a listagem da partida. A tela foi fotografada em desktop e celular,
jogando por clique de verdade; as fotos mostraram três defeitos de layout,
corrigidos antes do commit — o tabuleiro grudado no campo de lance, o botão de
consulta no fim da página do celular (onde menos serve durante uma partida) e
um buraco no desktop.

**Testes:** 28 no módulo da consulta, 10 nos endpoints, 2 na correção do
Explicador, 35 no frontend (tabuleiro, tela, regras de notação e armazenamento,
serviço e guard) — 901 backend, 303 frontend.

**Próximas fases:** F5.3 casa cada consulta com a partida coletada ("o que você
jogou depois?") e transforma a dúvida em sinal do Hexágono e em card da fila;
F5.4 sincroniza pelo link do Lichess, só contra bot; F5.5 cobre o Chess.com.

### D-68 — A consulta ao vivo ganha desfecho: o que foi jogado depois da dúvida

**Data:** 17/09/2026

**Contexto.** O D-67 registra a dúvida no momento em que ela acontece, mas o
sistema nunca ficava sabendo o que aconteceu com ela. A consulta era um fim em
si: nem o jogador via se seguiu a ajuda, nem o treino aproveitava que aquela
posição foi declaradamente difícil.

**Decisão.** `casar_consultas_ao_vivo.py` roda no pipeline diário, depois da
coleta, do Stockfish, do Agente 1 e da fila, e procura na partida coletada a
posição de cada consulta pendente. Achando, grava o lance jogado depois, se ele
era uma das ideias candidatas, se era o lance do motor e quanto custou — medido
pelo mesmo `win_percent_na_posicao` do trecho (D-66), que já trata posição
terminal sem perguntar ao motor.

**Como acha a partida.** Com `partida_externa_id` (consulta sincronizada, D-69),
direto por `partidas.external_id`. Sem ele, pelas partidas do dono, mesma cor e
mesma plataforma numa janela larga de horário — e, entre elas, a que de fato
passou pela posição. **A posição decide, a janela só evita varrer o acervo**:
`data_partida` é o início no Lichess e pode ser o fim no Chess.com, então a
janela é generosa (24 h antes, 6 h depois). A comparação de posição usa peças,
vez e roques, ignorando en passant e contadores; numa repetição, vale a
ocorrência com o mesmo número de lance da consulta.

**Três estados, e desistir é um deles.** `pendente` (normal no mesmo dia),
`casada` ou `sem_partida` — depois de 3 dias sem achar, a partida não virá
(outro site, tabuleiro físico, variante não coletada). Parar de procurar é o
certo: insistir para sempre gastaria uma consulta ao banco por dia por nada.

**A dúvida vira prioridade no treino.** Se a posição consultada é um lance
crítico da partida (PICO naquele lance, ou uma EROSAO cuja janela o cobre), a
consulta guarda o vínculo, e o card desse lance, **se nunca foi respondido**, é
trazido para hoje. É o card mais valioso da fila: a dúvida foi declarada e o
erro aconteceu mesmo assim. Card que o SM-2 já agendou pelo desempenho do
jogador não é atropelado.

**O que ficou de fora, e por quê:** um sinal de "dúvida" no Hexágono. O plano
original incluía, mas não existe hoje uma consulta real sequer — só as de
verificação, já apagadas. Desenhar uma métrica agregada sobre zero pontos seria
inventar o formato antes de ver o dado. Volta à mesa quando houver algumas
dezenas de dúvidas casadas.

**Verificado com dado real, e desfeito depois.** Uma consulta de verificação
sobre a posição de um erro crítico real do dono (lance 25, `Qb6`, queda de
24,14% registrada pelo pipeline), rodando o script contra produção: casou com a
partida certa, `lance_jogado = Qb6`, `era_candidato = true` (estava na camada de
ideias da consulta de teste), `era_o_melhor = false`, vínculo com o lance
crítico, e o card 514 foi trazido de 05/11 para hoje. A queda medida foi 27,8%
contra os 24,14% do pipeline: o mesmo motor na mesma profundidade não é
determinístico entre execuções, e a diferença é desse tamanho. A data do card
foi restaurada e as duas consultas de verificação (esta e a do D-67) apagadas.

**Na tela.** Cada consulta mostra o desfecho quando existe, e uma seção "Suas
dúvidas anteriores" lista as das outras partidas — é onde o casamento fica
visível, já que a coleta só traz a partida depois de ela acabar.

**Testes:** 20 no script, 2 nos endpoints, 3 no componente.

---

### D-69 — Sincronizar a consulta ao vivo com a partida em andamento, contra qualquer adversário

**Data:** 17/09/2026

**Contexto.** O D-67 exigia espelhar cada lance à mão. O plano propunha
sincronizar pelo link só contra bot; o dono decidiu **sincronizar todas as
partidas**, porque também joga com amigos, alunos e professores. A feature
continua exclusiva dele (D-67).

**O que as plataformas permitem, verificado na documentação e na API:**

- **Lichess.** Os endpoints públicos de partida em andamento
  (`/game/export/{id}`, `/api/stream/game/{id}`, `/api/user/{u}/current-game`)
  são, nas palavras da documentação, *"delayed by 3 moves, as to prevent cheat
  bots from using this API"*. A posição atual sem atraso só vem de
  `/api/account/playing`, que lista as partidas **do dono do token** — FEN e
  último lance, sem histórico. Funciona com o escopo `puzzle:read` que o OAuth
  do D-33 já tem (testado: 200). `fullId`, que identifica o jogador dentro da
  partida e serve para jogar por ele, nunca é lido.
- **Chess.com.** A API pública só lista partidas **diárias** em andamento, com
  PGN completo e FEN. Partidas ao vivo em andamento não aparecem em endpoint
  público nenhum; nelas o espelho continua manual, ou colando o PGN. A tela diz
  isso em vez de listar vazio sem explicação.

**Posição exata, histórico reconstruído.** Do Lichess vêm a posição atual (sem
atraso) e o histórico atrasado. Os lances que faltam entre os dois são
reconstruídos por busca (`completar_lances`). A primeira versão, ingênua,
estourou 280 s com partidas reais: 6 meios-lances são dezenas de milhões de nós.
Três podas tornaram viável — só se mexe peça que está numa casa diferente da
posição final; a paridade da vez elimina metade das profundidades; e o número de
casas diferentes limita o que ainda cabe —, mais comparação por bitboard e SAN
gerado só no fim. Medido em 198 cortes de 12 partidas reais:

| Meios-lances faltando | Reconstruídos | Pior tempo |
|---|---|---|
| 1–2 | 66/66 | < 0,01 s |
| 3 | 31/33 | 0,06 s |
| 4–6 | 85/99 | 4,98 s |

Nenhum resultado errado: os que não são idênticos ao que aconteceu são
transposições que chegam à mesma posição. Um teto de 60 mil nós garante que a
busca nunca prende a requisição; passar dele devolve `historico_completo=false`,
e a consulta usa a posição exata sem a lista de lances.

**Os segundos só na primeira vez.** O servidor guarda o último estado completo
de cada partida. Nas atualizações seguintes (a tela pede a cada 4 s), faltam um
ou dois meios-lances **a partir dele**, não do export atrasado — reconstrução
instantânea, sem nem pedir o export. Um cache de 3 s evita ir à plataforma a
cada pedido; o Lichess pede uma requisição por vez e um minuto de espera ao
receber 429, e a tela respeita isso.

**A consulta de partida sincronizada não confia no cliente.** Com
`sincronizada`, o servidor busca lances, cor e adversário na plataforma — sem o
cache, porque a consulta tem que ser sobre a posição de agora — e ignora o que
o cliente mandou. A partida espelhada ganha um id **determinístico** (uuid5 da
partida real): recarregar a tela ou trocar de aparelho cai na mesma partida, e o
teto de consultas por partida não zera. A consulta grava `partida_externa_id`,
que é o que faz o D-68 casar direto, sem janela de horário.

**Credenciais só do próprio dono.** O token OAuth do Lichess dele, nunca o
`LICHESS_TOKEN` do ambiente — que seria a conta de outra pessoa e listaria as
partidas dela. Há teste para isso.

**Sobre adversários humanos.** A decisão de sincronizar todas as partidas é do
dono, e o sistema não tenta adivinhar se o adversário sabe da consulta. Fica
registrado o fato relevante: as regras do Lichess e do Chess.com proíbem ajuda
externa em partida contra outra pessoa, e a detecção das plataformas não sabe
de combinados entre os jogadores. A sincronização não altera o que a consulta
entrega (as três camadas continuam as mesmas) nem contorna nenhuma detecção —
usa o endpoint oficial das próprias partidas do dono.

**Na tela.** "Sincronizar com uma partida em andamento" lista as partidas das
duas plataformas (com os avisos do que não deu para listar). Sincronizada, a
tela mostra plataforma, adversário, ritmo e se é ranqueada, o tabuleiro só
acompanha, e o espelho à mão (tabuleiro clicável, campo de lance, desfazer, PGN)
some para não divergir da partida real. "Parar" volta ao espelho à mão na
posição em que estava. Quando a partida termina, a tela para de atualizar e
explica que o desfecho aparece depois da coleta.

**O que não foi verificado de ponta a ponta:** a sincronização com uma partida
real **sua** em andamento. Nenhuma das duas contas tinha partida em curso
durante o trabalho; o que foi verificado de verdade foi a listagem real (vazia)
nas duas plataformas, o parsing de partidas diárias reais de um jogador público
do Chess.com (os lances reproduzem a FEN), o export real de uma partida ao vivo
do Lichess e a reconstrução com partidas reais. A primeira partida jogada com a
tela aberta é o teste que falta.

**Testes:** 22 no módulo de plataformas, 10 nos endpoints, 8 no componente —
955 backend, 314 frontend.

### D-70 — A consulta ao vivo ensina a avaliar a posição, e não entrega lance

**Pedido do dono:** durante uma partida espelhada, ajuda para saber *como
avaliar* a posição e *por que* pensar daquele jeito — não quais são os melhores
lances.

**O que mudou.** As camadas 2 (ideias candidatas) e 3 (lance do motor) do D-67
saíram. A resposta passou a ter um único bloco, `como_pensar`:

- `tipo_de_posicao` — tática ou calma, aberta ou fechada, quem tem a
  iniciativa, e o que isso exige do raciocínio agora;
- `sobre_o_seu_raciocinio` — comenta o *processo* do jogador (o que avaliou,
  o que deixou de fora, em que ordem deveria ter olhado); se ele listou lances,
  não diz qual é bom;
- `roteiro` — 3 a 5 passos na ordem em que avaliar, cada um com `o_que_avaliar`
  e `por_que` (por que isso importa NESTA posição e nesta ordem);
- `principio` — a regra de pensamento que vale em outras partidas.

Planos e perguntas-guia também saíram: um plano descrito em palavras já é meia
resposta, e o roteiro cobre as perguntas com o porquê junto.

**Esconder, não só não mostrar.** No D-67 a ocultação era da tela; as camadas
chegavam inteiras ao navegador. Agora o servidor não devolve nada do motor: o
que o Stockfish diz vai para `resposta.motor` no banco (o desfecho do D-68
compara o lance jogado com os candidatos) e o modelo de resposta da API não tem
campo para isso. Nem a aba de rede mostra o lance.

**O Stockfish continua rodando**, por dois motivos: o desfecho precisa dele, e o
Gemini erra a leitura sem ele — é a análise que diz se a posição é tática (o
roteiro começa por ameaças e lances forçantes) ou calma (começa por peças e
estrutura). As linhas vão no prompt marcadas como segredo, só para esse fim.

**Verificado, não só pedido.** Além da notação inglesa e portuguesa, a resposta
agora é rejeitada se *descrever* um lance em palavras ("leve o cavalo para f5",
"avance o peão até h5"): verbo de movimento no imperativo ou infinitivo seguido
de uma casa. O padrão só pega formas de comando, para "o jogador olha para f7"
não ser falso positivo. Roteiro com menos de 3 passos ou princípio vazio também
contam como problema. O limite é honesto: uma dica disfarçada sem casa ("pense
em trocar as damas") não é detectável por padrão; o prompt a proíbe
explicitamente, e é o que resta.

**Fallback determinístico** também virou roteiro: o que o último lance do
adversário mudou → peças soltas suas → lances forçantes (quando há alvos) →
segurança dos reis → a pior peça, com o porquê de cada um, e um princípio
diferente para posição tática e calma. Nunca repassa a lista de xeques e
capturas do inspetor, que é feita de lances.

**O desfecho do D-68 continua comparando com o motor** ("era o lance do motor",
"estava entre os lances que o motor considerava"). Isso aparece só em "Suas
dúvidas anteriores", depois de a partida ser coletada — quando já não tira
decisão de ninguém.

**Sem migração:** a tabela estava vazia quando o formato mudou (conferido antes).

**Verificação real:** API local, Gemini de verdade, duas posições — a italiana
fechada do D-67 com o pensamento preenchido e uma posição de lance crítico real
do dono (pretas, lance 27). As duas vieram do Gemini na primeira tentativa, em
10–11 s, com 4 passos cada, nenhum lance no texto e nenhum campo do motor na
resposta HTTP; o `motor` foi gravado no banco. Telas fotografadas em desktop e
celular sem erro de console. As duas consultas de teste foram apagadas depois.

**Testes:** 31 no módulo (eram 28), API e componente adaptados — 958 backend,
314 frontend.

### D-71 — Navegação lateral, tema claro/escuro e o Hexágono em quatro páginas

**Pedido do dono:** o app parecia "blog, página corrida, muita informação numa
página só". Ele pediu navegação lateral, fundo mais claro, escolha entre claro
e escuro, e validar em telas pequenas.

**O diagnóstico por trás do "jeito de blog".** Não era só a barra de menu no
topo. A página inicial tinha **cerca de 7.900 px de altura no desktop**:
ressalva de cadência, narrativa, perguntas pendentes, radar, treino focado,
repertório de aberturas, puzzles e sessões de treino, tudo numa rolagem. E
todas as telas abriam com um título de até 3.25rem e parágrafos de subtítulo,
como capa de revista. Perguntado, o dono escolheu quebrar a página em
subpáginas (em vez de abas ou de só trocar o menu) e fazer o tema seguir o
aparelho por padrão.

**Navegação em três grupos**, pelo que a pessoa vai fazer:
- **Diagnóstico:** Visão geral, Aberturas, Puzzles, Plano de treino;
- **Praticar:** Treino diário, Laboratório;
- **Ferramentas:** Explicador, Analisador, Ao vivo (este só para quem o
  servidor libera, D-67).

Tema, Perfil, Sair e o e-mail ficam no rodapé da lateral. A partir de 1024px
a lateral é fixa. Abaixo, uma barra no topo com botão de menu abre a mesma
lateral como gaveta: é um único `<aside>`, porque duas cópias da lista
acabariam divergindo. A gaveta leva o foco para dentro e o devolve ao botão,
fecha no Esc, no véu e ao navegar, e trava a rolagem da página por trás. Fora
da tela ela fica com `visibility: hidden`, senão o teclado alcançaria os links
escondidos. `/sessao/:id` acende "Plano de treino".

**Subpáginas sem reescrever nada.** Repertório, puzzles e sessões de treino já
eram componentes que buscam os próprios dados; ganharam as rotas `/aberturas`,
`/puzzles` e `/plano` numa página fina (`diagnostico-secao`) que só põe o
título. O subtítulo da página foi tirado depois da primeira captura: o cartão
de cada bloco já traz a descrição, e a tela a repetia duas vezes seguidas. Os
links que apontavam para as sessões na raiz ("sessões de treino do Hexágono",
"Voltar ao Hexágono", "a sprint prescrita abaixo") agora levam a `/plano`.

**Tema como papéis, não como cores.** `styles.css` já era a única fonte de
cor, e os templates usavam os tokens de forma consistente, então o tema claro
é um bloco `:root[data-tema="claro"]` que redefine os mesmos papéis
(`ardosia-900` = fundo da página, `marfim` = texto de maior ênfase). Não houve
renomeação espalhada pelos 18 componentes. As exceções foram tratadas
explicitamente:
- `ardosia-950` continua escuro nos dois temas (é o preto das peças pretas e
  o véu de modal);
- entraram `tinta` e `giz`, textos que não mudam com o tema, sobre a casa
  clara e sobre esse preto;
- entrou `sobre-latao`: escuro no tema escuro, branco no claro.

O latão escurece no claro (`#dea34c` sobre branco dá 2,2:1; `#9a661c` passa de
4,5:1). No claro, o botão primário desabilitado deixa de ser latão a 50% e
vira um controle cinza, porque texto branco sobre latão lavado ficava
ilegível.

**Sem lampejo.** Um script inline no `index.html` aplica `data-tema` antes da
primeira pintura, com a mesma chave e regra do `TemaService`; sem ele, quem
usa o claro via o escuro piscar a cada recarga. O radar do Chart.js lê as
cores dos tokens na criação e por isso é recriado quando o tema muda.

**Densidade.** Título de página entre 1.5rem e 2rem (era até 3.25rem),
subtítulo menor e mais apagado, menos espaço entre cartões, e o subtítulo
longo do Treino Diário encurtado para duas linhas.

**Bugs achados no caminho:**
- **A gaveta fechava ao abrir:** o efeito que fecha a gaveta ao navegar lia
  `menuAberto()` e passava a depender dele. O teste pegou antes de chegar à
  tela; resolvido com `untracked`.
- **Botão fora do cartão:** no histórico de análises, título longo não
  truncava (faltava `min-w-0`) e empurrava o botão para fora. A coluna mais
  estreita da nova casca é que expôs isso.

**Verificação real:** API e frontend locais com a sessão do dono. Foram
capturadas 31 telas no claro e 31 no escuro, em 1440, 820 e 390px. Olhei uma
amostra de cada largura e tema (Visão geral, Aberturas, Plano, Treino,
Explicador, Analisador, Ao vivo, login), e as duas correções abaixo foram
fotografadas de novo depois de feitas. A gaveta foi
exercitada no navegador em 390 e 320px nos dois temas: foco entrando e
voltando, rolagem travada e destravada, fechar no Esc e ao navegar, e nenhuma
rolagem horizontal. Nenhum erro de console da aplicação; dois 500 passageiros
da API local em rotas que esta mudança não toca, que responderam 200 nas
outras chamadas.

**Fica para depois:**
- **A Visão geral ainda é longa:** a narrativa do Agente 2 sozinha passa de
  meia tela.
- **Markdown cru na narrativa:** `*calculo_tatico_deficiente*` aparece com os
  asteriscos. É anterior a esta mudança, mas continua visível.

**Testes:** `TemaService` (4), casca (grupos, item ativo, gaveta, seletor de
tema) e `diagnostico-secao` — 322 frontend.

---

### D-72 — Quarto livro no RAG ("How to Calculate Chess Tactics") e um bug real de chunking corrigido

**Pedido do dono:** fazer mais OCR de livros para enriquecer o que der.

**Levantamento antes de gastar Gemini.** `backend/rag/livros_pdf/` tinha 2 PDFs
ainda não processados. Antes de rodar o pipeline caro (OCR + embedding +
sugestão de conceitos), rodei `--preview` nos dois — modo que só faz o chunking
local, sem custo:

- **"How to Calculate Chess Tactics" (Valeri Beim, 178 páginas):** já tinha OCR
  em cache de uma sessão anterior (14–15/09). Prosa real, boa candidata.
- **"5334 Táticas de Xadrez" (1184 páginas):** ao inspecionar o texto nativo
  extraído (`pdfplumber`), ele não é prosa nem OCR malformado — é a saída
  literal de uma **fonte de diagrama** (glifos tipo `0Z0ZrZ0Z` que renderizam
  peças/casas, usados por softwares de diagramação para desenhar o tabuleiro
  como texto). O livro (**5334 Problems, Combinations & Games**, de László
  Polgár) é praticamente só diagramas de posição, sem texto explicativo.
  **Decisão: não processar.** Chunk nenhum desse livro teria conteúdo
  conceitual — só poluiria `livros_chunks` e apareceria como citação vazia
  ("Fonte: pág. 55") nas prescrições do Agente 3. O que esse livro daria de
  útil (posições táticas soltas) já vem, de forma estruturada e com FEN de
  verdade, do dump de puzzles do Lichess (D-49, tabela `exercicios_taticos`) —
  não precisa de OCR nenhum.

**Bug real achado no chunking, não hipotético.** O preview de "How to
Calculate Chess Tactics" (idioma certo, `--ocr-lang eng`) chunkeou em **41
"capítulos"**, a maioria lixo tipo `PART 1: TACTICS IN CHESS 19` — o cabeçalho
de página do livro, que muda de texto a cada página (o número no fim), então
`remove_repeated_headers` (que só apara repetição *exata*) nunca via os
cabeçalhos como iguais. A causa era um bug em `detect_chapter`: o guard que
deveria rejeitar título terminado em dígito solto comparava a linha inteira
contra uma regex que SEMPRE casava (`\d+\s*$` bate em qualquer string
terminada em dígito) — código morto que nunca rejeitava nada. Corrigido para
checar só o **sufixo** depois do número do capítulo (grupo nomeado no regex):
um título real termina no próprio número/romano ("PART 3", sem sufixo) ou em
palavra ("PART 3 - Calculation Trees"); só um cabeçalho de página termina o
sufixo em outro dígito solto. Com a correção, o mesmo livro caiu para **9
capítulos reais** (mais 1 sem capítulo). 2 testes novos em
`test_processar_livro.py`, os 11 existentes continuam passando — nenhum dos
casos já cobertos (português, inglês, numerado) termina em dígito, então o
fix não muda o comportamento deles. Conferi rodando o preview dos 3 livros já
importados: `How to Reassess Your Chess` deu exatamente os mesmos 251 chunks
de antes — o bug não afetava livros sem esse padrão de cabeçalho.

**Pipeline real executado**, na mesma sequência manual dos 3 livros
anteriores: `processar_livro.py` (OCR do cache + chunking + embedding) → 179
chunks em `livros_chunks` → `sugerir_indice_conceitual.py` (Gemini, 1 chamada
por capítulo, 9 capítulos) → 27 conceitos revisados à mão no JSON antes de
importar → `importar_indice_conceitual.py` → `indice_conceitual`. 3 títulos de
capítulo com resíduo de OCR que a limpeza automática de borda não cobre
(`PART 1: TACTICS IN CHESS Il`, `PART I: TACTICS IN CHESS 4]`,
`EXERCISES FOR PART |`) foram corrigidos à mão nas duas tabelas — mesmo
precedente já documentado no código para os livros anteriores.

**Achado colateral, não corrigido agora:** o casamento de `buscar_conceitos`
(usado por `resolver_citacao` nas prescrições do Agente 3) é `ILIKE` literal
contra `CATEGORY_SEARCH_TERMS`, que usa português acentuado ("segurança do
rei"). Boa parte dos conceitos que o Gemini sugere — dos 3 livros antigos e
deste novo — vêm em formato de tag sem acento (`seguranca_do_rei`,
`avaliacao_posicional_incorreta`), que não bate com o termo de busca
acentuado. Ou seja: esses conceitos aparecem em `indice_conceitual` (existem,
contam nas estatísticas) mas uma fatia deles nunca é *encontrada* pela busca
de citação — só o RAG vetorial (`match_livros_chunks`, usado direto pelo
Agente 3 pra montar os módulos de sprint) não sofre disso, porque compara
embedding, não string. Pré-existente, não introduzido aqui; mexer nisso é
trabalho à parte (normalizar `CATEGORY_SEARCH_TERMS` ou usar `unaccent()` no
Postgres).

**Cobertura por categoria não mudou onde mais precisava.** Contagem de
`indice_conceitual` batida contra `CATEGORY_SEARCH_TERMS` antes/depois:
TATICA 8, ESTRATEGIA 9, FINAIS 12→14, ESTRUTURA_DE_PEOES 4 (inalterada),
GESTAO_DE_TEMPO 10→11, CALCULO 10→11. `ESTRUTURA_DE_PEOES` continua sendo o
gargalo — tem cobertura cheia no catálogo tático do Lichess (300 exercícios,
D-49) mas quase nada de citação de livro. Um livro específico de estrutura de
peões (ex.: "Pawn Structure Chess", Soltis) seria o próximo alvo mais
valioso, mas precisa vir de fora — não posso obter PDF de livro protegido por
mim mesmo; depende do dono colocar o arquivo em `backend/rag/livros_pdf/`.

**Verificação real:** rodei os 3 scripts contra o Supabase de produção de
verdade (não é dry-run) — 179 linhas em `livros_chunks`, 27 em
`indice_conceitual`, contagem final conferida por query. `pytest`/`unittest`
completo do módulo depois do fix: 13/13. Processos órfãos do Windows (2
tentativas iniciais com idioma OCR errado, que rodaram em paralelo por engano)
identificados via `Get-CimInstance Win32_Process` e encerrados antes de
qualquer cache ser gravado com o idioma errado — conferido que nenhum arquivo
de cache espúrio ficou em `.ocr_cache/`.

**Testes:** 13 em `test_processar_livro.py` (eram 11).

---

### D-73 — Biblioteca pessoal do usuário no Google Drive como fonte de livros; dois materiais curtos de estrutura de peões processados

**Contexto:** seguindo o D-72 ("quero fazer mais OCR's de livros"), o usuário
apontou uma pasta pessoal no Google Drive com mais de 110 PDFs de xadrez.
Acessei via o conector do Google Drive (`search_files`/`read_file_content`/
`download_file_content`) — a pasta pertence ao próprio usuário
(`edson.hirano28@gmail.com`), sem risco de acessar dado de terceiro.

**Achado de escala:** a pasta é grande demais para processar sem curadoria —
tem muita duplicata do que já está no RAG (o próprio "How to Calculate Chess
Tactics", "How to Reassess Your Chess", "Meu Sistema", "Xadrez Vitorioso -
Táticas", e o "5334 Problems" do Polgár já descartado no D-72), várias cópias
repetidas do mesmo título, e material de peso bem desigual (biografia agrega
pouco ao RAG de prescrição tática/estratégica). Perguntei ao usuário como
priorizar em vez de processar tudo de uma vez — ele escolheu começar pelos
candidatos a atacar o gargalo de `ESTRUTURA_DE_PEOES` (apontado no D-72).

**Os 4 candidatos de estrutura de peões, o que cada um realmente era:**
1. `feismo.com-pawn-structure-pr_...pdf` — não é o livro do Soltis, é o verbete
   da Wikipédia em inglês "Pawn structure" (a lista de 17 formações do
   Soltis é só citada, não reproduzida). Sem paginação real de livro, não
   serve ao formato de citação do projeto — descartado.
2. "Estrutura e Desenvolvimento dos Peões" (FM Bolívar Gonzalez, aula IV do
   curso FEXPAR) — prosa real, 13 páginas, com partidas citadas de verdade
   (ex. Portisch–Fischer, Sousse 1967). Processado.
3. "Estrutura de Peões" (Mestre FIDE Frederico Gazel, @xadrezescolar) —
   slides bem curtos, 7 conceitos em frases soltas (isolado, passado,
   dobrado, atrasado, ligados, colgantes, ilha de peões). Processado mesmo
   sendo raso, porque nomeia certinho o vocabulário da categoria.
4. "PEÕES NA SÉTIMA.pdf" — 146 páginas, 100% imagem (sem camada de texto,
   confirmado via leitura direta do PDF), 32MB. Não deu pra baixar pelo
   conector do Drive (limite de 10MB da ferramenta) — fica pendente até o
   usuário colocar o arquivo manualmente em `backend/rag/livros_pdf/`.

**Achado que limita o resultado:** os dois materiais processados (#2 e #3)
não têm título de capítulo que bata no `detect_chapter()` — são textos
corridos de aula/slide, não livros com "Capítulo N". Resultado:
`sugerir_indice_conceitual.py` rodou e devolveu **zero sugestões nos dois**
(`Capítulos elegíveis: 0` ou `1 pulado por amostra curta`), então nenhuma
linha nova entrou em `indice_conceitual` — o gargalo de citação de livro em
`ESTRUTURA_DE_PEOES` continua aberto. Os 7 chunks entraram normalmente em
`livros_chunks` e reforçam a busca vetorial (RAG), que independe de
capítulo. Decidi não forçar entrada manual de conceito nesses dois: o
schema de `indice_conceitual` existe para dado citável com página real, e
"página 8 de um slide" não é uma citação útil pro usuário final. O próximo
alvo real para fechar esse gargalo continua sendo um livro de verdade sobre
estrutura de peões, com capítulos — candidato mais forte agora é o próprio
"PEÕES NA SÉTIMA.pdf" pendente (#4 acima), depois de baixado.

**Verificação real:** `--preview` rodado nos 2 arquivos antes de gastar
qualquer coisa (0 custo, só extração local) — 6 chunks e 1 chunk
respectivamente. Depois, processamento completo de verdade contra o
Supabase de produção (`pmzmershonrqzwbmhaco`): `livros_chunks` confirmado
em 807 (era 800) por query direta. `sugerir_indice_conceitual.py` rodado
para os dois, confirmando 0 sugestões em ambos antes de decidir não
processar `indice_conceitual` para eles.

---

### D-74 — Google Drive Desktop resolve o limite de 10MB; "Segredos da Moderna Estratégia" processado e um bug de citação por TOC corrigido na revisão manual

**Contexto:** continuação do D-73. O conector MCP do Google Drive só baixa
arquivo de até 10MB, o que bloqueava a maior parte da biblioteca (a maioria
dos livros bons passa disso, incluindo o candidato mais forte de estrutura
de peões). O usuário instalou o Google Drive para Windows (Google Drive
Desktop) e montou a pasta como unidade local (`G:\Meu Drive\...`) — a partir
daí, qualquer arquivo passou a ser acessível via sistema de arquivos comum
(`Copy-Item`/PowerShell), sem limite de tamanho.

**Priorização por dado real, não achismo:** antes de escolher o próximo
livro, rodei a mesma query de `buscar_conceitos` (por categoria do
Hexágono) direto no Supabase de produção, contando quantos conceitos
citáveis cada categoria já tem: TATICA 8, ESTRATEGIA 9, FINAIS 14,
ESTRUTURA_DE_PEOES 4, GESTAO_DE_TEMPO 11, CALCULO 11. Confirma o gargalo
apontado no D-72: ESTRUTURA_DE_PEOES continua de longe o mais fraco.

**Achado que muda o plano — "PEÕES NA SÉTIMA" não é sobre peões:** o título
sugeria um livro de teoria de estrutura de peões, mas rodar o OCR completo
(146 páginas, grátis, só extração local) revelou que é uma coletânea de
memórias/história do xadrez brasileiro (capítulos como "BOBBY FISCHER — O
SPUTNIK DO XADREZ", "SINOPSE DA HISTÓRIA DO XADREZ NO BRASIL", perfis de
Petrosian, Tartakover, Rossolimo, Trompowsky). Verificado o restante da
biblioteca: não existe nenhum outro candidato real de teoria de estrutura
de peões nela. Consultado o usuário, que decidiu descartar esse livro (não
processar) e seguir para o próximo gargalo mais forte disponível.

**Livro escolhido:** "Segredos da Moderna Estratégia" (John Watson, tradução
PT-BR), 540 páginas, texto nativo (sem necessidade de OCR), 380 chunks.
Escolhido entre 4 candidatos com texto nativo confirmado (também
disponíveis: "Arte do Ataque no Xadrez" de Vukovic, "Positional Decision
Making in Chess" de Gelfand, "The Complete Manual of Positional Chess" de
Sakaev/Landa) por já ter capítulos numerados reais no sumário.

**Um bug real de citação, achado na revisão manual antes do import:** o
`detect_chapter()` capturou como "capítulo" uma linha do **sumário** do
livro (`CAPÍTULO 7: BISPOS VERSUS CAVALOS 2: PARES DE PEÇAS`, que aparece
listada no sumário nas primeiras páginas) e atribuiu a ela os 33 chunks
seguintes (páginas 10–42) — que na verdade são a dedicatória, a introdução
e o conteúdo real do Capítulo 1 (clássico vs. hipermoderno, centro e
tempos), **nada relacionado a bispos e cavalos**. Uma citação assim seria
ativamente enganosa. Comparando a extração real de texto (via `pdfplumber`,
sem custo) contra cada um dos 23 "capítulos" que `sugerir_indice_conceitual.py`
gerou, encontrei mais 3 casos análogos (páginas de ficha catalográfica, e
dois títulos cujo intervalo de página na verdade pertencia à seção
seguinte) — todos os 4 tiveram o `capitulo` zerado (`NULL`) em
`livros_chunks` e as sugestões correspondentes removidas do JSON antes do
import, em vez de inventar um título "corrigido" sem prova. Outros 9
títulos estavam apenas truncados por quebra de linha (ex.: `"A MASSA DE
PEÕES"` → `"A Massa de Peões Móveis Centrais"`, confirmado lendo a página
real) e foram corrigidos com o texto verificado, nunca com título inventado
— quando a continuação truncada não pôde ser confirmada no texto extraído,
o fragmento ficou como estava (ex.: `"Do Flanco Para o"`), em vez de eu
completar a frase por conta própria. Isso não é o mesmo bug do D-72 (aquele
era sobre cabeçalho de página repetido); esse é sobre o sumário do livro
sendo confundido com o início real de um capítulo — mecanismo diferente,
mesma categoria de risco (R2 do `AGENTS.md`). Não alterei `detect_chapter()`
desta vez — é uma particularidade de layout deste livro (sumário detalhado
com títulos de capítulo completos), não um padrão genérico como o do D-72.

**Achado que fica para depois, quantificado agora:** ao conferir a
contagem por categoria depois do import, ESTRATEGIA subiu 9→11,
GESTAO_DE_TEMPO 11→13, CALCULO 11→14 — mas os 58 conceitos novos deveriam
ter batido muito mais forte que isso (vários são literalmente sobre
fraqueza de peões, ex. `fraqueza_estrutural_de_peoes`, mas `ILIKE
'%estrutura de peões%'` não bate em texto sem acento e com underscore).
Confirma, com número concreto agora, o gap de acentuação/formatação entre
o que o Gemini sugere e o que `CATEGORY_SEARCH_TERMS` busca (apontado no
D-72, ainda não corrigido).

**Verificação real:** `--preview` gratuito primeiro (380 chunks, 23
capítulos). Processamento completo contra produção
(`pmzmershonrqzwbmhaco`): `livros_chunks` 807→1187 (confirmado por query).
`sugerir_indice_conceitual.py` gerou 70 sugestões brutas em 23 capítulos;
depois da revisão manual (4 capítulos descartados, 9 títulos corrigidos),
58 conceitos entraram em `indice_conceitual` (216→274, confirmado por
query). Contagem por categoria refeita depois do import para medir o
impacto real.

---

### D-75 — Corrigido o gap de acento/underscore em `buscar_conceitos()`, destravando conceitos já salvos

**Contexto:** apontado como achado pendente no D-72 e quantificado no D-74
— o Gemini frequentemente sugere conceitos em formato de tag, sem acento e
com underscore (`fraqueza_estrutural_de_peoes`, `seguranca_do_rei`),
enquanto `CATEGORY_SEARCH_TERMS` (`agente3_prescritor.py`) busca por termo
em português com acento e espaço (`estrutura de peões`, `segurança do
rei`) via `ILIKE`. Como `ILIKE` não normaliza acento, uma fração grande dos
conceitos já salvos em `indice_conceitual` nunca aparecia na busca de
citação (`buscar_conceitos()`, usada por `popular_fila_treino_espacado.py`
e pela prescrição do Agente 3) — o dado existia no banco mas era invisível
para esse caminho de código. Depois de processar o D-74 e ver o ganho real
ficar bem menor do que o esperado, o usuário pediu pra corrigir isso agora,
em vez de continuar só adicionando mais livros.

**Decisão:** normalizar os dois lados da comparação (o `conceito` salvo e
os termos de `CATEGORY_SEARCH_TERMS`) removendo acento
(`unicodedata.normalize("NFKD", ...)` + descartar caracteres combinantes) e
trocando `_` por espaço antes de comparar por substring, em vez de usar
`ILIKE` direto no Postgres. Optei por trazer as ~274 linhas de
`indice_conceitual` de uma vez (`select("*")`, sem filtro) e filtrar em
Python, ao invés de `N` chamadas `.ilike()` (uma por termo) como antes —
mais simples de testar (`unittest` puro, sem precisar simular o
comportamento de acento do Postgres num mock) e também mais barato em
round-trips de rede (1 chamada em vez de até 7). A tabela é um catálogo
compartilhado pequeno (não escala por usuário), então trazer tudo de uma
vez é seguro.

**Por que não resolvi durante o D-74:** decidiu-se separar em duas
decisões porque são mudanças de natureza diferente — D-74 foi ingestão de
dado (processar um livro), D-75 é uma mudança de comportamento de busca em
produção (afeta a prescrição de todo usuário, não só o livro novo).
Mudança de comportamento merece o próprio registro e a própria verificação
de regressão, sem depender de reler o histórico de um commit de dados.

**Resultado real, medido antes e depois do fix** (mesma query de
`buscar_conceitos()` por categoria, contra produção):

| Categoria | Antes | Depois |
|---|---|---|
| TATICA | 8 | 38 |
| ESTRATEGIA | 11 | 36 |
| CALCULO | 14 | 32 |
| GESTAO_DE_TEMPO | 13 | 13 (sem mudança) |
| FINAIS | 14 | 14 (sem mudança) |
| **ESTRUTURA_DE_PEOES** | **4** | **4 (sem mudança)** |

TATICA, ESTRATEGIA e CALCULO saltaram porque boa parte dos termos de
`CATEGORY_SEARCH_TERMS` dessas categorias (`segurança do rei`, `avaliação`,
`iniciativa`, `profilaxia`) já tinha correspondente direto nos conceitos
salvos, só que mascarado por acento/underscore. **ESTRUTURA_DE_PEOES
continua travado em 4 mesmo depois do fix** — achado honesto: não é (só)
um problema de acento. O conceito mais comum sugerido pelo Gemini para
peão fraco é `fraqueza_estrutural_de_peoes` (com a palavra "estrutural"),
enquanto o termo de busca da categoria é "estrutura de peões" (sem o
"-al"): são raízes de palavra diferentes, substring não bate mesmo sem
acento. Resolver isso é um problema de vocabulário/sinônimo, não de
formatação — e fica fora do escopo deste fix (mudar a lista de termos de
busca é uma decisão de produto sobre o que conta como "sobre estrutura de
peões", não uma correção técnica; não decidi isso sozinho).

**Verificação real:** 3 testes novos em
`backend/agentes/test_agente3_prescritor.py`
(`BuscarConceitosTest`) cobrindo o caso de acento+underscore, categoria
inexistente e não-duplicação; suíte completa do backend (todos os módulos
`test_*.py`) rodada depois do fix, saída limpa (`exit=0`), incluindo os 25
testes de `popular_fila_treino_espacado.py` (que consome
`buscar_conceitos()` mas mocka a função inteira, então não foi afetado
pela mudança de implementação interna). Contagem por categoria antes/depois
confirmada por query direta contra o Supabase de produção
(`pmzmershonrqzwbmhaco`), não estimada.

---

### D-76 — "Los 100 Finales que Hay que Saber" processado só para a busca vetorial, sem citação

**Contexto:** depois do D-75, `FINAIS` (14 conceitos) passou a ser a
categoria mais fraca entre as que ainda têm chance real de melhorar via
livro (`ESTRUTURA_DE_PEOES`, em 4, não tem mais candidato na biblioteca,
ver D-74). Testei 4 candidatos de finais: "Técnicas de Finais em Xadrez"
(Euwe/Hooper, 263 páginas) e "Teoria dos Finais de Partida" (Averbach, 98
páginas) são 100% imagem, sem camada de texto; "Dvoretsky — Endgame
Analysis" (131 páginas) tem texto nativo mas é uma compilação de exemplos
anotados, sem títulos de capítulo reconhecíveis; "Essential Chess Endings"
(162 páginas) e "Reuben Fine — Basic Chess Endings" (604 páginas) também
são 100% imagem. "Los 100 Finales que Hay que Saber" (Jesús de la Villa,
191 páginas) foi o único com texto nativo limpo.

**Achado no `--preview`:** esse livro organiza os finais individuais como
"Final 71. O rei cortado na oitava", não como "CAPÍTULO N" — formato que
`detect_chapter()` não reconhece. O que ele capturou foi só 4 marcadores
de seção de nível bem mais alto (que por acaso batem no padrão
`numbered_chapter_number`, ex. `"4. Dama contra peão"`), um deles
("4. Dama contra peão") absorvendo 124 dos 167 chunks, páginas 50–191 —
uma citação nesse nível seria tecnicamente real (é um título de seção
verdadeiro do livro) mas grosseira demais para servir de referência útil
por final individual. Também capturou 13 chunks de lixo de fonte de
diagrama (`"XIIIIIIIIY XIIIIIIIIY"`, o mesmo tipo de artefato do 5334 no
D-72, só que aqui misturado com conteúdo real em vez de ser o livro
inteiro).

**Decisão, com o usuário:** apresentei 3 caminhos (processar só para RAG
vetorial descartando a citação; investir em reconhecer o padrão "Final N."
no `detect_chapter()`; partir para OCR pesado num livro com capítulo mais
limpo). O usuário escolheu processar mesmo assim, só para a busca
vetorial — os 167 chunks têm conteúdo real e valioso (o RAG semântico não
depende de capítulo), só não geram citação nova em `indice_conceitual`.
Não rodei `sugerir_indice_conceitual.py`/`importar_indice_conceitual.py`
para este livro, de propósito. Zerei (`NULL`) o `capitulo` só do chunk de
lixo de diagrama, por precaução — mesmo sem citação automática, esse
campo pode aparecer em resultados de busca semântica exibidos ao usuário,
e `"XIIIIIIIIY XIIIIIIIIY"` como "fonte" ficaria visivelmente quebrado.
Mantive os 4 marcadores de seção reais como estão (incluindo o grosseiro
`"4. Dama contra peão"`) — são títulos verdadeiros do livro, só de baixa
resolução, categoria diferente do lixo de fonte.

**Verificação real:** `--preview` gratuito primeiro (167 chunks). Depois,
processamento completo contra produção (`pmzmershonrqzwbmhaco`):
`livros_chunks` 1187→1354 (confirmado por query). `indice_conceitual`
inalterado em 274 (confirmado por query, nenhuma sugestão gerada de
propósito).

---

### D-77 — "Understanding Chess Endgames" (Nunn) — mesmo tratamento do D-76, sem capítulo nenhum detectado

**Contexto:** o usuário colocou mais um livro na pasta de Finais depois do
D-76: "Understanding Chess Endgames" (John Nunn). Texto nativo confirmado
(234 páginas, sem OCR necessário), organizado do mesmo jeito problemático
do D-76 — títulos como `"31 Bishop and Two Pawns vs Bishop"` (final
numerado individual, sem palavra CAPÍTULO/PART) em vez de capítulo. O
`--preview` confirmou: **0 de 267 chunks** com capítulo detectado (pior que
o D-76, que ao menos capturou 4 marcadores de seção grosseiros — aqui nem
isso, porque a numeração de finais individuais desse livro não bate nem no
padrão `numbered_chapter_number`).

**Decisão:** mesmo tratamento do D-76, sem repetir a pergunta ao usuário
— o caso é estruturalmente idêntico e a decisão já tinha sido tomada:
processado só para `livros_chunks` (busca vetorial), sem rodar
`sugerir_indice_conceitual.py`/`importar_indice_conceitual.py`. Diferente
do D-76, não foi encontrado nenhum chunk de lixo de fonte de diagrama
neste livro (os diagramas aqui parecem ser imagem embutida, não fonte de
texto), então não precisou de limpeza adicional.

**Verificação real:** `--preview` gratuito primeiro (267 chunks, 0
capítulos). Processamento completo contra produção
(`pmzmershonrqzwbmhaco`): `livros_chunks` 1354→1621 (confirmado por
query). `indice_conceitual` inalterado em 274.

---

### D-78 — "Arte do Ataque no Xadrez" (Vukovic, só RAG) e "The Complete Manual of Positional Chess Vol 1" (Sakaev/Landa, com citação real) — escolhidos pelo maior conteúdo entre os candidatos já validados

**Contexto:** pedido do usuário — "escolha os próximos 2 livros que tem
mais conteúdo pra agregar nas nossas ferramentas". Entre os candidatos já
confirmados com texto nativo (sem OCR) nas checagens anteriores (D-74),
os dois maiores eram "Arte do Ataque no Xadrez" (Vukovic, 429 páginas) e
"The Complete Manual of Positional Chess Vol 1" (Sakaev/Landa, 320
páginas).

**"Arte do Ataque no Xadrez" — achado de inconsistência interna do
próprio livro:** o `--preview` deu 0 capítulos em 244 chunks. Investigando
a fundo (testando `detect_chapter()` linha a linha contra o texto real):
o sumário lista os capítulos como `"12. Título"` (com ponto — que bate no
`NUMBERED_CHAPTER_PATTERN`), mas o cabeçalho real de cada capítulo no
corpo do livro usa `"12 Título"` (só espaço, sem pontuação nenhuma — que
não bate). O pipeline já tem proteção deliberada contra confundir sumário
com capítulo real (só aceita capítulo numerado nas 2 primeiras linhas
"significativas" da página, e só em sequência estrita a partir de 1) —
essa proteção funcionou corretamente aqui, rejeitando tanto o sumário
quanto o corpo (que usa formato diferente). Cogitei relaxar
`NUMBERED_CHAPTER_PATTERN` para aceitar "N Título" sem pontuação, mas
isso abriria risco real de falso positivo: lances de xadrez anotados como
`"11 Qxd4 Rd8"` têm exatamente o formato "número + espaço + maiúscula" e
aparecem aos milhares num livro de ataque cheio de análise de partida — o
guard de sequência estrita reduz mas não elimina esse risco,
especialmente nos números baixos (1, 2, 3...) que colidem facilmente com
número de lance. Decidido não arriscar; mesmo tratamento do D-76/D-77 (só
RAG vetorial), sem repetir a pergunta ao usuário por já ser padrão
estabelecido para esse tipo de caso.

**"The Complete Manual of Positional Chess Vol 1" — capítulo real,
título verificado manualmente antes da sugestão:** aqui o `--preview` já
veio bom de cara — 30 capítulos detectados (`Chapter N`), sequenciais,
5–20 páginas cada. Mas o título capturado era só `"Chapter N"`, sem a
frase descritiva (que fica na linha seguinte, não capturada pelo
`CHAPTER_PATTERNS`, que só olha o sufixo na mesma linha). Antes de rodar
qualquer coisa cara, extraí o título real de cada um dos 30 capítulos
direto da página (via `pdfplumber`, sem custo), lendo as primeiras linhas
de cada página de início de capítulo — não inventei nenhum título, todos
vêm do texto literal do livro. Apliquei essas correções em `livros_chunks`
**antes** de rodar `sugerir_indice_conceitual.py`, ao contrário do D-74
(onde a correção veio depois, por já ter descoberto o problema só na
revisão). Resultado: as 96 sugestões saíram já com título completo e
correto, sem precisar de revisão/descarte pós-geração como no D-74.

**Achado lateral, dois processos do SO por uma única execução:**
verificando por que o processamento do Sakaev/Landa não mostrava progresso
por vários minutos, encontrei um processo filho (`C:\Python312\python.exe`)
gerado pelo processo da venv, com CPU real (38s) e memória real (1,5GB) —
diferente do bug do D-72 (que eram processos duplicados/órfãos de
execuções distintas), aqui é pai+filho de uma única invocação, o pai
ficando ocioso enquanto o filho faz o trabalho de verdade. Confirmado via
`ParentProcessId` antes de mexer em qualquer coisa — não matei nenhum
processo, só esperei terminar.

**Verificação real:** `--preview` gratuito nos dois antes de gastar
qualquer coisa. Processamento completo contra produção
(`pmzmershonrqzwbmhaco`): `livros_chunks` 1621→2092 (+244 Vukovic +227
Sakaev/Landa, confirmado por query). Títulos dos 30 capítulos do
Sakaev/Landa corrigidos e conferidos por query antes da sugestão de
conceito. `indice_conceitual` 274→370 (+96, só do Sakaev/Landa).
Recontagem por categoria: TATICA 38→57, ESTRATEGIA 36→40, CALCULO 32→52,
GESTAO_DE_TEMPO 13→18, FINAIS 14→15, ESTRUTURA_DE_PEOES continua em 4.

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
