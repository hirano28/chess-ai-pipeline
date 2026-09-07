# Roadmap de Evolução — Do Diagnóstico por Blunder ao Diagnóstico Multidimensional

Consolidação das duas pesquisas em fases executáveis, na ordem de melhor custo-benefício (mais barato e maior impacto primeiro). Numeração continua a partir da Fase 11 (loop adaptativo) do guia original.

---

## Por que essa ordem

1. **Fases 12-13** corrigem o viés estrutural do sistema atual (tudo vira "tática") sem exigir nenhuma coleta de dado novo — só reprocessamento do que já existe.
2. **Fase 14** adiciona a coleta que falta e é barata (relógio já vem no PGN).
3. **Fase 15** é a peça mais inovadora (ninguém documentado faz isso) — captura de pensamento via Lichess Studies.
4. **Fases 16-17** são enriquecimento incremental, podem esperar.

---

## Status geral (atualizado em 07/09/2026)

- ✅ **Fase 12 concluída e validada matematicamente.** Testes confirmam a curva de Win% batendo com os valores públicos do Lichess (cp 300 → ~75%, 800 → ~95%), e a comparação de queda em posição equilibrada vs. já ganha confirma o objetivo (16,4 pontos percentuais de diferença).
- ✅ **Fase 13 concluída e validada com 2 partidas reais anotadas manualmente** (`cwrI5a8c` e `AmxiZxvj`). Achados-chave:
  - Confirmado: erros de processo que o próprio jogador identificou (ex: xeque não visto, ameaça percebida tarde) ficam **invisíveis** para o critério de gravidade isolada — só a erosão ou a própria anotação os capturam.
  - Bug real encontrado e corrigido: o prompt do Agente 1 aplicado a eventos `EROSAO` inicialmente invertia a perspectiva (atribuía lances do próprio jogador ao oponente) e citava lances fora da janela. Corrigido com prompt dedicado (`build_erosion_prompt`), roteado por `tipo_evento`.
  - **Achado novo e não previsto:** o detector de erosão revelou um padrão comportamental — a dama fazendo manobras repetidas e desconectadas (`Qc4-Qd3-Qc4`) enquanto o resto das peças fica parado — que o vocabulário atual de 16 tags não nomeia bem. Candidato a nova tag: `falta_de_coordenacao_de_pecas` (já usada pelo LLM organicamente, fora do vocabulário controlado — precisa ser formalizada ou mapeada para uma tag existente).
- 🆕 **Achado que muda a Fase 14/15:** o próprio Lichess já calcula precisão/erros por fase (abertura/meio-jogo/final) e tem gráfico de tempo por lance com a curva de avaliação sobreposta ("Análise do computador" + "Tempo por movimento" na interface). Isso é exposto via API (`GET /game/export/{id}?evals=1&accuracy=1&clocks=1&division=1`, formato JSON) — não precisamos recalcular isso do zero com nosso próprio Stockfish, só consumir o que já existe pronto. Fases 14 e 15 abaixo foram ajustadas para refletir isso.

**Ação pendente de decisão:** formalizar `falta_de_coordenacao_de_pecas` no vocabulário controlado (17ª tag) ou mapear para uma existente antes de escalar o processamento — decidir antes ou durante a Fase 14.

---

## Fase 12 — Corrigir a métrica de gravidade (Win% em vez de centipawns crus)

**Problema que resolve:** hoje, perder 300cp numa posição equilibrada e numa posição já ganha contam igual — distorcendo qual lance é "mais crítico".

**O que muda:**
- Nova função utilitária: `centipawns_para_win_percent(cp)` usando a fórmula pública do Lichess:
  `Win% = 50 + 50 * (2 / (1 + exp(-0.00368208 * cp)) - 1)`
- `analisar_partidas.py` passa a calcular a gravidade de cada lance como **queda de Win%**, não `avaliacao_depois_cp - avaliacao_antes_cp` cru.
- Adicionar coluna `queda_win_percent` em `lances_criticos` (manter `gravidade_cpl` para não quebrar histórico).

