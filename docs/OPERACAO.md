---
doc: OPERACAO.md
escopo: comandos, execução de scripts, automação, variáveis de ambiente, troubleshooting
nao_contem: arquitetura (ver ARQUITETURA.md), schema (ver BANCO.md), estado (ver ESTADO.md)
verificado_em: 2026-09-11
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
  backend.agentes.test_agente3_prescritor \
  backend.agentes.test_analisar_pgn_avulso \
  backend.agentes.test_explicador_posicao \
  backend.agentes.test_gerar_perguntas_pendentes \
  backend.agentes.test_gerar_resumo_partida \
  backend.agentes.test_revisar_exercicio_avulso \
  backend.agentes.test_revisar_pensamento \
  backend.analise_engine.test_analisar_partidas \
  backend.api.test_api_server \
  backend.common.test_chess_math \
  backend.common.test_notacao_pt
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

### Scripts que existem mas não estão em nenhum workflow

Precisam ser rodados à mão hoje:

```bash
python backend/ingestao/enriquecer_partidas_lichess.py  # precisão por fase + relógio
python backend/ingestao/importar_puzzle_activity.py     # histórico de puzzles
python backend/ingestao/importar_anotacoes_lichess.py   # anotações de Lichess Study
python backend/agentes/gerar_resumo_partida.py          # narrativa por partida
python backend/agentes/gerar_perguntas_pendentes.py     # perguntas retroativas
python backend/agentes/medir_eficacia.py                # fecha o loop adaptativo
python backend/ingestao/backfill_eco_abertura.py        # ECO faltante (execução única)
```

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
| `pipeline-diario.yml` | `0 9 * * *` | coleta Lichess + Chess.com, Stockfish, Agente 1 |
| `pipeline-semanal.yml` | `0 10 * * 1` | Agente 2, Agente 3 |
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
`ALLOWED_ORIGINS`, `EXERCICIO_AVULSO_SEARCHTIME_MS`.

`API_SECRET_KEYS` usa o formato `nome:chave,nome:chave` e convive com a
`API_SECRET_KEY` antiga (chave única) por compatibilidade.

Secrets do GitHub Actions: os mesmos acima mais `GCP_SA_KEY`.

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
