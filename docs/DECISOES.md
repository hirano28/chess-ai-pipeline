---
doc: DECISOES.md
escopo: decisões de design e o motivo delas; conhecimento durável, não envelhece
regra: nunca reescreva uma decisão antiga — acrescente uma nova marcando a anterior como substituída
verificado_em: 2026-09-11
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

## Decisões tomadas sobre o que NÃO fazer

- **ChessTempo não tem API pública.** Não gaste tempo tentando integrar; a
  alternativa adotada foi migrar exercícios temáticos para o sistema de puzzles
  do Lichess, que tem API.
- **Modelo Maia personalizado** (distinguir erro previsível de aleatório) é
  tecnicamente interessante mas exige treinar rede neural. Fora de escopo até o
  resto do roadmap amadurecer.
- **Gemini Code Assist na IDE** foi descontinuado pelo Google em 18/06/2026. Não
  é bug local e não tem correção.
