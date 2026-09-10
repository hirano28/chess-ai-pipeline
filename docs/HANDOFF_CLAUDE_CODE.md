# HANDOFF PARA CLAUDE CODE — ESTADO DO PROJETO & PRÓXIMOS PASSOS

Este documento resume com precisão o estado do repositório, as últimas funcionalidades desenvolvidas nesta sessão e o checklist operacional para você (Claude Code) continuar o trabalho sem perda de contexto.

---

## 1. Visão Geral do Projeto & Arquitetura

- **Propósito**: Pipeline pessoal de treino de xadrez do Edson Hirano (`hirano28`).
- **Stack Backend**: Python 3.11 (`fastapi`, `supabase-py`, `google-genai`, `stockfish`, `chess` / `python-chess`, `pydantic`).
- **Stack Frontend**: Angular 21 (`standalone components`, Tailwind CSS 4, Vitest).
- **Banco de Dados**: Supabase (PostgreSQL + pgvector).
- **Deploy Automático**:
  - **Frontend**: Vercel (deploy automático a cada push na `main`). URL: `https://chess-ai-pipeline.vercel.app`
  - **Backend**: Cloud Run (workflow `.github/workflows/deploy-backend.yml` via GitHub Actions). Roda toda a suíte de 214 testes unitários, faz build Docker e deploy no serviço `laboratorio-xadrez` (`us-east1`).

---

## 2. O Que Foi Desenvolvido Recentemente (Nesta Sessão)

### A. Deploy Automático do Backend (`.github/workflows/deploy-backend.yml`) — [CONFIGURADO & TESTADO]
- Service Account GCP configurada (`github-deployer`).
- Endpoint `GET /health` adicionado em `backend/api/api_server.py`.
- Pipeline CI/CD atualizado para rodar todos os módulos de teste (`214 testes de backend`).

### B. Explicador de Posição — [COMMITTED & EM PRODUÇÃO]
- **Backend**: `backend/agentes/explicador_posicao.py` + endpoint `POST /explicar-posicao` no `api_server.py`.
- **Frontend**: Componente `frontend/src/app/components/explicador-posicao/` e rota `/explicador`.
- Análise de material, peças indefesas, cravadas, segurança do rei, avaliação Stockfish (Win%) e explicação didática Gemini com validação anti-alucinação.

### C. Agente de Resumo de Partidas (`gerar_resumo_partida.py`) — [CRIADO & TESTADO]
- **Arquivo**: `backend/agentes/gerar_resumo_partida.py`
- **Tabela SQL**: `backend/db/resumo_partida.sql`
- **Testes**: `backend/agentes/test_gerar_resumo_partida.py` (37 testes passando).
- **Lógica**:
  - Busca partidas com diagnósticos completos que ainda não têm resumo em `resumo_partida`.
  - Coleta lances críticos (`PICO` e `EROSAO`), métricas Lichess (`metricas_lichess_partida`) e apuro de tempo (`tempos_lance`).
  - Reutiliza `HEXAGON_CATEGORIES` (de `agente2_analista.py`), `extrair_lances_san` (de `revisar_pensamento.py`) e `em_apuro_de_tempo` (de `agente1_linter.py`).
  - Validação anti-alucinação com retry e fallback literal.

### D. Orquestrador de PGN Avulso (`analisar_pgn_avulso.py`) — [CRIADO, REFATORADO & TESTADO]
- **Arquivo**: `backend/agentes/analisar_pgn_avulso.py`
- **Testes**: `backend/agentes/test_analisar_pgn_avulso.py` (28 testes passando).
- **Lógica e Refatoração**:
  - `resolver_cor(game, cor_fornecida=None)`: Se a cor não for passada, infere automaticamente comparando headers com usernames do `.env`. Se falhar, levanta `ValueError` claro pedindo a cor (ideal para APIs/não-interativo).
  - `determinar_cor(game)`: Mantida para uso exclusivo do CLI, perguntando interativamente no terminal se a inferência automática falhar.
  - `executar_pipeline_partida(...)`: Função centralizada que executa em sequência Stockfish -> Diagnóstico -> Resumo SOMENTE para a partida indicada. Usa `engine_lock` para proteger o uso do Stockfish contra concorrência e marca `status_processamento='falhou'` se ocorrer qualquer falha durante a execução.

