---
doc: OPERACAO.md
escopo: comandos, execução de scripts, automação, variáveis de ambiente, troubleshooting
nao_contem: arquitetura (ver ARQUITETURA.md), schema (ver BANCO.md), estado (ver ESTADO.md)
verificado_em: 2026-09-13
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
  backend.agentes.test_explicador_posicao \
  backend.agentes.test_gerar_perguntas_pendentes \
  backend.agentes.test_gerar_resumo_partida \
  backend.agentes.test_insights_repertorio \
  backend.agentes.test_insights_puzzles \
  backend.agentes.test_medir_eficacia \
  backend.agentes.test_normalizar_aberturas \
  backend.agentes.test_revisar_exercicio_avulso \
  backend.agentes.test_revisar_pensamento \
  backend.analise_engine.test_analisar_partidas \
  backend.analise_engine.test_backfill_fen_lances_criticos \
  backend.api.test_api_server \
  backend.common.test_chess_math \
  backend.common.test_lichess_explorer \
  backend.common.test_lichess_oauth \
  backend.common.test_notacao_pt \
  backend.common.test_syzygy_tablebase \
  backend.common.test_tenant \
  backend.ingestao.test_coletar_partidas \
  backend.ingestao.test_coletar_partidas_chesscom \
  backend.ingestao.test_common_ingestao \
  backend.ingestao.test_enriquecer_partidas_lichess \
  backend.ingestao.test_importar_puzzle_activity
```

Para gerar a lista automaticamente e não esquecer nenhum módulo:

```bash
python -m unittest $(find backend -name "test_*.py" | sed 's/\.py$//' | sed 's#/#.#g')
```

Ao criar um módulo de teste novo, registre-o também em `CLAUDE.md` e em
`.github/workflows/deploy-backend.yml` (regra R8) — a lista do CI é mantida à mão.

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
python backend/agentes/agente2_analista.py             # estatística + narrativa
python backend/agentes/agente3_prescritor.py           # sprint de treino
```

### Scripts que continuam manuais (fora dos workflows)

Precisam ser rodados à mão quando necessário:

```bash
python backend/ingestao/importar_anotacoes_lichess.py   # anotações de Lichess Study (precisa study:write)
python backend/ingestao/backfill_eco_abertura.py        # ECO faltante (execução única)
python backend/agentes/normalizar_aberturas.py          # abertura_normalizada (após novas levas de partidas)
```

Os scripts `importar_puzzle_activity.py`, `enriquecer_partidas_lichess.py`, `gerar_perguntas_pendentes.py` e `gerar_resumo_partida.py` foram automatizados no `pipeline-diario.yml`, e `medir_eficacia.py` no `pipeline-semanal.yml` (ver D-37 em `DECISOES.md`).

## 5. Processar um livro novo no RAG

```bash
# 1. coloque o PDF em backend/rag/livros_pdf/
# 2. preview primeiro (não gasta API, mostra a estrutura de capítulos)
python backend/rag/processar_livro.py --pdf "backend/rag/livros_pdf/NOME.pdf" --nome "Nome do Livro" --preview
#    PDF escaneado (texto vazio no preview) → acrescente --forcar-ocr
# 3. se o preview estiver bom, rode sem --preview
# 4. popule indice_conceitual por SQL, usando os nomes de capítulo EXATOS do preview
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
| `pipeline-diario.yml` | `0 9 * * *` | coleta Lichess + Chess.com, puzzles, enriquecimento Lichess, Stockfish, Agente 1, perguntas pendentes, resumos |
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
`YOUTUBE_API_KEY`, `STOCKFISH_PATH`, `API_SECRET_KEY`, `API_SECRET_KEYS`,
`ALLOWED_ORIGINS`, `EXERCICIO_AVULSO_SEARCHTIME_MS`, `DEFAULT_USER_ID`,
`LIMITE_DIARIO_ANALISAR_PGN`, `LIMITE_DIARIO_EXPLICAR_POSICAO`,
`LIMITE_DIARIO_REVISAR_AVULSO`, `LIMITE_DIARIO_RECONHECER_POSICAO`,
`LICHESS_OAUTH_CLIENT_ID`, `LICHESS_OAUTH_REDIRECT_URI`,
`LICHESS_OAUTH_SCOPES`, `FRONTEND_URL`.

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

**Limite diário por usuário nas rotas caras (D-32).** As 4 variáveis
`LIMITE_DIARIO_*` acima são opcionais — cada uma tem um default no código
(`LIMITES_DIARIOS_ENV` em `api_server.py`: 20/50/50/30, na ordem listada) e só
precisam ir no `.env`/secret quando o valor precisar mudar sem novo deploy de
código. `/analisar-pgn`, `/explicar-posicao`, `/revisar-avulso` e
`/reconhecer-posicao` passaram a depender de `limite_diario(rota)`, que
incrementa `uso_diario_usuario` via RPC (`incrementar_uso_diario`, atômico,
dia calculado em `America/Sao_Paulo`) ANTES do corpo da rota, e barra com 429
quando a contagem do dia supera o limite — ver BANCO.md e D-32 em
`DECISOES.md`.

`API_SECRET_KEYS` usa o formato `nome:chave,nome:chave` e convive com a
`API_SECRET_KEY` antiga (chave única) por compatibilidade. **Desde D-25 as
duas não controlam mais acesso nenhum**: o gate da API é o
`Authorization: Bearer` da sessão do Supabase Auth. Elas continuam sendo lidas
no startup (o servidor ainda aborta sem elas) só porque a limpeza foi
deliberadamente adiada — ver a pendência em `ESTADO.md`.

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
`SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, `API_SECRET_KEYS`,
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

## 8. Troubleshooting — erros já vistos neste projeto

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
