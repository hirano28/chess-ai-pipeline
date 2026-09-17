---
doc: OPERACAO.md
escopo: comandos, execução de scripts, automação, variáveis de ambiente, troubleshooting
nao_contem: arquitetura (ver ARQUITETURA.md), schema (ver BANCO.md), estado (ver ESTADO.md)
verificado_em: 2026-09-16
---

# Operação

## 1. Ambiente local

```bash
# Windows / PowerShell
.\.venv\Scripts\Activate.ps1
```

O interpretador do projeto é `.venv/Scripts/python.exe`. O `python` do PATH é
outra instalação e não tem as dependências.

## 2. Testes

### Backend

`unittest discover` **não funciona** a partir de `backend/`: os pacotes são
namespace packages (sem `__init__.py`). Use a lista explícita.

```bash
python -m unittest \
  backend.agentes.test_agente1_linter \
  backend.agentes.test_agente2_analista \
  backend.agentes.test_agente3_prescritor \
  backend.agentes.test_analisar_pgn_avulso \
  backend.agentes.test_consulta_ao_vivo \
  backend.agentes.test_explicador_posicao \
  backend.agentes.test_gerar_perguntas_pendentes \
  backend.agentes.test_gerar_resumo_partida \
  backend.agentes.test_insights_repertorio \
  backend.agentes.test_insights_puzzles \
  backend.agentes.test_medir_eficacia \
  backend.agentes.test_normalizar_aberturas \
  backend.agentes.test_popular_fila_treino_espacado \
  backend.agentes.test_refazer_trecho \
  backend.agentes.test_revisar_exercicio_avulso \
  backend.agentes.test_revisar_pensamento \
  backend.analise_engine.test_analisar_partidas \
  backend.analise_engine.test_backfill_fen_lances_criticos \
  backend.api.test_api_server \
  backend.common.test_chess_math \
  backend.common.test_cadencia \
  backend.common.test_lichess_explorer \
  backend.common.test_lichess_oauth \
  backend.common.test_notacao_pt \
  backend.common.test_progress \
  backend.common.test_settings \
  backend.common.test_spaced_repetition \
  backend.common.test_syzygy_tablebase \
  backend.common.test_tenant \
  backend.common.test_treino_trecho \
  backend.ingestao.test_backfill_pgn_lichess \
  backend.ingestao.test_backfill_tempos_chesscom \
  backend.ingestao.test_coletar_partidas \
  backend.ingestao.test_coletar_partidas_chesscom \
  backend.ingestao.test_common_ingestao \
  backend.ingestao.test_enriquecer_partidas_lichess \
  backend.ingestao.test_importar_puzzle_activity \
  backend.rag.test_importar_exercicios_taticos \
  backend.rag.test_importar_exercicios_posicionais \
  backend.rag.test_importar_indice_conceitual \
  backend.rag.test_processar_livro
```

Para gerar a lista automaticamente e não esquecer nenhum módulo:

```bash
python -m unittest $(find backend -name "test_*.py" | sed 's/\.py$//' | sed 's#/#.#g')
```

Ao criar um módulo de teste novo, registre-o **nesta lista acima** e em
`.github/workflows/deploy-backend.yml` (regra R8) — as duas são mantidas à mão,
e esquecer a do CI faz o teste nunca rodar lá. (`CLAUDE.md` não tem mais lista
de testes; a R8 aponta para cá.) Conferência rápida de que as duas batem:

```bash
find backend -name "test_*.py" | wc -l                          # módulos em disco
grep -cE "^\s+backend\..*test_" .github/workflows/deploy-backend.yml   # módulos no CI
```

O `-E "^\s+backend\..*test_"` é para não contar junto a linha do `paths:` no
topo do workflow, que também casa com `backend.`. Os dois números têm que ser
iguais.

### Frontend

```bash
cd frontend && npx ng test --no-watch
cd frontend && npx ng build          # valida template + tipos
```

## 3. Rodar a aplicação

```bash
uvicorn backend.api.api_server:app --reload --port 8000
cd frontend && npm start             # http://localhost:4200
```

