# HANDOFF PARA CLAUDE CODE — ESTADO DO PROJETO & PRÓXIMOS PASSOS

Este documento resume com precisão o estado do repositório, todas as funcionalidades desenvolvidas recentemente e o checklist operacional para você (Claude Code) continuar o desenvolvimento sem perda de contexto ou risco de regressão.

---

## 1. Visão Geral do Projeto & Arquitetura

- **Propósito**: Pipeline pessoal de treino de xadrez do Edson Hirano (`hirano28`).
- **Stack Backend**: Python 3.11 (`fastapi`, `uvicorn`, `supabase-py`, `google-genai`, `stockfish`, `chess` / `python-chess`, `pydantic`).
- **Stack Frontend**: Angular 21 (`standalone components`, signals, Tailwind CSS 4, Vitest).
- **Banco de Dados**: Supabase (PostgreSQL + pgvector).
- **Ambientes em Produção**:
  - **Frontend (Vercel)**: [`https://chess-ai-pipeline.vercel.app`](https://chess-ai-pipeline.vercel.app)
  - **Backend (Cloud Run)**: [`https://laboratorio-xadrez-kltmum75rq-ue.a.run.app`](https://laboratorio-xadrez-kltmum75rq-ue.a.run.app)
- **CI/CD**:
  - Frontend: Deploy automático na Vercel a cada push na branch `main`.
  - Backend: Workflow GitHub Actions em `.github/workflows/deploy-backend.yml` disparado a cada push em `main` (quando há alterações em `backend/**` ou `Dockerfile`). Roda os 219 testes unitários, faz build da imagem Docker, sobe no Artifact Registry e atualiza a revisão do Cloud Run.

---

## 2. O Que Foi Desenvolvido e Consolidado Recentemente

### A. Deploy Automático do Backend (`.github/workflows/deploy-backend.yml`)
- Service Account GCP configurada (`github-deployer`).
- Endpoint `GET /health` adicionado em `backend/api/api_server.py`.
- Pipeline CI/CD executa todos os 219 testes unitários antes de qualquer deploy.
- Alocação garantida no Cloud Run: `--memory 2Gi --cpu 2 --no-cpu-throttling`.

### B. Explicador de Posição (End-to-End)
- **Backend**: `backend/agentes/explicador_posicao.py` + endpoint `POST /explicar-posicao` no `api_server.py`.
- **Frontend**: Componente `frontend/src/app/components/explicador-posicao/` e rota `/explicador`.
- Análise de material, peças indefesas, cravadas, segurança do rei, avaliação Stockfish (Win%) e explicação didática Gemini com validação anti-alucinação.

### C. Agente de Resumo de Partidas (`gerar_resumo_partida.py`)
- **Arquivo**: `backend/agentes/gerar_resumo_partida.py` (37 testes passando).
- **Tabela SQL**: `backend/db/resumo_partida.sql` (tabela `resumo_partida`).
- **Lógica**:
  - Busca partidas com diagnósticos completos que ainda não têm resumo.
  - Consolida pontos críticos (`PICO` e `EROSAO`), métricas de abertura (ECO), e apuro de tempo.
  - Gera narrativa aprofundada estruturada e extrai o **Momento-Chave Estratégico** da partida.
  - Validação anti-alucinação com retry e fallback literal.

### D. Orquestrador de PGN Avulso (`analisar_pgn_avulso.py`)
- **Arquivo**: `backend/agentes/analisar_pgn_avulso.py` (28 testes passando).
- **Lógica**:
  - `resolver_cor(game, cor_fornecida=None)`: Se a cor não for passada, infere automaticamente comparando headers com usernames do `.env` (`LICHESS_USERNAME`, `CHESSCOM_USERNAME`). Se falhar, levanta `ValueError` claro pedindo a cor (evitando bloqueios interativos na API).
  - `determinar_cor(game)`: Mantida para uso exclusivo no terminal CLI.
  - `inserir_partida_avulsa(pgn, cor_jogada, client)`: Faz upsert por `external_id` gerado via hash SHA-256 (`manual_<hash>`).
  - `executar_pipeline_partida(partida_id, client)`: Executa as 3 etapas em sequência:
    1. **Stockfish**: `analisar_partida_com_timeout` (com lock global `engine_lock`).
    2. **Diagnóstico Gemini**: Classificação em 16 tags controladas para lances críticos (`PICO` e `EROSAO`).
    3. **Resumo Narrativo**: `gerar_resumo_partida` com narrativa e momento-chave.
  - Se ocorrer qualquer exceção em qualquer etapa, marca `status_processamento = 'falhou'` e limpa dados parciais.

### E. Endpoints de API Criados (`backend/api/api_server.py`)
- Todos protegidos por `X-API-Key` (validado contra `API_SECRET_KEY` / `API_SECRET_KEYS`):
  - `POST /analisar-pgn`: Recebe `{ pgn: str, cor: 'BRANCAS' | 'PRETAS' | null }`. Valida o PGN, cria a partida no Supabase com status `pendente`, retorna `HTTP 202` imediatamente e agenda a execução via `BackgroundTasks`.
  - `GET /partidas/{partida_id}/resumo`: Consulta status (`pendente`, `processando`, `concluido`, `falhou`) e devolve os dados de `resumo_partida` quando concluído.
  - `GET /partidas/recentes`: Retorna a lista das últimas partidas analisadas (ID, jogadores, cor, abertura ECO, status e data) para preencher o histórico na interface.
  - `POST /partidas/{partida_id}/reprocessar`: Reseta status para `pendente` e reexecuta o pipeline em segundo plano sob demanda.

### F. Frontend do Analisador de Partida (`frontend/src/app/components/analisador-partida/`)
- Rota `/analisador` com design Dark de alto contraste.
- **Histórico de Análises**: Card listando partidas recentes com badges de status em tempo real (`processando`, `pendente`, `concluido`, `falhou`). Clique em qualquer item restaura instantaneamente o relatório na tela.
- **Persistência Pós-Refresh (`F5`)**: O ID da partida ativa é sincronizado no `localStorage` (`chess_analisador_partida_ativa`). Recarregar a tela não perde mais o progresso da análise nem os dados já concluídos.
- **Reprocessamento com 1 Clique**: Botão para forçar reanálise caso uma partida falhe ou trave.
- **Visualização Completa**: Card dourado com o Momento-Chave Estratégico, narrativa parágrafo a parágrafo e grid de lances críticos com tags de falha.

### G. Correções Críticas de Infraestrutura & Multiprocessing
1. **Erro de SemLock (Fork vs Spawn no Linux)**:
   - Em `backend/analise_engine/analisar_partidas.py`, a função `processar_partida_com_timeout` criava `ctx = multiprocessing.get_context("spawn")`, mas antes misturava com `multiprocessing.Queue()`. No Linux com Uvicorn, isso gerava o erro fatal `SemLock created in a fork context is being shared with a process in a spawn context`.
   - **Correção**: Ambos `ctx.Queue()` e `ctx.Process(...)` agora usam o mesmo `ctx` spawn.
2. **CPU Throttling no Cloud Run**:
   - Background tasks do FastAPI sofriam congelamento de CPU assim que a resposta HTTP 202 era enviada.
   - **Correção**: Adicionada a flag `--no-cpu-throttling` no Cloud Run.
3. **Out-of-Memory (OOM) no Cloud Run**:
   - O container com limite padrão de 512 MiB estourava para ~533 MiB durante a avaliação profunda do Stockfish (depth 16 em 65+ lances) somada ao overhead do processo spawn. O Cloud Run enviava `SIGKILL`, matando o processo e deixando a partida órfã em estado "processando".
   - **Correção**: Serviço Cloud Run atualizado para **2 GiB de memória e 2 vCPUs**. Configuração consolidada permanentemente em `.github/workflows/deploy-backend.yml`.
4. **Partida Real de Validação**:
   - A partida `923e26e9-6ecf-4c79-9a29-8944acbe02de` (`MajesticXVI vs tantofaz123`, ECO `A21`) foi reprocessada em produção e concluída com 100% de sucesso.

---

## 3. Estado Atual dos Testes e Repositório

- **Backend**: **219 testes unitários** passando (`python -m unittest`).
  - Módulos testados: `test_agente1_linter`, `test_agente3_prescritor`, `test_analisar_pgn_avulso`, `test_explicador_posicao`, `test_gerar_perguntas_pendentes`, `test_gerar_resumo_partida`, `test_revisar_exercicio_avulso`, `test_revisar_pensamento`, `test_analisar_partidas`, `test_api_server`, `test_chess_math`.
- **Frontend**: **27 testes unitários** passando no Vitest (`npx ng test --no-watch`).
  - Cobertura completa de `AnalisadorPartidaComponent`, `ExplicadorPosicaoComponent` e `App`.
- **Git**: Branch `main` limpa e sincronizada com `origin/main`.

---

## 4. Comandos de Operação e Testes

### Como Rodar Testes no Backend (Python)
```bash
# Execução da suíte completa de backend:
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
  backend.common.test_chess_math
```

### Como Rodar Testes no Frontend (Angular / Vitest)
```bash
cd frontend
npx ng test --no-watch
```

### Como Rodar o Servidor de Desenvolvimento Frontend
```bash
cd frontend
npm start  # Roda em http://localhost:4200
```

### Como Rodar o Servidor Backend Localmente
```bash
uvicorn backend.api.api_server:app --reload --port 8000
```

---

## 5. Regras Críticas e Convenções Obrigatórias

1. **Vocabulário Estrito de 16 Tags de Falha**:
   - `calculo_tatico_deficiente`, `seguranca_do_rei`, `perda_de_iniciativa`, `erro_tecnico_de_final`, `fraqueza_estrutural_de_peoes`, `negligencia_profilatica`, `gestao_de_tempo_ruim`, `abertura_de_linhas_desfavoravel`, `simplificacao_prematura`, `avaliacao_posicional_incorreta`, `troca_desfavoravel`, `falta_de_coordenacao_de_pecas`, `ataque_prematuro`, `passividade_excessiva`, `visao_em_tunel`, `perda_de_material`.
   - **NUNCA crie tags novas sem alinhamento prévio.**
2. **Validação Anti-Alucinação**:
   - Obrigatória ao gerar lances de xadrez via LLM. Padrão: extrair SAN via regex, validar no `chess.Board`, executar retry de correção em caso de erro e usar fallback determinístico se persistir.
3. **Concorrência com Stockfish**:
   - Em qualquer endpoint da API que interaja com o motor, utilize o lock assíncrono `engine_lock` (gerenciado em `backend/api/api_server.py`) para evitar colisão de processos.
4. **Multiprocessing no Linux / Cloud Run**:
   - Sempre use `ctx = multiprocessing.get_context("spawn")` tanto para `ctx.Queue()` quanto para `ctx.Process(...)`.
5. **Configuração de Recursos no Cloud Run**:
   - Sempre manter `--memory 2Gi`, `--cpu 2` e `--no-cpu-throttling` para garantir estabilidade da análise Stockfish.
6. **Supabase Schema Reload**:
   - Ao executar qualquer DDL (`CREATE TABLE`, `ALTER TABLE`) no Supabase SQL Editor, execute sempre:
     ```sql
     NOTIFY pgrst, 'reload schema';
     ```
7. **Formato da `SUPABASE_URL`**:
   - NUNCA deve terminar com `/rest/v1/` (o SDK adiciona o path automaticamente).

---

## 6. Próximos Passos Sugeridos / Backlog de Evolução

1. **Loop Adaptativo de Treino (Agente 3 & `medir_eficacia.py`)**:
   - O pipeline e o modelo de prescrição de treino estão implementados, mas nenhuma sessão real foi concluída e medida de ponta a ponta com partidas jogadas pós-treino.
2. **Visualizador de Tabuleiro Interativo no Analisador**:
   - Adicionar uma visualização visual do tabuleiro (ex.: chessboard interativo no Angular) para permitir avançar lance a lance até os momentos críticos (`PICO` e `EROSAO`) diretamente na interface.
3. **Segurança & Rotação de Chaves**:
   - Fazer rotação das chaves `GEMINI_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY` e `API_SECRET_KEYS` que constam no histórico de desenvolvimento.
