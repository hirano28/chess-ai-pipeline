# Ferramentas gratuitas para capturar e diagnosticar o "processo de pensamento" no seu pipeline de treino de xadrez

## TL;DR
- **A melhor forma de capturar o think-aloud de forma assíncrona já existe e é gratuita: Lichess Studies.** Você cria um capítulo por partida, escreve seus pensamentos como comentários por lance (entre chaves no PGN) e o pipeline exporta tudo via API (`GET /api/study/{id}.pgn?comments=true`), cruzando o texto do jogador com o diagnóstico do Stockfish/Gemini no mesmo lance. É a única peça que você não precisa construir do zero.
- **A ideia de classificar automaticamente "erro de processo" vs "erro de conteúdo" a partir do relato do próprio jogador parece ser território inédito** — existe a base teórica (Heisman, de Groot) e existem ferramentas engine→explicação (DecodeChess, Blunder Tutor, ChessLogix Decision Patterns), mas nenhum projeto conhecido cruza o *relato introspectivo do jogador* com a linha do engine para essa distinção. Você estaria construindo algo novo.
- **APIs gratuitas com valor diagnóstico real para integrar já:** Opening Explorer (`explorer.lichess.org`, masters + lichess DB, CORS aberto, sem auth), Tablebase Syzygy de 7 peças (`tablebase.lichess.org`), Puzzle Dashboard/temas e o dump público de puzzles do Lichess (6.057.356 puzzles, CC0, com temas taggeados automaticamente), além do próprio export de partidas com `evals`/`accuracy`/`clocks` em JSON.

## Key Findings

### 1. Lichess Studies é a solução pronta para captura do think-aloud
- **Comentários por lance:** cada lance num Study pode ter comentário de texto (antes e depois), setas/círculos e NAGs (`?!`, `??`, `$1`…). Isso é exatamente o "diário de raciocínio" que você precisa.
- **API de escrita:** `POST /api/study/{studyId}/import-pgn` (via `berserk`: `client.studies.import_pgn(study_id, chapter_name, pgn, orientation='white', variant='standard')`) cria um capítulo por partida a partir de um PGN. Requer token OAuth com escopo `study:write`. Se o PGN tiver comentários `{...}` e NAGs, eles são preservados no capítulo. Múltiplos jogos num só PGN (separados por 2+ quebras de linha) geram múltiplos capítulos.
- **Limites confirmados por staff do Lichess:** até **64 capítulos por estudo** e **300 lances por jogo** por capítulo. Um post de coach observa que, jogando bastante, você acaba batendo no limite de 64 capítulos no study de "log de partidas", mas "nesse ponto é fácil só criar um novo estudo".
- **API de leitura (o coração do cruzamento):** `GET /api/study/{studyId}.pgn` e `.../{chapterId}.pgn` com `comments=true` (default) retornam os comentários do jogador junto dos lances. Para PGN limpo, usa-se `?comments=false&variations=false`.
- **Confirmação de round-trip:** exports reais mostram comentários preservados, ex.: `9. dxc5 d4 { Now that the knight is on a3 let's leave it there }`. Logo, escrever PGN com comentários → importar → exportar preserva o texto por lance.
- **Ressalva:** a API NÃO permite setar "interactive lessons/hints" via PGN (isso é metadado próprio do Lichess). Mas comentários de texto e NAGs — que é o que você precisa — funcionam normalmente.
- **Uso documentado como diário de treino:** treinadores e jogadores fortes descrevem exatamente esse uso. Um GM descreve Studies como "um caderno de xadrez interativo que salva seu trabalho... completamente grátis" e recomenda um Study dedicado a "log de suas próprias partidas". O post "The 4 Lichess studies I make for improvement" (zwischenzug.substack.com) detalha um setup de studies: log de partidas, aberturas, e um study de "Flashcards" para "salvar posições importantes ou instrutivas das suas próprias partidas".