O `ng serve` sobe em `[::1]:4200` (IPv6). `curl http://127.0.0.1:4200` falha com
exit 7 mesmo com o servidor no ar — use `http://localhost:4200`.

## 4. Pipeline em lote, na ordem

```bash
python backend/ingestao/coletar_partidas.py            # Lichess
python backend/ingestao/coletar_partidas_chesscom.py   # Chess.com
python backend/analise_engine/analisar_partidas.py     # Stockfish
python backend/agentes/agente1_linter.py               # diagnóstico por lance
python backend/agentes/popular_fila_treino_espacado.py # fila de repetição espaçada (D-48)
python backend/agentes/agente2_analista.py             # estatística + narrativa
python backend/agentes/agente3_prescritor.py           # sprint de treino
```

### Scripts que continuam manuais (fora dos workflows)

Precisam ser rodados à mão quando necessário:

```bash
python backend/ingestao/importar_anotacoes_lichess.py   # anotações de Lichess Study (precisa study:write)
python backend/ingestao/backfill_eco_abertura.py        # ECO faltante (execução única)
python backend/agentes/normalizar_aberturas.py          # abertura_normalizada (após novas levas de partidas)
python backend/rag/importar_exercicios_taticos.py       # catálogo de exercícios táticos (D-49) — baixa o dump do Lichess, ~1-2min
python backend/rag/importar_exercicios_posicionais.py   # catálogo posicional de partidas OTB (D-55) — broadcasts do Lichess, ~10min/mês
python backend/ingestao/backfill_cadencia.py            # preenche partidas.cadencia (D-57) do PGN já guardado; --todas recalcula
python backend/ingestao/backfill_pgn_lichess.py         # rebusca o PGN oficial no Lichess (D-62); --simular não grava, --todas refaz tudo
```

**Os dois backfills não são intercambiáveis.** `backfill_cadencia.py` lê o
`TimeControl` do PGN **já guardado** — resolve quando o PGN está completo e só
falta a coluna. `backfill_pgn_lichess.py` vai buscar o PGN na fonte — é o que
resolve quando o próprio PGN está pobre, que era o caso de 100% do acervo do
Lichess antes do D-62. Rode sempre o segundo **antes** do primeiro em partidas
do Lichess; depois dele, o primeiro não tem mais o que fazer ali.

Rode `--simular` antes de valer: ele imprime quantas partidas mudariam, a
distribuição de cadência resultante e quais seriam recusadas por divergência de
lances, sem tocar no banco.

O importador posicional lê o mês **inteiro** de broadcasts e amostra por
reservatório (D-58), então demora ~10 minutos por mês pedido. Vale a espera:
a versão anterior parava ao bater o teto e trazia tudo do mesmo punhado de
torneios dos primeiros dias.

Os scripts `importar_puzzle_activity.py`, `enriquecer_partidas_lichess.py`, `gerar_perguntas_pendentes.py` e `gerar_resumo_partida.py` foram automatizados no `pipeline-diario.yml`, e `medir_eficacia.py` no `pipeline-semanal.yml` (ver D-37 em `DECISOES.md`). `popular_fila_treino_espacado.py` também roda no `pipeline-diario.yml`, logo após `agente1_linter.py` (D-48). `importar_exercicios_taticos.py` (D-49) fica de fora de propósito: importa conteúdo de referência estático (o catálogo de puzzles do Lichess não muda dia a dia), não dado de usuário — rodar de novo só acrescenta puzzles novos ou amplia a faixa de rating, sem necessidade de agenda diária. `importar_exercicios_posicionais.py` (D-55) fica de fora pelo mesmo motivo, com uma diferença: o default dele é o último mês completo de broadcasts, calculado na hora, então rodar de novo daqui a alguns meses traz partidas novas sem precisar editar nada.

## 5. Processar um livro novo no RAG

```bash
# 1. coloque o PDF em backend/rag/livros_pdf/
# 2. preview primeiro (não gasta API, mostra a estrutura de capítulos)
python backend/rag/processar_livro.py --pdf "backend/rag/livros_pdf/NOME.pdf" --nome "Nome do Livro" --preview
#    PDF escaneado (texto vazio no preview) → acrescente --forcar-ocr
# 3. se o preview estiver bom, rode sem --preview (gera chunks e embeddings no Supabase)
# 4. gere as sugestões de conceitos com o Gemini:
python backend/rag/sugerir_indice_conceitual.py --livro "Nome do Livro"
# 5. importe as sugestões para a tabela indice_conceitual no Supabase:
python backend/rag/importar_indice_conceitual.py --json backend/rag/sugestoes/Nome_do_Livro.json [--substituir]
```

