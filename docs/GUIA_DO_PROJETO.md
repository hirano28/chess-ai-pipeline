# Guia Prático — Pipeline de Xadrez com IA

Referência rápida para não se perder entre os scripts, agentes e automações. Guarde este arquivo na raiz do repositório.

---

## 1. Visão geral em uma frase

Suas partidas de xadrez são coletadas automaticamente → analisadas pelo Stockfish → diagnosticadas por IA → agregadas estatisticamente → viram sprints de treino citando livros reais → tudo visível num dashboard.

---

## 2. Onde as coisas rodam

| Onde | O quê | Frequência |
|---|---|---|
| **GitHub Actions (automático)** | Coleta de partidas, Stockfish, Agente 1 (diário) · Agente 2, Agente 3 (semanal) | Diário 06h / Semanal segunda 07h (horário de Brasília) |
| **Seu computador (manual)** | Processar livros novos (RAG), backfills, debugging | Sob demanda |
| **Dashboard (Angular)** | Visualização | `ng serve` na pasta `frontend/`, acesse `localhost:4200` |

**Na prática:** no dia a dia, você não precisa rodar quase nada manualmente — a automação cuida da coleta e diagnóstico. Você só entra em ação para: processar um livro novo, estudar as sprints, jogar mais partidas, e marcar sessões como concluídas no dashboard.

---

## 3. Estrutura de pastas

```
chess-ai-pipeline/
├── backend/
│   ├── ingestao/          → coleta partidas (Lichess, Chess.com)
│   ├── analise_engine/    → roda Stockfish
│   ├── agentes/           → Agente 1 (linter), Agente 2 (analista), Agente 3 (prescritor), medir_eficacia
│   ├── rag/               → processamento de livros (OCR, chunking, embeddings)
│   │   └── livros_pdf/    → PDFs dos livros (não versionado no Git)
│   ├── db/                → scripts SQL (RPCs, tabelas auxiliares)
│   ├── common/            → utilidades compartilhadas (progress.py)
│   └── logs/              → logs de execução (não versionado)
├── frontend/              → dashboard Angular
├── .github/workflows/     → automação (pipeline-diario.yml, pipeline-semanal.yml)
└── .env                   → suas credenciais (NUNCA commitar)
```

---

## 4. Tabelas do banco (Supabase) — o que cada uma guarda

| Tabela | Conteúdo |
|---|---|
| `partidas` | Toda partida coletada (Lichess + Chess.com), com resultado, cor, ratings, ECO |
| `lances_criticos` | Os piores lances de cada partida, identificados pelo Stockfish |
| `diagnosticos` | O diagnóstico do Agente 1 para cada lance crítico (tags, causa raiz, sugestão) |
| `analises_hexagono` | O resultado do Agente 2: estatística agregada + narrativa + gargalo atual |
| `sessoes_treino` | As sprints geradas pelo Agente 3, com módulos e status de conclusão |
| `livros_chunks` | Trechos dos livros processados, com embeddings para busca RAG |
| `indice_conceitual` | Mapa manual: conceito → livro → capítulo/página |

---

## 5. Comandos manuais — quando usar cada um

Sempre ative o ambiente virtual antes: `.\.venv\Scripts\Activate.ps1`

### 5.1 — Processar um livro novo (RAG)

```powershell
# 1. Coloque o PDF em backend/rag/livros_pdf/

# 2. Teste primeiro em modo preview (não gasta API, mostra estrutura de capítulos)
python backend/rag/processar_livro.py --pdf "backend/rag/livros_pdf/NOME.pdf" --nome "Nome do Livro" --preview

# Se o PDF for escaneado (texto vazio no preview), adicione --forcar-ocr:
python backend/rag/processar_livro.py --pdf "backend/rag/livros_pdf/NOME.pdf" --nome "Nome do Livro" --forcar-ocr --preview

# 3. Se o preview parecer bom, rode de verdade (sem --preview)
python backend/rag/processar_livro.py --pdf "backend/rag/livros_pdf/NOME.pdf" --nome "Nome do Livro" [--forcar-ocr]

# 4. Depois, popule manualmente o indice_conceitual via SQL no Supabase,
#    usando os nomes de capítulo EXATOS que apareceram no preview/resultado.
```

⚠️ **Sempre confira antes**: `select capitulo, count(*), min(pagina_aprox), max(pagina_aprox) from livros_chunks where livro = '...' group by capitulo` — para garantir que a paginação varia corretamente e não há capítulo "gigante" absorvendo outros.

### 5.2 — Rodar o pipeline manualmente (equivalente ao que a automação faz)

