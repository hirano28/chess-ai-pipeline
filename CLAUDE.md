# Claude Code Guide — Chess AI Pipeline

Este repositório é o pipeline pessoal de treino e análise de xadrez de Edson Hirano (`hirano28`).

> 📖 **Para o handoff completo e detalhado das últimas sessões, leia obrigatoriamente:**
> - [`docs/HANDOFF_CLAUDE_CODE.md`](docs/HANDOFF_CLAUDE_CODE.md) (Estado detalhado, decisões recentes e regras operacionais)
> - [`docs/CONTEXTO_HANDOFF_AGENTE.md`](docs/CONTEXTO_HANDOFF_AGENTE.md) (Contexto geral do pipeline e schema do banco)
> - [`docs/GUIA_DO_PROJETO.md`](docs/GUIA_DO_PROJETO.md) (Guia de execução de scripts)

---

## 1. Visão Geral da Arquitetura

- **Backend**: FastAPI + Python 3.11, `stockfish`, `python-chess`, `google-genai` (Gemini), `supabase-py`.
- **Frontend**: Angular 21 (standalone components, signals), Tailwind CSS 4, Vitest.
- **Banco de Dados**: Supabase (Postgres + pgvector).
- **Produção**:
  - Frontend (Vercel): `https://chess-ai-pipeline.vercel.app`
  - Backend (Cloud Run): `https://laboratorio-xadrez-kltmum75rq-ue.a.run.app` (2 GiB RAM, 2 vCPUs, `--no-cpu-throttling`)
  - CI/CD Backend: `.github/workflows/deploy-backend.yml` (dispara testes + deploy automático a cada push na `main`).

---

## 2. Comandos Principais

### Testes do Backend (Python)
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
  backend.common.test_chess_math
```
*(Total: 219 testes unitários)*

### Testes do Frontend (Angular / Vitest)
```bash
cd frontend
npx ng test --no-watch
```
*(Total: 27 testes unitários)*

### Execução Local do Backend
```bash
uvicorn backend.api.api_server:app --reload --port 8000
```

### Execução Local do Frontend
```bash
cd frontend
npm start
```

---

## 3. Regras Críticas e Convenções

1. **Vocabulário Estrito de 16 Tags de Falha**:
   - `calculo_tatico_deficiente`, `seguranca_do_rei`, `perda_de_iniciativa`, `erro_tecnico_de_final`, `fraqueza_estrutural_de_peoes`, `negligencia_profilatica`, `gestao_de_tempo_ruim`, `abertura_de_linhas_desfavoravel`, `simplificacao_prematura`, `avaliacao_posicional_incorreta`, `troca_desfavoravel`, `falta_de_coordenacao_de_pecas`, `ataque_prematuro`, `passividade_excessiva`, `visao_em_tunel`, `perda_de_material`.
   - **NÃO crie tags novas.**
2. **Validação Anti-Alucinação**:
   - Sempre valide lances SAN gerados por LLM via `chess.Board`. Aplique retry de correção e fallback literal em falha persistente.
3. **Concorrência com Stockfish**:
   - Use o lock `engine_lock` ao executar análises do motor via API.
4. **Multiprocessing no Linux / Cloud Run**:
   - Sempre use `ctx = multiprocessing.get_context("spawn")` para instanciar simultaneamente `ctx.Queue()` e `ctx.Process(...)`.
5. **Configuração de Recursos no Cloud Run**:
   - Manter `--memory 2Gi`, `--cpu 2` e `--no-cpu-throttling` (necessário para o processo do Stockfish depth 16).
6. **Supabase Schema Reload**:
   - Sempre rode `NOTIFY pgrst, 'reload schema';` após executar migrações no Supabase.
7. **URL do Supabase**:
   - A variável `SUPABASE_URL` nunca deve ter terminação `/rest/v1/`.