Confira sempre antes de considerar pronto:

```sql
select capitulo, count(*), min(pagina_aprox), max(pagina_aprox)
from livros_chunks where livro = '...' group by capitulo;
```

Se a paginação não variar, ou um capítulo "gigante" absorver os outros, o
chunking saiu errado e o RAG vai citar página errada.

## 6. Automação (GitHub Actions)

| Workflow | Agenda (UTC) | O que roda |
|---|---|---|
| `pipeline-diario.yml` | `0 9 * * *` | coleta Lichess + Chess.com, puzzles, enriquecimento Lichess, Stockfish, Agente 1, fila de treino espaçado (D-48), perguntas pendentes, resumos |
| `pipeline-semanal.yml` | `0 10 * * 1` | medir eficácia de treinos, Agente 2, Agente 3 |
| `deploy-backend.yml` | push na `main` em `backend/**` ou `Dockerfile` | testes, build, deploy no Cloud Run |

Execução manual: GitHub → aba **Actions** → workflow → **Run workflow**.
Para investigar uma execução, abra os steps e baixe o artifact de logs no rodapé.

## 7. Variáveis de ambiente

Nomes apenas; valores ficam em `.env` (local) e `env.yaml` (Cloud Run), nunca
commitados.

`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`,
`LICHESS_USERNAME`, `LICHESS_TOKEN`, `LICHESS_STUDY_TOKEN`,
`LICHESS_GAMES_LIMIT`, `CHESSCOM_USERNAME`, `CHESSCOM_MONTHS_LIMIT`,
`YOUTUBE_API_KEY`, `STOCKFISH_PATH`,
`ALLOWED_ORIGINS`, `EXERCICIO_AVULSO_SEARCHTIME_MS`, `DEFAULT_USER_ID`,
`LIMITE_DIARIO_ANALISAR_PGN`, `LIMITE_DIARIO_EXPLICAR_POSICAO`,
`LIMITE_DIARIO_REVISAR_AVULSO`, `LIMITE_DIARIO_RECONHECER_POSICAO`,
`LIMITE_DIARIO_REPROCESSAR`, `LIMITE_DIARIO_TREINO_RESPONDER`,
`LIMITE_DIARIO_TREINO_TRECHO`, `LIMITE_DIARIO_CONSULTA_AO_VIVO`,
`CONSULTA_AO_VIVO_USUARIOS`, `CONSULTA_MAX_POR_PARTIDA`,
`LIMITE_DIARIO_IMPORTAR_PARTIDAS`, `IMPORTACAO_MAX_PARTIDAS`,
`LICHESS_OAUTH_CLIENT_ID`, `LICHESS_OAUTH_REDIRECT_URI`,
`LICHESS_OAUTH_SCOPES`, `FRONTEND_URL`, `TREINO_NOVOS_POR_DIA`,
`TREINO_FOCO_QTD_EXERCICIOS`, `EXERCICIO_RATING_MIN`, `EXERCICIO_RATING_MAX`,
`EXERCICIO_POPULARIDADE_MIN`, `EXERCICIOS_POR_CATEGORIA`,
`SESSAO_QTD_EXERCICIOS`, `TREINO_TETO_FILA`, `TREINO_HORIZONTE_DIAS`,
`TREINO_TRECHOS_POR_DIA`,
`PERGUNTA_VALIDADE_DIAS`, `POSICIONAL_MESES`,
`POSICIONAL_EVAL_MAX_CP`, `POSICIONAL_QUEDA_MIN_CP`,
`POSICIONAL_SEGUNDOS_PRESSAO`, `POSICIONAL_PECAS_FINAL`,
`POSICIONAL_POR_CATEGORIA`, `POSICIONAL_EXIGIR_TITULO`.