```powershell
python backend/ingestao/coletar_partidas.py           # Lichess
python backend/ingestao/coletar_partidas_chesscom.py   # Chess.com
python backend/analise_engine/analisar_partidas.py     # Stockfish
python backend/agentes/agente1_linter.py               # Diagnóstico por lance
python backend/agentes/agente2_analista.py             # Estatística + narrativa
python backend/agentes/agente3_prescritor.py           # Gera sprint de treino
python backend/agentes/medir_eficacia.py               # Mede se sprints concluídas funcionaram
```

**Quando rodar manualmente:** só se quiser forçar uma atualização fora do horário da automação, ou para debugar algo. No dia a dia, isso já roda sozinho.

### 5.3 — Backfill (execução única, não recorrente)

```powershell
python backend/ingestao/backfill_eco_abertura.py   # preenche ECO faltante em partidas antigas
```

---

## 6. Automação (GitHub Actions)

- **`pipeline-diario.yml`** (todo dia, ~06h Brasília): coleta partidas novas + Stockfish + Agente 1.
- **`pipeline-semanal.yml`** (segundas, ~07h Brasília): Agente 2 + Agente 3.

**Para rodar manualmente sem esperar o horário:**
GitHub → aba **Actions** → selecione o workflow → **Run workflow**.

**Para ver o que aconteceu numa execução:**
Clique na execução → veja os steps → se algo falhou, baixe o artifact de logs na parte de baixo da página.

**Secrets necessários** (Settings → Secrets and variables → Actions):
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, `LICHESS_USERNAME`, `LICHESS_TOKEN`, `LICHESS_GAMES_LIMIT`, `CHESSCOM_USERNAME`, `CHESSCOM_MONTHS_LIMIT`, `YOUTUBE_API_KEY`

⚠️ Erro clássico já visto duas vezes: `SUPABASE_URL` cadastrado com `/rest/v1/` no final. O valor certo é só `https://SEU_PROJETO.supabase.co`, sem nada depois.

---

## 7. Dashboard (Angular)

```powershell
cd frontend
ng serve
```
Acesse `localhost:4200`. Componentes hoje:
- **Narrativa** (topo): resumo em texto do Agente 2.
- **Hexágono**: gráfico de radar com toggle "Frequência de erros" / "Pontos fortes".
- **Sessões de treino**: lista de sprints, com botão para marcar como concluída.

Credenciais em `frontend/src/environments/environment.ts` (usa a chave **anon**, nunca a service role).

---

## 8. O ciclo de uso recomendado (o que você faz)

1. Jogue partidas normalmente no Lichess/Chess.com.
2. Deixe a automação rodar sozinha (diário/semanal).
3. Abra o dashboard, veja seu gargalo atual e a sprint prescrita.
4. Estude/pratique o que a sprint sugere.
5. Marque a sessão como **concluída** no dashboard.
6. Continue jogando — depois de ~15 dias, `medir_eficacia.py` (roda junto com o semanal) vai avaliar se aquele treino específico reduziu a frequência daquele erro.

---

## 9. Glossário rápido dos agentes

| Agente | O que faz | Usa LLM? |
|---|---|---|
| **Agente 1 (Linter)** | Diagnostica CADA lance ruim individualmente | Sim (Gemini) |
| **Agente 2 (Analista)** | Calcula estatística agregada (SQL/pandas) + narra em texto | Só para narrar |
| **Agente 3 (Prescritor)** | Busca no RAG + YouTube, monta sprint de treino | Sim (Gemini) |
| **medir_eficacia** | Compara frequência de erros antes/depois de um treino concluído | Não |

---

## 10. Problemas comuns e onde olhar

| Sintoma | Causa provável | Onde checar |
|---|---|---|
| `PGRST125: Invalid path` | `SUPABASE_URL` com `/rest/v1/` sobrando | `.env` local ou GitHub Secret |
| Script diz "0 processados, 0 falhas" suspeito | Variável de ambiente ausente/errada | Rodar o script manual pra ver erro real |
| Sprint sempre cita o mesmo livro | Índice conceitual só tem esse livro para a categoria, ou poucos conceitos | `select livro from indice_conceitual where conceito ilike '%tema%'` |
| Análise Stockfish trava/demora muito | Partida muito longa (raro) ou backlog grande (primeira vez) | Normal na primeira execução após importar muito histórico |
| Log do GitHub Actions com números tipo `***` | Secret numérico curto mascarando dígitos coincidentes | Mover esse valor de Secret para Variable |

---

## 11. Livros já processados no RAG

| Livro | Idioma | OCR necessário |
|---|---|---|
| Meu Sistema — Aaron Nimzowitsch | PT | Sim |
| Xadrez Vitorioso: Táticas — Seirawan/Silman | PT | Não (texto nativo) |

**Pendente:** "How to Calculate Chess Tactics" (inglês, precisa OCR + configurar idioma inglês no Tesseract).

---

*Última atualização: mantenha este arquivo conforme o projeto evoluir — ele não se atualiza sozinho.*
