---
doc: ARQUITETURA.md
escopo: componentes, fluxo de dados, superfície de API, frontend, topologia de deploy
nao_contem: estado factual (ver ESTADO.md), comandos (ver OPERACAO.md), schema (ver BANCO.md)
verificado_em: 2026-09-11
---

# Arquitetura do Chess AI Pipeline

## 1. Duas metades independentes

O repositório contém dois sistemas que compartilham o mesmo banco e as mesmas
bibliotecas, mas rodam de formas diferentes:

- **Pipeline em lote** — scripts Python em `backend/`, sem servidor HTTP,
  executados por GitHub Actions ou na mão. Coletam partidas, rodam Stockfish,
  diagnosticam, agregam estatística e prescrevem treino.
- **Aplicação web** — FastAPI (`backend/api/api_server.py`) no Cloud Run +
  Angular (`frontend/`) na Vercel. Dá feedback sob demanda, com o usuário na
  frente da tela.

## 2. Fluxo de dados do pipeline em lote

```
Lichess API / Chess.com API
        ↓  backend/ingestao/coletar_partidas*.py
   tabela partidas (status_processamento = 'pendente')
        ↓  backend/analise_engine/analisar_partidas.py  [Stockfish]
   tabela lances_criticos (eventos PICO e EROSAO)
        ↓  backend/agentes/agente1_linter.py            [Gemini]
   tabela diagnosticos (tags_falha, causa raiz)
        ↓  backend/agentes/agente2_analista.py          [pandas + Gemini p/ narrar]
   tabela analises_hexagono (métricas agregadas + gargalo atual)
        ↓  backend/agentes/agente3_prescritor.py        [RAG pgvector + YouTube + Gemini]
   tabela sessoes_treino (sprint com módulos citando livro/capítulo/página)
        ↓  backend/agentes/medir_eficacia.py
   coluna sessoes_treino.eficacia_medida (fecha o loop adaptativo)
```

Enriquecimentos que entram lateralmente nesse fluxo:

- `backend/ingestao/enriquecer_partidas_lichess.py` → `metricas_lichess_partida`
  e `tempos_lance` (precisão por fase e relógio, calculados pelo próprio Lichess).
- `backend/ingestao/importar_anotacoes_lichess.py` → `anotacoes_pensamento`
  (comentários que o jogador escreveu em um Lichess Study).
- `backend/ingestao/importar_puzzle_activity.py` → `puzzle_atividade`.
- `backend/agentes/gerar_resumo_partida.py` → `resumo_partida` (narrativa da
  partida inteira + momento-chave estratégico).
- `backend/agentes/gerar_perguntas_pendentes.py` → `perguntas_pendentes`.

## 3. Os três agentes de LLM

| Agente | Arquivo | Entrada | Saída | Papel do LLM |
|---|---|---|---|---|
| 1 — Linter | `agente1_linter.py` | um lance crítico + linha do motor | `diagnosticos` | diagnostica a causa do erro em 16 tags fechadas |
| 2 — Analista | `agente2_analista.py` | todos os diagnósticos | `analises_hexagono` | só narra; a estatística é pandas puro |
| 3 — Prescritor | `agente3_prescritor.py` | gargalo + RAG de livros | `sessoes_treino` | monta a sprint citando teoria real |

O Agente 1 usa **prompts diferentes por `tipo_evento`**: um para `PICO` (erro
pontual em um lance) e `build_erosion_prompt` para `EROSAO` (perda gradual ao
longo de uma janela de lances). Misturar os dois inverte a perspectiva e faz o
modelo atribuir lances do jogador ao adversário — ver `D-3` em `DECISOES.md`.

## 4. RAG de livros de xadrez

Distinto do conhecimento de agente deste repositório. `backend/rag/processar_livro.py`
faz OCR quando necessário, quebra o PDF em chunks por capítulo, gera embeddings e
grava em `livros_chunks` (pgvector). A busca acontece via RPC
`match_livros_chunks` (`backend/db/match_livros_chunks.sql`), consumida pelo
Agente 3. A tabela `indice_conceitual` é um mapa **manual** de
conceito → livro → capítulo → página, populado por SQL depois de processar cada
livro.

## 5. Superfície da API

Todos os endpoints exigem header `X-API-Key`, exceto `/health` e `/guia-passos`.
A autenticação aceita múltiplas chaves nomeadas via `API_SECRET_KEYS`
(formato `nome:chave,nome:chave`) e registra em log quem chamou.