**Ajuste fino do motor, do OCR e da coleta.** Todas opcionais, com default no
código, e nenhuma delas é segredo — ficaram fora da lista acima até a revisão
de documentação de 16/09/2026, embora o código as leia desde sempre:

| Variável | Onde é lida | Para que serve |
|---|---|---|
| `STOCKFISH_DEPTH` | `analisar_partidas.py`, `gerar_resumo_partida.py`, `revisar_pensamento.py` | profundidade da análise (é o que exige `--memory 2Gi` no Cloud Run, regra R10) |
| `STOCKFISH_SEARCHTIME_MS` | `analisar_partidas.py`, `explicador_posicao.py`, `revisar_exercicio_avulso.py`, `revisar_pensamento.py` | teto de tempo por posição, alternativa à profundidade |
| `WINDOW_SIZE_EROSAO` | `analisar_partidas.py` | tamanho da janela de lances que define um evento `EROSAO` |
| `LIMIAR_APURO_TEMPO_SEG` | `agente1_linter.py`, `gerar_resumo_partida.py` | abaixo de quantos segundos no relógio o erro conta como apuro de tempo (é o que alimenta a tag `gestao_de_tempo_ruim`) |
| `GEMINI_RATE_LIMIT_SLEEP_SEC` | `agente1_linter.py` | pausa entre chamadas para não bater no rate limit da API |
| `CHESSCOM_USER_AGENT` | `coletar_partidas_chesscom.py` | User-Agent identificável que a API do Chess.com pede; tem default no código, então só mexa se a coleta começar a tomar 403 |
| `TESSERACT_PATH` / `POPPLER_PATH` | `processar_livro.py` | binários de OCR e de rasterização de PDF; só importam na máquina que processa livro, não em produção |

**OAuth do Lichess (D-33).** As 4 últimas são opcionais, com default no código.
Nenhuma delas é segredo: o Lichess usa cliente público, sem `client_secret` e
sem registro prévio — `LICHESS_OAUTH_CLIENT_ID` é só uma string de
identificação (default `chess-ai-pipeline`). A que realmente importa mudar por
ambiente é `LICHESS_OAUTH_REDIRECT_URI` (default
`http://localhost:8000/lichess/oauth/callback`): ela precisa bater **exatamente**
entre a autorização e a troca do código, então em produção tem que apontar para
a URL pública do Cloud Run. `LICHESS_OAUTH_SCOPES` (default `puzzle:read`) só
vale para conexões novas — token já emitido carrega os escopos que foram
pedidos na hora, então ampliar a lista exige reconectar as contas.
`FRONTEND_URL` (default: a primeira entrada de `ALLOWED_ORIGINS`) é para onde o
callback devolve o navegador.

**Limite diário por usuário nas rotas caras (D-32; auditoria pós-D-49).** As
variáveis `LIMITE_DIARIO_*` acima são opcionais — cada uma tem um default no
código (`LIMITES_DIARIOS_ENV` em `api_server.py`: 20/50/50/30/20 para as
rotas caras de Stockfish+Gemini, e 200 só para `treino-responder`, que só usa
Stockfish) e só precisam ir no `.env`/secret quando o valor precisar mudar
sem novo deploy de código. `/analisar-pgn`, `/explicar-posicao`,
`/revisar-avulso`, `/reconhecer-posicao`, `/partidas/{id}/reprocessar` e
`/treino/{id}/responder` dependem de `limite_diario(rota)`, que incrementa
`uso_diario_usuario` via RPC (`incrementar_uso_diario`, atômico, dia
calculado em `America/Sao_Paulo`) ANTES do corpo da rota, e barra com 429
quando a contagem do dia supera o limite — ver BANCO.md e D-32 em
`DECISOES.md`. `/reprocessar` e `/treino/{id}/responder` tinham ficado de
fora do D-32/D-48 originais por descuido — corrigido numa auditoria de
segurança/operação (achado documentado, ver `DECISOES.md`).

**Fila de treino diário (D-48).** `TREINO_NOVOS_POR_DIA` (default 10) limita
quantos cards NOVOS `popular_fila_treino_espacado.py` introduz "hoje" por
usuário a cada execução — o resto do backlog (típico na primeira execução,
com meses de diagnósticos acumulados) é escalonado nos dias seguintes, para
não despejar centenas de cards de uma vez na tela `/treino`.