**Critério de sucesso:** reprocessar uma amostra de partidas já conhecidas e confirmar que lances em posições já decididas (ex: +8 caindo para +5) deixam de aparecer no topo de gravidade, e lances em posições equilibradas (ex: 0 caindo para -2) sobem no ranking.

**Modelo sugerido:** Claude Sonnet 5 — lógica matemática simples e bem especificada, sem ambiguidade de design.

---

## Fase 13 — Detector de erosão estratégica (ataca o viés tático)

**Problema que resolve:** erros estratégicos não aparecem porque nunca causam um pico isolado — se dissolvem ao longo de vários lances.

**O que muda:**
- Nova função em `analisar_partidas.py`: percorre os lances do jogador em janelas deslizantes (ex: 8 lances), soma a perda de Win% acumulada na janela. Se ultrapassar um limiar (ex: 15 pontos de Win% sem nenhum lance individual ultrapassar o limiar de "crítico" isolado), registra como um novo tipo de evento: `erosao_estrategica` (nova tabela ou campo `tipo_evento` em `lances_criticos`: `'PICO'` vs `'EROSAO'`).
- O Agente 1 recebe esse tipo de evento com um prompt diferente — não "que erro neste lance", mas "que padrão nesta sequência de 8 lances causou a perda gradual de vantagem".

**Critério de sucesso:** rodar contra o histórico completo e verificar se `ESTRATEGIA`/`ESTRUTURA_DE_PEOES` deixam de ter contagem quase zero — mesmo que a mudança seja modesta, qualquer aumento real confirma que o detector está funcionando.

**Modelo sugerido:** Claude Opus 4.8 — é uma decisão de design nova (defini limiares, estrutura de dados), maior risco de acerto na primeira tentativa importar.

---

## Fase 14 — Estatísticas por fase, cor e abertura (AJUSTADA: puxar do Lichess, não recalcular)

**Problema que resolve:** hoje não há visão de "erro em qual fase" nem "problema de repertório".

**Ajuste importante (07/09/2026):** o Lichess já calcula precisão e contagem de erros por fase (abertura/meio-jogo/final) para toda partida analisada por ele. Em vez de recalcular isso do zero com nosso próprio Stockfish (caro e redundante), a Fase 14 passa a ser majoritariamente um **ETL simples**: puxar o que já existe pronto.

**O que muda:**
- Novo script `backend/ingestao/enriquecer_partidas_lichess.py`: para cada `external_id` de partida do Lichess já em `partidas`, chama `GET https://lichess.org/game/export/{id}?evals=1&accuracy=1&clocks=1&division=1&opening=1` (header `Accept: application/json`), extrai:
  - `players.white/black.analysis.inaccuracy/mistake/blunder/acpl` (erros e ACPL por jogador).
  - `division` (índices de lance onde abertura/meio-jogo/final começam).
  - Isso NÃO se aplica a partidas do Chess.com (API diferente, sem esse endpoint) — documentar essa limitação: enriquecimento só cobre Lichess por enquanto.
- Nova tabela `metricas_lichess_partida` (partida_id, precisao_propria, precisao_oponente, imprecisoes, erros, blunders, acpl, fase_abertura_fim, fase_meiojogo_fim).
- `agente2_analista.py`: passa a cruzar essas métricas com win-rate por ECO (que você já coleta) e por cor — sem precisar computar ACPL por fase manualmente.
- Novo card no dashboard mostrando essas quebras.

**Critério de sucesso:** conseguir responder "eu jogo pior de brancas ou pretas?" e "meu problema é mais em aberturas específicas ou geral?" só olhando o dashboard — usando dado que o Lichess já validou, não uma reimplementação nossa sujeita a bugs de cálculo.

**Modelo sugerido:** Claude Sonnet 5.

---

## Fase 15 — Coletar tempo de relógio (fecha a lacuna de GESTAO_DE_TEMPO)