| Método e rota | Função |
|---|---|
| `GET /health` | health check do Cloud Run (público) |
| `GET /guia-passos` | títulos dos 8 passos da rubrica (público) |
| `POST /revisar-avulso` | avalia lance único ou sequência a partir de FEN/PGN + texto do raciocínio |
| `POST /revisar-avulso/salvar` | persiste um exercício revisado; devolve o `id` da linha criada |
| `GET /revisoes-avulsas/recentes` | histórico do Laboratório (só o que foi salvo manualmente) |
| `POST /explicar-posicao` | avaliação objetiva + explicação didática de uma posição; persiste em `explicacoes_posicao` e devolve o `id` (falha de persistência não derruba a resposta — ver D-11) |
| `GET /explicacoes-posicao/recentes` | histórico do Explicador; cada item embute a resposta completa, sem endpoint "buscar por id" |
| `GET /resolver-fen` | resolve FEN ou PGN para o FEN final; parsing puro, sem Gemini nem Stockfish |
| `POST /reconhecer-posicao` | recebe foto de diagrama (multipart) e devolve o FEN, via Gemini multimodal |
| `POST /analisar-pgn` | dispara o pipeline completo de uma partida; responde `202` na hora e processa em `BackgroundTasks` |
| `GET /partidas/{id}/resumo` | status do processamento + `resumo_partida` quando concluído |
| `GET /partidas/recentes` | histórico para a tela do Analisador |
| `POST /partidas/{id}/reprocessar` | reseta para `pendente` e reexecuta |

Recursos caros (Stockfish, cliente Gemini, cliente Supabase, `engine_lock`) são
inicializados uma vez no startup e guardados em `_state`, um dict de módulo.

## 6. Frontend

Angular 21, standalone components, signals, Tailwind CSS 4, testes em Vitest.

| Rota | Componente | O que faz |
|---|---|---|
| `/` | `hexagono-radar` | radar das 6 categorias + narrativa + sessões de treino |
| `/laboratorio` | `laboratorio-raciocinio` | exercício avulso com feedback imediato |
| `/explicador` | `explicador-posicao` | explicação didática de uma posição |
| `/analisador` | `analisador-partida` | cola PGN, acompanha o progresso, lê o resumo |

Componentes de apoio: `tabuleiro-preview` (tabuleiro 8x8 em CSS Grid com SVGs do
conjunto cburnett), `narrativa-analise`, `perguntas-pendentes`, `sessoes-treino`,
`historico-analise` (lista de histórico genérica e reutilizável — ver D-11 em
`DECISOES.md`; as 3 telas interativas mapeiam seus próprios itens para o shape
`HistoricoAnaliseItem` e tratam `(itemClicado)` para restaurar o que só cada uma
sabe restaurar).

Cada uma das 3 telas interativas persiste o item ativo em `localStorage` para
sobreviver a um F5 (`chess_analisador_partida_ativa`, `chess_explicador_ativo`,
`chess_laboratorio_ativo`). `frontend/src/app/shared/data.ts` guarda o
formatador de data compartilhado por todas elas.

Convenções do frontend que não são óbvias:

- Assets ficam em `frontend/public/`, **não** em `src/assets/` — é o que o
  `angular.json` serve. Referencie sem prefixo (`pieces/cburnett/wK.svg`).
- O Angular colapsa espaço entre elementos no template. Para manter um espaço
  entre dois `<span>` irmãos, use a entidade `&ngsp;`.
- `frontend/src/app/shared/` guarda funções puras reaproveitáveis entre
  componentes (ex.: `lichess.ts`, que monta a URL do analisador do Lichess).

## 7. Topologia de deploy

- **Frontend**: Vercel, deploy automático a cada push na `main`.
  `https://chess-ai-pipeline.vercel.app`
- **Backend**: Cloud Run, serviço `laboratorio-xadrez`, região `us-east1`,
  projeto GCP `gen-lang-client-0828609060`.
  `https://laboratorio-xadrez-kltmum75rq-ue.a.run.app`
- **CI/CD do backend**: `.github/workflows/deploy-backend.yml`, disparado por push
  na `main` que toque `backend/**` ou `Dockerfile`. Roda os testes, autentica no
  GCP com a service account `github-deployer` (secret `GCP_SA_KEY`), builda com
  buildx e cache, publica no Artifact Registry, faz `gcloud run deploy` e valida
  com `curl /health`.
- **Banco**: Supabase Postgres + pgvector, projeto `pmzmershonrqzwbmhaco`.

Deploy manual de emergência:

```bash
gcloud run deploy laboratorio-xadrez --source . --region us-east1 \
  --allow-unauthenticated --max-instances=3 --env-vars-file=env.yaml
```