**Catálogo de exercícios táticos e treino focado (D-49).**
`TREINO_FOCO_QTD_EXERCICIOS` (default 8) é quantos exercícios entram na fila
de uma vez quando o usuário clica "Focar" numa categoria
(`POST /treino/foco/{categoria}`). As outras 4 controlam o import ocasional
de `backend/rag/importar_exercicios_taticos.py`: `EXERCICIO_RATING_MIN`/
`EXERCICIO_RATING_MAX` (default 1000/2200) filtram a faixa de dificuldade dos
puzzles aceitos, `EXERCICIO_POPULARIDADE_MIN` (default 50) evita puzzles
obscuros/mal avaliados no Lichess, e `EXERCICIOS_POR_CATEGORIA` (default 300)
é o teto de exercícios importados por categoria — o script para de ler o
dump assim que todas as categorias com tema mapeado batem o teto.

**Catálogo posicional de partidas OTB (D-55).** Controlam
`backend/rag/importar_exercicios_posicionais.py`, que lê os broadcasts do
Lichess (partidas reais de torneio) e extrai posições onde o melhor lance é
quieto — o material que ESTRATEGIA e GESTAO_DE_TEMPO não tinham (P-15).
`POSICIONAL_MESES` (default: o último mês completo, calculado) é a lista de
meses `YYYY-MM` a baixar, separados por vírgula. `POSICIONAL_EVAL_MAX_CP`
(default 300) descarta posições já decididas, `POSICIONAL_QUEDA_MIN_CP`
(default 150) exige que o erro tenha custado caro, `POSICIONAL_PECAS_FINAL`
(default 4) é o corte que classifica a posição como final,
`POSICIONAL_SEGUNDOS_PRESSAO` (default 120) é o relógio abaixo do qual o erro
vira GESTAO_DE_TEMPO, `POSICIONAL_POR_CATEGORIA` (default 300) é o teto por
categoria, e `POSICIONAL_EXIGIR_TITULO` (default ligado; `0` desliga) limita
às partidas com pelo menos um jogador titulado. **Desligar esse último enche
o catálogo de opens juvenis** — foi o que aconteceu na primeira execução
real, antes do filtro existir.

`SESSAO_QTD_EXERCICIOS` (default 12, D-54) é quantos exercícios entram no
bloco de prática ao iniciar uma sessão de treino focado — maior que o
`TREINO_FOCO_QTD_EXERCICIOS` do "Focar" avulso de propósito: a sessão é o
formato longo, com começo e fim.

**Importação sob demanda (D-65).** `IMPORTACAO_MAX_PARTIDAS` (default 10) é
quantas partidas `POST /perfis/importar` analisa por execução — o número que
governa o custo do onboarding, já que cada partida custa Stockfish mais uma
chamada de Gemini por lance crítico. `LIMITE_DIARIO_IMPORTAR_PARTIDAS`
(default 3) é o menor teto de `LIMITES_DIARIOS_ENV`: a rota serve ao
onboarding, não ao uso repetido. A importação **não** gera resumo por partida,
de propósito — é a etapa mais cara em Gemini e a menos urgente; o pipeline
diário a faz depois.

**Atenção ao token do Lichess.** A API de partidas responde **404 sem
`Authorization`** (verificado em 17/09/2026), e o Cloud Run não recebe
`LICHESS_TOKEN` — o `deploy-backend.yml` manda só 4 variáveis (D-20). Por isso
a importação usa o token **OAuth do próprio usuário**; quem não conectou a
conta do Lichess importa só do Chess.com, e a resposta diz isso.

**Válvula da fila (D-64).** `TREINO_HORIZONTE_DIAS` (default 60) é até quantos
dias à frente `popular_fila_treino_espacado.py` pode agendar material NOVO.
Junto com a regra de que card novo entra no **fim** da fila (nunca disputa o
dia com o que já está atrasado), é o que impede a fila de crescer no ritmo da
ingestão em vez do consumo. Material além do horizonte não se perde: volta a
ser candidato na execução seguinte, quando a fila drenar. No log isso aparece
como `fila cheia até <data>; material novo aguarda a fila drenar`.