**Problema que resolve:** essa categoria está zerada desde o início — não por você ter ótima gestão de tempo, mas porque nunca coletamos o dado.

**Ajuste (07/09/2026):** o mesmo endpoint da Fase 14 (`?clocks=1`) já traz o relógio por lance para partidas do Lichess — reaproveitar o mesmo script de enriquecimento em vez de reimplementar parsing de `%clk` do zero (embora o PGN também tenha isso nativamente e sirva de fallback para Chess.com, cuja API é diferente e precisa de tratamento próprio).

**O que muda:**
- Reaproveitar `enriquecer_partidas_lichess.py` (Fase 14) para extrair também o array de `clocks` por lance, salvando em nova tabela `tempos_lance` (partida_id, numero_lance, tempo_restante_seg).
- Para Chess.com: extrair `%clk` diretamente do PGN já armazenado (não depende de API externa, já temos o dado bruto salvo).
- `analisar_partidas.py`: ao identificar um lance crítico, anexar o tempo restante e o tempo gasto naquele lance via join com `tempos_lance`.
- Novo critério no Agente 1: se o tempo restante estava abaixo de um limiar (ex: <30s ou <15% do tempo total do controle), a tag preferencial passa a ser `gestao_de_tempo_ruim`, sobrepondo o palpite "cognitivo" — separando erro por pressão de tempo de erro por desconhecimento real.

**Critério de sucesso:** `gestao_de_tempo_ruim` sai de zero; idealmente você consegue ver se seus blunders táticos concentram-se em apuro de tempo (mudaria o treino de "mais teoria" para "disciplina de relógio").

**Modelo sugerido:** Claude Sonnet 5 para o parsing; Claude Opus 4.8 se a lógica de "sobrepor tag por tempo" gerar ambiguidade com o restante do pipeline do Agente 1.

---

## Fase 16 — Captura de pensamento via Lichess Studies (a peça mais nova)

**Problema que resolve:** hoje o LLM adivinha a causa olhando só a posição final — nunca sabe se você nem viu a ameaça (erro de processo) ou se viu e avaliou errado (erro de conteúdo).

**Validado manualmente em 07/09/2026** com uma partida real (`cwrI5a8c`) anotada por você e comparada linha a linha com o diagnóstico automático. Achados que mudaram o desenho original:

- Nos lances onde a anotação e o diagnóstico automático coincidiram (ex: lance 28, `Rxe3`), o Agente 1 já havia acertado sozinho a tag `visao_em_tunel` — mas sua anotação (*"estava focadíssimo... nem cogitei outros lances"*) confirma a causa real com uma certeza que o LLM não tem sozinho.
- **Achado mais importante:** dois erros de processo que você mesmo identificou (lance 15, xeque não visto; lance 26, ameaça percebida tarde) **nem apareceram na lista de lances críticos do Stockfish**, porque a queda de avaliação foi pequena demais (perda de 1 peão, não de a partida). Ou seja, o critério de seleção por gravidade **esconde exatamente o tipo de erro de processo mais recorrente e mais fácil de corrigir** (checklist de verificação antes de jogar).

**Refinamento no desenho (o que muda vs. a versão original desta fase):** o critério de "o que vira lance crítico" não pode depender só de gravidade/Win%. Um lance **com anotação sua** deve ser promovido a analisável mesmo com gravidade baixa — a existência do seu relato já é, por si, sinal de valor diagnóstico.