### 2. Lichess NÃO tem captura de voz nem anotação rápida durante partida ao vivo (confirmado)
- Existe a caixa **"Notes"** ao lado do tabuleiro durante a partida, mas: é uma nota livre única (não por lance), e a comunidade confirma que na prática só é usada em partidas por correspondência/longas — não serve para rapid cronometrado sem atrapalhar.
- Há um **feature request aberto** (lila #5155) pedindo "nota privada por lance" justamente para "registrar o processo de pensamento durante o jogo e depois analisar as fraquezas" — ou seja, o Lichess reconhece o caso de uso mas ainda não o implementou nativo durante a partida.
- Conclusão: para partidas rated rapid, o caminho é **assíncrono** (escrever depois, no Study), não durante.

### 3. A distinção processo vs conteúdo tem base teórica sólida mas automatização é inédita
- **Heisman (processo vs conteúdo):** "a thought process error is different than a thought content error; in the latter, the process is correct but the player makes a mistake in the content of the analysis or the evaluation". Taxonomia de erros de processo listada no site dele: Quiescence Errors, Hand-Waving, Hope Chess, "Just Because It's Forced", "Look Wide Before You Look Deep" (tunnel vision), jogar rápido/devagar demais, etc.
- **de Groot / think-aloud:** metodologia clássica (*Thought and Choice in Chess*; fases orientação, exploração, investigação, prova), replicada com lances graded por engine em **Connors, Burns & Campitelli (2011), "Expertise in Complex Decision Making: The Role of Search in Chess 70 Years After de Groot," *Cognitive Science*, Vol. 35, No. 8, pp. 1567–1579**. A amostra foi "Six Grandmasters, five International Masters, six Experts, and five Class A players completed the think-aloud procedure for two chess positions", e o achado central é que "Grandmasters and International Masters search more quickly than Experts and Class A players... both groups today search substantially faster than players in previous studies".
- **Prior art de automação:** existem ferramentas engine→explicação (DecodeChess; Blunder Tutor open-source que classifica blunder em "missed tactic" vs "allowed tactic" via python-chess; ChessLogix "Decision Patterns" com 16 labels de hábito a partir do eval swing; Caïssa AI neuro-simbólico Prolog+Neo4j+LLM para comentário fundamentado). Mas todos diagnosticam a partir da posição/eval, **nunca do relato do jogador**.
- **Lacuna confirmada:** nenhum paper, tese ou repositório encontrado cruza o *relato do próprio jogador* com o engine para dizer "processo vs conteúdo". É nicho aberto — a recomendação é posicionar seu recurso explicitamente sobre Heisman + de Groot como base teórica, e sobre ChessLogix Decision Patterns / DecodeChess como o prior art *automatizado* mais próximo (que você estende ao adicionar a dimensão do relato).
- **Caveat técnico repetidamente documentado:** LLMs alucinam ao avaliar posições sozinhos, mas vão bem ao *explicar análise pré-computada* do engine. Portanto o Gemini deve receber a linha do Stockfish + o relato do jogador e apenas comparar os dois, não avaliar a posição por conta própria.

### 4. APIs e datasets gratuitos que agregam valor ao pipeline
- **Opening Explorer** (`explorer.lichess.org`): endpoints `/masters`, `/lichess`, `/player`. Sem autenticação, CORS aberto (`Access-Control-Allow-Origin: *`), sem rate limit rígido documentado. Retorna estatísticas W/D/L por lance. Útil para detectar "saiu da teoria no lance X" e enriquecer o diagnóstico da fase de abertura.
- **Tablebase Syzygy 7 peças** (`tablebase.lichess.org/standard?fen=...`): JSON com categoria (win/draw/loss, cursed-win, blessed-loss), DTZ/DTM. Sujeito ao rate limiting geral da API; para volume alto, baixar os tables e sondar localmente. Valor para o vértice FINAIS do hexágono — verifica objetivamente se um lance de final foi um erro de conversão.
- **Puzzle Dashboard / temas:** página `/training/dashboard/30` com Strengths e Improvement Areas por tema. **Dump público oficial de puzzles em `database.lichess.org` (CC0): atualmente 6.057.356 puzzles, "rated, and tagged".** Segundo o Lichess, "Generating these chess puzzles took more than 100 years of CPU time. We went through 600,000,000 analysed games from the Lichess database, and re-analyzed interesting positions with Stockfish NNUE at 40 meganodes. The resulting puzzles were then automatically tagged". Existe também um dataset combinado puzzle+jogo de terceiros (mcognetta, ndjson, CC0) — porém esse é menor e mais antigo: "The puzzle data was pulled in September 2022. There are 2,969,948 puzzles in total". Bom para alimentar sprints de treino por tema alinhados ao hexágono.
- **Export de partidas em JSON:** `GET /game/export/{id}?evals=1&accuracy=1&clocks=1&opening=1&division=1` com header `Accept: application/json`; accuracy e ACPL ficam sob o campo `players`. `division` dá marcadores de fase (opening/middle/endgame). Isso complementa sua análise local do Stockfish com metadados já calculados pelo Lichess.
- **Lichess Insights:** "answer engine" que indexa suas partidas (move times, fase, imbalances, ACPL, etc.). Não tem API pública de export dedicada — é uma ferramenta de UI. Serve de inspiração de dimensões, mas não é fonte programática.

### 5. Ferramentas de terceiros gratuitas/open-source relevantes
- **Blunder Tutor** (MrLokans, open-source, self-hosted, Docker): pipeline quase idêntico ao seu (fetch Lichess/Chess.com → Stockfish → classifica lance → detecta padrões táticos/armadilhas → treina em cima dos seus blunders). Classifica blunder em "missed tactic" vs "allowed tactic" com python-chess puro, sem engine. Boa referência de arquitetura e de "winning chances" (abordagem Lichess) em vez de centipawn cru. O próprio autor sugere, como versão futura, "feed Stockfish's PV line and positional features into an LLM" — exatamente o padrão que você já usa com o Gemini.
- **obsidian-chess-study** (open-source): plugin do Obsidian que persiste PGN + comentários + setas em JSON no vault. Alternativa de captura se você preferir markdown/Obsidian como front de journaling.
- **LiChess Tools** (extensão Siderite, Firefox/Chrome, grátis): "Explorer Practice" (jogar contra os lances do Explorer em qualquer faixa de rating), merge de PGNs, editor de PGN robusto. Útil para praticar posições específicas.
- **Caïssa AI** (open-source no GitHub, MazenS0liman): agente neuro-simbólico LLM+Prolog+Neo4j+LangGraph que verifica o comentário do LLM contra lógica simbólica para reduzir alucinação. Referência conceitual forte para o seu problema de "não deixar o Gemini inventar a causa". (Cuidado: há outros projetos homônimos "Caissa" no GitHub que são apenas simuladores de partidas Stockfish — não confundir.)
- **SDKs oficiais:** `berserk` (Python) é o cliente oficial e cobre studies, games, puzzles, tablebase, explorer. Recomendado para o seu stack Python.

### 6. Prática documentada de "chess journal / mistake log"
- Rotina de duas passadas amplamente recomendada: auto-avaliação curta (10–20 min) logo após a partida enquanto os pensamentos estão frescos, depois passada profunda (45–60 min) no dia seguinte, mantendo um journal semanal de "Mistake → Habit".
- "Personal Mistake Database": registrar padrões recorrentes de erro para tornar o treino direcionado em vez de aleatório ("cada partida vira dado de treino").
- Consenso dos coaches: **escrever o próprio raciocínio ANTES de ligar o engine** é o passo de maior valor — captura tunnel vision, pânico de tempo, negligência de segurança do rei. Chess.com tem "Retry Mistakes"; a prática recomendada é perguntar "o que eu deveria ter considerado aqui?".
- Prompts pós-jogo recomendados por coaches: "houve lances do adversário que me surpreenderam?" (indica cálculo incompleto), análise de uso do tempo, e comparar sua escolha com master games na mesma variação.
- Para o público 1700–2100 especificamente: a distinção "que TIPO de erro" (perdeu ameaça / pânico / apressou por parecer simples / entendeu errado o plano) é apontada como o que realmente destrava melhora nessa faixa, mais do que decorar linhas de engine.

## Details

### Fluxo recomendado de captura (assíncrono, sem atrasar rapid rated)
1. Jogar a partida rated normalmente no Lichess (sem anotar durante).
2. Logo após (janela de 10–20 min, pensamentos frescos): abrir a partida, ir em Analysis board → hamburger → Study, e escrever em cada momento crítico o que estava pensando *durante* aquele lance — em linguagem natural, entre chaves (comentário por lance). Opcionalmente marcar NAGs.
   - Alternativa para "jogos de prática" dedicados: partidas casuais/untimed onde você faz think-aloud mais completo.
3. O pipeline chama `GET /api/study/{id}.pgn?comments=true`, faz parse dos comentários por lance (python-chess), e para cada lance crítico já detectado pelo Stockfish, alinha: (a) eval swing + melhor linha do engine, (b) causa tagueada pelo Gemini, (c) texto do jogador.
4. O Gemini recebe os três e classifica: se o jogador **não menciona** a ameaça/linha que o engine aponta → forte sinal de **erro de processo** (não considerou); se **menciona mas avaliou errado** ("achei que Qxc1 era forçado") → **erro de conteúdo**. Isso ancora a orientação de treino na causa real.

### Por que Studies e não a caixa "Notes" ou voz
- "Notes" é nota única por partida, não por lance, e some do fluxo programático (não vem no export estruturado por lance). Voz durante partida ao vivo não existe no Lichess. O feature request lila #5155 confirma que a nota-por-lance-durante-o-jogo ainda é só pedido, não recurso. Studies é o único mecanismo nativo, gratuito, com API, que amarra texto a lance específico e é exportável.

### Nota sobre speech-to-text
- Para o think-aloud oral (mais fiel ao protocolo de de Groot), a captura de áudio + transcrição roda fora do Lichess (qualquer STT: Whisper local é gratuito/open-source). O texto transcrito então entra como comentário no Study via `import-pgn`, ou direto no seu Supabase. Ferramentas de "AI coach por voz" (Chessy/Chessvia) existem mas são freemium/pagas e não expõem API para seu pipeline.

## Recommendations

**Estágio 1 — Adotar Lichess Studies como camada de captura (fazer primeiro):**
- Criar um Study privado por período (ex.: mensal, respeitando o teto de 64 capítulos) e usar `berserk` para `import_pgn` de cada partida crítica como capítulo. Token com escopo `study:write`.
- Padronizar um template de prompts no comentário do lance crítico: (1) "Que candidatos eu vi?"; (2) "Considerei checks/captures/threats do adversário?"; (3) "Por que rejeitei a alternativa?"; (4) "Estava em apuro de tempo?". Isso força um relato que discrimina processo vs conteúdo.
- Threshold que muda a decisão: se você não conseguir manter o hábito de escrever em mais de ~60% das partidas críticas, migre para think-aloud oral + Whisper (menor fricção) em jogos de prática dedicados.

**Estágio 2 — Implementar o classificador processo/conteúdo:**
- Alinhar por lance: comentário do jogador × PV do Stockfish × tag do Gemini. Prompt do Gemini deve ser de *comparação* (recebe a linha do engine já pronta), nunca de avaliação da posição — para evitar alucinação (lição do Caïssa AI e do Blunder Tutor).
- Começar com um esquema binário (processo/conteúdo) + "indeterminado" quando o relato for vago. Só refinar para a taxonomia fina de Heisman (hope chess, quiescência, tunnel vision) depois de validar o binário.
- Como é território inédito, versionar com cuidado e guardar exemplos rotulados manualmente por você para medir a precisão do Gemini (crie um pequeno "gold set" de 30–50 lances rotulados à mão como benchmark).

**Estágio 3 — Enriquecer o pipeline com APIs gratuitas:**
- Integrar **Opening Explorer** para marcar o ponto de saída da teoria e alimentar o vértice ESTRATEGIA/abertura.
- Integrar **Tablebase** para validar objetivamente erros no vértice FINAIS (≤7 peças).
- Puxar `accuracy`/`ACPL`/`division` do export JSON para calibrar a detecção de lance crítico e a métrica de GESTAO_DE_TEMPO (via `clocks`).
- Considerar o **dump de puzzles CC0** (6 milhões, taggeados por tema) para gerar sprints de treino direcionados ao vértice mais fraco do hexágono.
- Estudar a arquitetura do **Blunder Tutor** (winning-chances em vez de centipawn cru; classificação missed/allowed tactic com python-chess) para melhorar sua detecção de lances críticos sem custo de engine adicional.

## Caveats
- **Fricção de escrita é o maior risco do projeto.** A literatura de journaling é unânime que o valor vem de escrever *antes* do engine, mas a adesão é o gargalo; por isso a captura assíncrona logo após o jogo (pensamentos frescos) é essencial.
- **Ausência de precedente não é prova de impossibilidade nem de inexistência absoluta** — uma tese de nicho ou ferramenta privada pode existir; a busca em arXiv/GitHub/blogs não retornou match, o que sugere fortemente originalidade, mas não é exaustivo.
- **Lichess rate limits:** respeitar o limite geral da API (uma chamada por vez, back-off em 429); tablebase e export em lote (300 jogos/req) têm restrições; para volume, usar os dumps locais (`database.lichess.org`).
- **Insights não tem API de export** — não conte com ele como fonte programática; use o export de partidas em JSON.
- **Comentários em import-pgn:** o round-trip de `{comentários}` e NAGs é confirmado por exports reais, mas não há uma frase única na spec dizendo "import preserva NAGs"; trate como inferência de alta confiança e valide com um teste real no seu fluxo antes de depender dele em produção.
- **Viés de fontes:** parte do material de "como analisar partidas" vem de blogs comerciais de xadrez (chessworld, chessdock, substacks de coaches); as afirmações metodológicas são consistentes entre si e com Heisman/de Groot, mas não são estudos controlados.

---

### Fontes principais
- Lichess API (studies, games, tablebase, opening explorer, puzzles): lichess.org/api, github.com/lichess-org/api, deepwiki.com/lichess-org/api, lichess-api.readthedocs.io, cliente `berserk`.
- Lichess forum / lila issues: #5155 (nota por lance), #13387 (export com comentários), threads sobre export/import de studies e limites (64 capítulos, 300 lances).
- database.lichess.org (dump de puzzles CC0, 6.057.356); mcognetta.github.io (dataset combinado 2,9M, 2022).
- Dan Heisman: danheisman.com (thought process errors, definitions), chess.com/blog/danheisman.
- de Groot: chessprogramming.org/Adriaan_de_Groot; Connors, Burns & Campitelli (2011), *Cognitive Science* 35(8):1567–1579 (Wiley).
- Blunder Tutor: mrlokans.work + github.com/MrLokans/chess-blunder-trainer.
- Caïssa AI: github.com/MazenS0liman/Caissa-AI; link.springer.com/chapter/10.1007/978-3-032-02813-6_11.
- Journaling/mistake log: chessworld.net, chessdock.com, worldchess.com/blogs, chesschatter.substack.com, zwischenzug.substack.com, ragchess.com/navigate-lichess, nextlevelchess.com.
- Outros: obsidian-chess-study (github.com/chrislicodes), LiChess Tools (Siderite), Lichess Insights blog (lichess.org/blog).