**Cota dos trechos (D-66).** `TREINO_TRECHOS_POR_DIA` (default 2) é quantos
cards de EROSAO ("Refazer o trecho") cabem num mesmo dia da fila. Um card de
PICO é uma decisão; um de erosão são 8 lances do jogador, cada um com a
resposta do motor — umas oito vezes o trabalho. Sem cota própria, uma sequência
de erosões na ordem de chegada faria um dia valer oito vezes outro. O resto do
dia é completado com picos, até `TREINO_NOVOS_POR_DIA`. Em `0`, os eventos de
erosão simplesmente não são enfileirados (é o desligador do recurso sem
precisar de deploy) e continuam candidatos para quando a configuração mudar.

`LIMITE_DIARIO_TREINO_TRECHO` (default 400) é o teto diário de
`POST /treino/{id}/trecho`. Bem mais alto que o de `/responder` porque um único
card de trecho gasta 8 requisições; contá-lo na mesma cota faria um trecho
parecer 8 revisões. Continua sendo freio de abuso contra o `engine_lock` (R3),
não do uso normal.

**Consulta ao vivo (D-67).** `CONSULTA_AO_VIVO_USUARIOS` é a lista, separada
por vírgula, dos `auth.users.id` que podem usar a feature — hoje, só as duas
contas do dono do projeto. **Fecha por padrão**: ausente ou vazia, ninguém
acessa. Em produção ela vem da **Variable** (não Secret) de mesmo nome do
repositório, lida pelo `deploy-backend.yml`; é Variable porque são ids, não
credenciais, e um Secret mascararia os dígitos nos logs (o problema da C4).
Para liberar ou retirar alguém: `gh variable set CONSULTA_AO_VIVO_USUARIOS
--body "<id1>,<id2>"` e um novo deploy. Localmente, exporte a variável antes do
`uvicorn`. `CONSULTA_MAX_POR_PARTIDA` (default 3) é o teto de consultas por
partida espelhada — o freio de uso, que obriga a escolher os momentos de dúvida.
`LIMITE_DIARIO_CONSULTA_AO_VIVO` (default 15) é o freio de gasto do dia: cada
consulta é Stockfish mais uma chamada ao Gemini (duas no pior caso).

**Validade das perguntas pendentes (D-64).** `PERGUNTA_VALIDADE_DIAS`
(default 14) governa as duas pontas de `gerar_perguntas_pendentes.py`: não
gerar pergunta para partida mais velha que isso, e marcar como `EXPIRADA` as
pendentes que passaram do prazo. A régua é a data da **partida**, não a da
pergunta — o que decide é o jogador ainda lembrar do lance. Nada é apagado;
`EXPIRADA` preserva o registro de que a pergunta existiu e não foi respondida.

`TREINO_TETO_FILA` (default 20, D-56) é quantos cards `GET /treino/fila`
mostra de uma vez. O teto corta a EXIBIÇÃO, nunca o agendamento: os cortados
continuam vencidos e aparecem conforme os outros são respondidos, e o campo
`vencidos_total` da resposta continua dizendo o tamanho real do atraso.
`0` desliga o teto.

`API_SECRET_KEYS`/`API_SECRET_KEY` (o antigo esquema de header `X-API-Key`,
aposentado como gate de acesso desde D-25) foram **removidas de vez** numa
auditoria pós-D-49: nenhuma rota dependia mais delas, mas o servidor ainda
recusava subir sem a variável configurada — um risco de disponibilidade
amarrado a uma feature morta. Se você tinha isso configurado localmente ou no
GitHub Secrets, pode remover com segurança; o servidor não lê mais essa
variável.

`DEFAULT_USER_ID` é **obrigatória**: é o dono gravado em `user_id` nas 6
tabelas raiz (ver D-14 em `DECISOES.md`). Sem ela, toda escrita nessas tabelas
falha com `ValueError` — de propósito, para o erro aparecer na hora em vez de
gravar linha órfã. Depois de D-25 ela vale **só para os scripts de CLI
standalone**: nos endpoints da API o dono vem sempre da sessão, sem fallback.
Por isso ela **não** entra na limpeza citada acima.