**O que muda (fluxo em 4 partes, era 3):**
1. **Escrever:** depois de jogar, você abre a partida no Lichess, cria/edita um Study, e comenta por lance nos momentos que sentiu difíceis — independente de saber se o motor vai considerar aquele lance "crítico". Prompts sugeridos: "que candidatos eu vi?", "considerei as ameaças do adversário?", "por que descartei a alternativa?". *(Já testado manualmente com resultado excelente — suas anotações livres, sem template, já saíram específicas o suficiente.)*
2. **Puxar:** novo script `backend/ingestao/importar_anotacoes_lichess.py`, usando a lib `berserk`, chama `GET /api/study/{id}.pgn?comments=true`, faz parse dos comentários por lance com `python-chess`, e salva numa nova tabela `anotacoes_pensamento` (partida_id + numero_lance + texto).
3. **Promover lances anotados:** em `analisar_partidas.py`, depois de escolher os lances críticos por gravidade normalmente, adicionar uma segunda passada: qualquer lance com anotação em `anotacoes_pensamento` que ainda não esteja em `lances_criticos` é inserido também (com sua própria gravidade real, mesmo que baixa) — marcando a origem (`origem: 'GRAVIDADE' | 'ANOTACAO'`).
4. **Cruzar:** o Agente 1 recebe, quando existir, o texto da anotação junto com a linha do Stockfish, e classifica: você mencionou a ameaça/lance que o motor aponta (→ erro de **conteúdo**, viu mas avaliou errado) ou não mencionou nada disso (→ erro de **processo**, nem cogitou). Novo campo `tipo_erro: 'PROCESSO' | 'CONTEUDO' | 'INDETERMINADO'` em `diagnosticos`.

**Pré-requisito:** gerar um token OAuth do Lichess com escopo `study:write` (em `lichess.org/account/oauth/token`), adicionar como `LICHESS_STUDY_TOKEN` no `.env`.

**Critério de sucesso:** com as próximas 5-10 partidas anotadas, o Agente 1 deve capturar tanto os erros de processo pequenos (tipo o xeque não visto) quanto os grandes (tipo o Rxe3), e classificar corretamente `tipo_erro` comparado ao que você mesmo diria.

**Modelo sugerido:** Claude Opus 4.8 — funcionalidade nova sem precedente conhecido, com risco real de o primeiro design não funcionar bem; vale o investimento de um modelo mais forte.

---

## Fase 17 — Gap puzzle vs. partida (opcional, complementar)

**Problema que resolve:** distingue "não conhece o padrão" de "conhece mas falha em aplicar sob pressão real".

**O que muda:**
- Novo script que puxa seu histórico de rating de puzzles via API do Lichess.
- Compara com seu desempenho tático em partida (frequência de `calculo_tatico_deficiente` normalizada).
- Se o gap for grande, uma nova tag entra no vocabulário: `falha_de_vigilancia_tatica` (você sabe o padrão, mas não está buscando ativamente por ele na partida).

**Critério de sucesso:** uma resposta clara a "eu preciso estudar mais teoria tática, ou preciso treinar reconhecimento sob pressão?".

**Modelo sugerido:** Claude Sonnet 5.

---

## Fase 18 — APIs adicionais (Opening Explorer, Tablebase) — enriquecimento incremental

- **Opening Explorer** (`explorer.lichess.org`, sem autenticação): marcar o lance exato em que você "saiu da teoria" e a avaliação daquele ponto — alimenta diagnóstico de abertura sem depender só do ECO.
- **Tablebase Syzygy** (`tablebase.lichess.org`, ≤7 peças): validar objetivamente erros de conversão em finais — hoje o vértice FINAIS é diagnosticado só pelo Stockfish normal, sem saber se era teoricamente ganho/perdido de forma provada.

**Modelo sugerido:** Claude Sonnet 5.

---

## Não fazer agora (fica para bem mais adiante, se algum dia)

- **Modelo Maia personalizado** — tecnicamente interessante (distinguir erro previsível de aleatório), mas exige rodar/treinar um modelo de rede neural, complexidade bem maior que o resto do pipeline. Só valeria depois que as Fases 12-17 estiverem maduras e você quiser ir mais fundo.

---

## Ordem recomendada de execução

12 → 13 → 14 → 15 → 16 → 17 → 18. Mas 14 e 18 são independentes das demais e podem ser intercaladas conforme sua energia/tempo disponível — só 12-13 (correção de métrica) e 15-16 (relógio → uso no Agente 1) têm dependência real de ordem.