### E. Endpoints da API para Análise de Partida — [CRIADOS & TESTADOS]
- **Arquivo**: `backend/api/api_server.py`
- **Testes**: `backend/api/test_api_server.py` (`AnalisarPgnEndpointTest` com 11 testes).
- **Endpoints**:
  - `POST /analisar-pgn`: Recebe `{ pgn: str, cor: 'BRANCAS' | 'PRETAS' | null }`. Retorna imediatamente status `HTTP 202` com `{ "partida_id": "...", "external_id": "..." }` e dispara o pipeline assíncrono via `BackgroundTasks`.
  - `GET /partidas/{partida_id}/resumo`: Consulta o status atual de processamento (`pendente`, `processando`, `concluido`, `falhou`) e retorna os dados de `resumo_partida` (narrativa, pontos críticos, momento-chave) quando concluído.

### F. Frontend: Tela do Analisador de Partida — [CRIADO & TESTADO]
- **Componente**: `frontend/src/app/components/analisador-partida/`
- **Testes**: `analisador-partida.component.spec.ts` (10 testes Vitest passando; 22 testes no total do front).
- **Rota e Navbar**: Rota `/analisador` em `app.routes.ts` e link `"Analisador de Partida"` em `app.html`.
- **Experiência Visual**:
  - Área para colar PGN com botão de exemplo.
  - Seletor de cor (Automático / Brancas / Pretas).
  - Card de progresso em tempo real (etapas ilustradas, cronômetro de tempo decorrido, polling assíncrono a cada 3.5s).
  - Card de destaque dourado com o **Momento-Chave Estratégico** 🔑.
  - Narrativa profunda parágrafo a parágrafo.
  - Grid de Pontos Críticos (`PICO` / `EROSAO` com suas tags de falha).

---

## 3. Estado Atual dos Arquivos (Git Status)

```text
M  .github/workflows/deploy-backend.yml
M  backend/api/api_server.py
M  backend/api/test_api_server.py
M  docs/CONTEXTO_HANDOFF_AGENTE.md
M  frontend/src/app/app.html
M  frontend/src/app/app.routes.ts
M  frontend/src/app/services/revisao-avulsa.service.ts
?? backend/agentes/analisar_pgn_avulso.py
?? backend/agentes/gerar_resumo_partida.py
?? backend/agentes/test_analisar_pgn_avulso.py
?? backend/agentes/test_gerar_resumo_partida.py
?? backend/db/resumo_partida.sql
?? frontend/src/app/components/analisador-partida/
?? docs/HANDOFF_CLAUDE_CODE.md
```

- **Backend**: **214 testes unitários** passando (`unittest`).
- **Frontend**: **22 testes unitários** passando (`vitest`).
- **Build do Angular**: Compilação de produção executada com sucesso.

---

## 4. Regras Críticas e Convenções Obrigatórias

1. **Nunca crie tags novas**: O vocabulário de `tags_falha` é estrito (16 tags em `agente1_linter.py` / `agente2_analista.py`).
2. **Validação anti-alucinação**: Obrigatória ao gerar lances de xadrez via LLM.
3. **Migration no Supabase**: Após rodar qualquer `ALTER TABLE` ou `CREATE TABLE` no Supabase, SEMPRE execute:
   ```sql
   NOTIFY pgrst, 'reload schema';
   ```
4. **`SUPABASE_URL`**: NUNCA deve terminar com `/rest/v1/` (a SDK adiciona automaticamente).
5. **Stockfish Lock**: Em qualquer endpoint HTTP que chame o Stockfish concorrentemente, use o lock `_state["engine_lock"]`.
6. **Multiprocessing no Linux**: No Linux/Uvicorn, sempre use `ctx = multiprocessing.get_context("spawn")` para criar `ctx.Queue()` e `ctx.Process(...)` juntos para evitar erros de SemLock.

---

## 5. Próximas Ações Imediatas para o Claude Code

1. **Executar a migration SQL** (`backend/db/resumo_partida.sql`) no Supabase SQL Editor e rodar `NOTIFY pgrst, 'reload schema';`.
2. **Commit & Push**: Commitar as alterações na branch `main` para disparar o deploy automático do frontend na Vercel e do backend no Cloud Run via GitHub Actions.
3. **Teste em Produção**: Acessar `https://chess-ai-pipeline.vercel.app/analisador`, colar o PGN de uma partida real e validar o fluxo completo fim a fim.