`LICHESS_USERNAME`/`CHESSCOM_USERNAME` **não controlam mais a coleta em lote**
desde D-28: `coletar_partidas.py`/`coletar_partidas_chesscom.py` passaram a
percorrer a tabela `perfis_usuario` (um usuário, uma conta cadastrada, uma
rodada de coleta atribuída ao `user_id` certo — ver BANCO.md). Desde D-31,
`enriquecer_partidas_lichess.py` também percorre `perfis_usuario` e não lê
mais `LICHESS_USERNAME`. As duas variáveis continuam valendo **só** para
quem roda `analisar_pgn_avulso.py` direto no terminal (CLI standalone): é o
fallback de inferência de cor `inferir_cor_jogador` usa quando não recebe
`usernames` explícito. Pela API, `/analisar-pgn` já passa o perfil de quem
está logado, sem tocar nessas variáveis.

`LICHESS_STUDY_TOKEN` **não é mais lido por `importar_puzzle_activity.py`**
desde D-34 (Estágio 2 do OAuth do Lichess, D-33): o script agora percorre a tabela
`lichess_oauth_tokens`, usando o token OAuth de cada usuário conectado para
importar seus puzzles de forma isolada. A variável `LICHESS_STUDY_TOKEN` continua
no `.env` exclusivamente para `importar_anotacoes_lichess.py`, que requer o escopo
OAuth `study:write` (ainda não migrado).

**`deploy-backend.yml` é a fonte de verdade em produção, não `env.yaml`
local (D-20).** A cada deploy automático, o workflow gera um arquivo de env
vars a partir dos secrets do repositório (`SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`,
`DEFAULT_USER_ID`) e sobe o Cloud Run com `--env-vars-file`, que **substitui
por completo** as env vars do serviço — nada fica órfão de um deploy manual
antigo. `env.yaml` local ainda existe só como referência de quais nomes
importam e para rodar `gcloud run deploy` manualmente se precisar; editar só
ele, sem também atualizar o secret correspondente no GitHub, não tem efeito
nenhum no próximo deploy automático. `STOCKFISH_PATH` fica de fora dessa
lista de propósito: vem gravado na imagem Docker (`ENV` no `Dockerfile`), não
depende de nenhum secret.

Secrets do GitHub Actions: os mesmos acima (exceto `STOCKFISH_PATH`, que não
é secret) mais `GCP_SA_KEY`.

## 8. Ferramentas de verificação local (D-53)

Duas ferramentas para exercitar a aplicação de verdade, em vez de só rodar
teste unitário. O procedimento completo está em `docs/ESTADO.md` §6.

| Comando | O que faz |
|---|---|
| `python backend/common/gerar_sessao_local.py <email> [saida.json]` | Emite uma sessão real do Supabase Auth via magic link (Admin API), sem precisar da senha. Sem argumento de saída, imprime só o `access_token` — útil para `curl -H "Authorization: Bearer ..."`. **O token é credencial válida: não cole em log, issue nem commit.** |
| `cd frontend && npm run telas -- <sessao.json> [pasta]` | Fotografa as 7 telas de lista fixa em 1440px e 390px, com a sessão injetada. Requer `npx playwright install chromium` na primeira vez, e os dois servidores no ar. |

Duas variáveis opcionais do `capturar-telas.mjs` (D-54):

- **`ROTAS_EXTRA`** acrescenta rotas à lista fixa, no formato
  `"/caminho:nome-do-arquivo"`, separadas por vírgula. Existe porque rota com
  parâmetro não cabe numa lista fixa — o id muda a cada execução. Para
  fotografar a tela de sessão:
  `ROTAS_EXTRA="/sessao/<uuid-real>:sessao" npm run telas -- ../sessao.json ../telas`
- **`ESPERA_MS`** (default 4500) é quanto esperar a tela assentar antes do
  clique do obturador. As telas buscam dado da API ao entrar; baixar esse
  valor rende um álbum de esqueletos de carregamento.

`npm run telas` é captura, não teste: não afirma nada sobre o que fotografou e
não roda em CI. Serve para alguém olhar — foi assim que apareceram o markdown
cru na narrativa e as métricas coladas ("0FEITAS HOJE"), ambos com a suíte
inteira verde.

## 9. Troubleshooting — erros já vistos neste projeto

| Sintoma | Causa | Correção |
|---|---|---|
| `PGRST125: Invalid path` | `SUPABASE_URL` terminando em `/rest/v1/` | remova o sufixo (regra R6) |
| `PGRST204` após criar coluna | schema cache do PostgREST desatualizado | `NOTIFY pgrst, 'reload schema';` (regra R5) |
| `SemLock created in a fork context…` | `multiprocessing.Queue()` global misturado com `Process` de contexto spawn | um único `ctx` spawn para os dois (regra R4) |
| Análise trava sem erro e sem timeout | duas chamadas concorrentes no mesmo subprocesso do Stockfish | `engine_lock` (regra R3) |
| Partida órfã em `processando`, container reiniciado | OOM do Stockfish em depth 16 | `--memory 2Gi` no Cloud Run (regra R10) |
| Background task congela após o HTTP 202 | CPU throttling do Cloud Run | `--no-cpu-throttling` (regra R10) |
| `UnicodeEncodeError` com emoji no PowerShell | console em `cp1252` | `configurar_encoding_utf8()` de `backend/common/progress.py`, no topo do script |
| Script diz "0 processados, 0 falhas" sem motivo | variável de ambiente ausente ou errada | rode na mão para ver o erro real |
| Sprint cita sempre o mesmo livro | `indice_conceitual` só tem esse livro para a categoria | `select livro from indice_conceitual where conceito ilike '%tema%'` |
| Números virando `***` no log do Actions | secret numérico curto mascarando dígitos coincidentes | mova o valor de Secret para Variable |
| `ng build` avisa que o bundle passou de 500 kB | orçamento padrão do Angular | conhecido e aceito; não é regressão |
| `ValueError: Variável de ambiente ausente: DEFAULT_USER_ID` | escrita numa das 6 tabelas raiz sem a variável definida | defina `DEFAULT_USER_ID` no `.env`/`env.yaml`/secret do Actions (D-14) |
| `null value in column "user_id" violates not-null constraint` | caminho de escrita novo numa tabela raiz esqueceu o `user_id` | acrescente `obter_default_user_id()` ao payload (ver os 7 pontos em D-14) |
| `OPTIONS ... 400 Bad Request` rodando `ng serve` numa porta diferente de 4200 | origem não está em `ALLOWED_ORIGINS` do backend local (default só libera `localhost:4200`) | suba o `uvicorn` com `ALLOWED_ORIGINS="http://localhost:SUA_PORTA,http://localhost:4200"` |
| `401` em toda chamada à API, mesmo com `X-API-Key` correta | esperado desde D-25: a chave foi aposentada como gate; só `Authorization: Bearer` da sessão abre a API | faça login; para testar por `curl`, pegue um `access_token` via `POST /auth/v1/token?grant_type=password` no Supabase |
| `401` só depois de um tempo usando a aplicação | sessão expirou no meio do uso (o `authGuard` só checa na navegação) | entre de novo; a tela mostra "Sua sessão expirou" (D-25) |
| Produção usando um valor de env var diferente do `env.yaml` local | `env.yaml` foi editado mas o secret correspondente no GitHub não — o deploy automático lê dos Secrets, não do arquivo local | atualize o secret em Settings > Secrets and variables > Actions e rode o deploy de novo (D-20) |
| `429 RESOURCE_EXHAUSTED … exceeded its monthly spending cap` em toda chamada ao Gemini; narrativa do hexágono vazia; Agente 1 com "0 processados, N falhas" | teto mensal de gastos do projeto Google estourado (17/09/2026, depois de a recuperação do D-61 processar 29 partidas acumuladas num dia) | subir o teto em https://ai.studio/spend ou esperar o ciclo virar; depois rodar `agente1_linter.py` e `agente2_analista.py` à mão para o que ficou para trás. Stockfish e estatística não param; o pipeline diário falha no Agente 1 e abre a issue `falha-automacao` |
