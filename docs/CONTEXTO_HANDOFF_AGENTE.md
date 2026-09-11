# CONTEXTO DO PROJETO — Handoff para Agente de IA

Leia este arquivo por completo antes de fazer qualquer alteração. Ele existe para você (agente de IA) se situar rapidamente sem precisar do histórico completo de desenvolvimento.

---

## 1. O que é este projeto

Pipeline pessoal de treino de xadrez movido a IA, para um único usuário (dono do projeto). Fluxo geral:

**Partidas jogadas (Lichess/Chess.com) → Stockfish analisa → LLM (Gemini) diagnostica a causa do erro → estatística agregada revela o gargalo real → RAG sobre livros de xadrez cita teoria relevante → sprint de treino é prescrita → dashboard visualiza tudo → ferramenta interativa dá feedback sobre exercícios avulsos.**

Não é um produto comercial nem multiusuário — é uma ferramenta pessoal, hoje compartilhada com alguns amigos apenas na parte de exercícios avulsos (Laboratório de Raciocínio).

---

## 2. Documentos que você DEVE ler antes de mexer em qualquer coisa

Nesta ordem:
1. `docs/GUIA_DO_PROJETO.md` — referência de comandos, estrutura de pastas, ordem de execução.
2. `docs/ROADMAP_EVOLUCAO.md` — histórico de decisões técnicas e por que certas escolhas foram feitas (Win%, detecção de erosão, etc.).
3. `docs/GUIA_GUESS_THE_MOVE.md` — a rotina de 8 passos que o próprio sistema usa como rubrica de avaliação (usado por `revisar_pensamento.py`).
4. Este arquivo (`CONTEXTO_HANDOFF_AGENTE.md`).

---

## 3. Arquitetura em duas partes distintas

### 3.1 — Pipeline de dados (roda localmente ou via GitHub Actions)
Scripts Python em `backend/`, sem servidor HTTP — são executados via linha de comando, agendados (GitHub Actions) ou manualmente. Usam Stockfish (binário local) + Gemini API + Supabase.

### 3.2 — Laboratório de Raciocínio (aplicação web publicada)
- **Frontend**: Angular, publicado na **Vercel** (`https://chess-ai-pipeline.vercel.app`). Deploy automático a cada `git push` na branch principal (`main`).
- **Backend**: FastAPI (`backend/api/api_server.py`), publicado no **Google Cloud Run** (serviço `laboratorio-xadrez`, região `us-east1`, projeto `gen-lang-client-0828609060`).
- **Deploy automático do Backend**: Configurado via GitHub Actions (`.github/workflows/deploy-backend.yml`). A cada commit na branch `main` contendo alterações em `backend/` ou `Dockerfile`:
  1. Executa a suíte de 80 testes unitários do backend.
  2. Autentica no GCP via Service Account `github-deployer` (secret `GCP_SA_KEY`).
  3. Builda a imagem Docker com buildx e cache no GitHub Actions e faz push para o Artifact Registry.
  4. Executa o deploy da nova revisão no Cloud Run (`gcloud run deploy laboratorio-xadrez --image ... --region us-east1`).
  5. Realiza teste de saúde (`curl /health`).
*(Caso seja necessário fazer deploy manual de emergência localmente, o comando continua sendo: `gcloud run deploy laboratorio-xadrez --source . --region us-east1 --allow-unauthenticated --max-instances=3 --env-vars-file=env.yaml`)*

---

## 4. Schema real do banco (Supabase Postgres) — confirmado via introspecção direta

| Tabela | Colunas principais | Propósito |
|---|---|---|
| `partidas` | plataforma, external_id, pgn, resultado, cor_jogada, ratings, eco_abertura, status_processamento | Toda partida coletada |
| `lances_criticos` | numero_lance, numero_lance_fim, tipo_evento (`PICO`/`EROSAO`), gravidade_cpl, queda_win_percent | Lances/janelas ruins detectados pelo Stockfish |
| `diagnosticos` | lance_id, tags_falha[] (16 tags controladas), diagnostico_mecanico, tipo_erro (`PROCESSO`/`CONTEUDO`/`INDETERMINADO`) | Causa do erro, via Gemini |
| `analises_hexagono` | metricas (jsonb), narrativa, gargalo_sistemico_atual | Saída do Agente 2 |
| `sessoes_treino` | diagnostico_gargalo, modulos (jsonb), data_concluida, eficacia_medida | Sprints do Agente 3 |
| `livros_chunks` | livro, capitulo, pagina_aprox, conteudo, embedding (vector) | RAG dos livros processados |
| `indice_conceitual` | conceito, livro, capitulo, pagina_aprox | Mapa manual conceito→localização no livro |
| `tempos_lance` | numero_lance, cor, tempo_restante_seg, tempo_gasto_seg | Dados de relógio (só Lichess) |
| `metricas_lichess_partida` | precisao_propria, acpl, fase_abertura_fim, fase_meiojogo_fim | Dados já calculados pelo próprio Lichess |
| `anotacoes_pensamento` | partida_id, numero_lance, texto_pensamento, origem | Anotações reais do jogador (Lichess Study ou pergunta retroativa) |
| `perguntas_pendentes` | lance_id, pergunta_texto, status | Perguntas geradas para lances sem anotação (só em partidas já anotadas) |
| `revisoes_pensamento` | qualidade_lance, qualidade_raciocinio, top_candidatos, checklist_rotina | Revisão IA do raciocínio em partidas reais |
| `revisao_exercicio_avulso` | fen, lance_jogado, melhor_lance, qualidade_lance, qualidade_raciocinio | Mesma revisão, para exercícios avulsos (Laboratório) |
| `resumo_partida` | partida_id, narrativa, pontos_criticos (jsonb), momento_chave_estrategico | Resumo narrativo consolidado da partida inteira |
| `puzzle_atividade` | puzzle_id, acertou, temas[], rating_puzzle | Histórico de puzzles do Lichess |

**Vocabulário controlado de 16 tags** (`tags_falha`): calculo_tatico_deficiente, seguranca_do_rei, perda_de_iniciativa, erro_tecnico_de_final, fraqueza_estrutural_de_peoes, negligencia_profilatica, gestao_de_tempo_ruim, abertura_de_linhas_desfavoravel, simplificacao_prematura, avaliacao_posicional_incorreta, troca_desfavoravel, falta_de_coordenacao_de_pecas, ataque_prematuro, passividade_excessiva, visao_em_tunel, perda_de_material. **Não crie tags novas sem necessidade real comprovada** — já verificamos que o vocabulário atual cobre bem os casos reais.

---

## 5. Estado atual — o que já está validado com dados reais

- ✅ Ingestão Lichess + Chess.com, Stockfish, Agente 1 (diagnóstico), Agente 2 (estatística + narrativa), Agente 3 (sprints com RAG).
- ✅ Métrica de gravidade em Win% (não centipawns crus) — corrige viés de posições já decididas.
- ✅ Detecção de erosão estratégica (janelas de lances, não só picos isolados).
- ✅ Enriquecimento com dados já calculados pelo Lichess (precisão por fase, relógio).
- ✅ Tag `gestao_de_tempo_ruim` ativa (usa dado real de relógio).
- ✅ RAG com 2 livros processados ("Meu Sistema" - Nimzowitsch, "Xadrez Vitorioso: Táticas" - Seirawan/Silman).
- ✅ Loop adaptativo (`medir_eficacia.py`) — criado e testado, mas **ainda sem nenhum caso real processado** (nenhuma sessão de treino foi concluída de verdade ainda).
- ✅ Laboratório de Raciocínio completo: aceita FEN/PGN, lance único ou sequência, mostra top 3 candidatos do motor com explicação comparativa validada (anti-alucinação), classifica qualidade do lance e do raciocínio, e avalia aderência à rotina de 8 passos do guia.
- ✅ Publicado em produção (Vercel + Cloud Run) e compartilhado com alguns amigos via chaves de API individuais.
- ✅ Deploy contínuo automático: Cloud Run (backend) via GitHub Actions + Vercel (frontend).
- ✅ Explicador de Posição: backend com Stockfish Win% e Gemini anti-alucinação + frontend Angular em `/explicador`.
- ✅ Resumo Narrativo de Partida: `gerar_resumo_partida.py` e tabela `resumo_partida`.
- ✅ Orquestrador de PGN Avulso: `analisar_pgn_avulso.py` rodando o pipeline ponta a ponta (Stockfish -> Diagnóstico -> Resumo).
- ✅ Endpoints de Análise de Partida: `POST /analisar-pgn` (assíncrono com BackgroundTasks), `GET /partidas/{partida_id}/resumo`, `GET /partidas/recentes` (histórico) e `POST /partidas/{partida_id}/reprocessar`.
- ✅ Analisador de Partida no Frontend: tela `/analisador` com input de PGN, progresso em tempo real, card de histórico, persistência via `localStorage` (recuperação pós-F5), reprocessamento com 1 clique e exibição do momento-chave estratégico.
- ✅ Infraestrutura Cloud Run: alocação de 2 GiB de memória e 2 vCPUs com `--no-cpu-throttling`, corrigindo OOM e congelamento de CPU durante a análise com Stockfish.
- ✅ Suíte de testes: 219 testes unitários de backend + 27 testes unitários de frontend (Vitest) passando 100%.

## 6. Pendências conhecidas (não esqueça)

- 🔴 **Rotação de chaves pendente.** `GEMINI_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY` e as `API_SECRET_KEYS` antigas foram expostas em texto puro várias vezes durante o desenvolvimento (compartilhadas em conversas/logs). Isso **ainda não foi corrigido**. Se for pedido para mexer em segurança, essa é a prioridade nº 1.
- 🟡 Nenhuma sessão de treino foi concluída de verdade — o loop adaptativo (Fase 11) está pronto mas nunca rodou com dado real.
- 🟡 ChessTempo não tem API pública — não perca tempo tentando integrar diretamente; a alternativa usada foi migrar exercícios temáticos para o próprio sistema de puzzles do Lichess (que tem API).
- 🟡 Livro "How to Calculate Chess Tactics" (inglês, precisa OCR) nunca foi processado — ficou pendente.
- 🟡 `chess-ai-pipeline` (projeto novo do Google Cloud, criado por engano numa tentativa de resolver um problema não relacionado) pode ainda existir e não ter sido deletado — verificar com `gcloud projects list` e deletar se ainda estiver lá.

---

## 7. Convenções de trabalho estabelecidas neste projeto

1. **Nunca gerar código sem antes confirmar o formato real de uma API externa.** Várias vezes assumimos um formato de resposta (Lichess API, Chesscom API) que estava errado — sempre valide primeiro com uma chamada real/print antes de escrever a lógica de parsing definitiva.
2. **Validação anti-alucinação é obrigatória sempre que o LLM cita dado técnico específico** (página de livro, lance de xadrez, nome de capítulo). Padrão usado: extrair menções via regex, comparar contra a fonte real, se não bater → retry de correção → se falhar de novo, fallback não-LLM formatando o dado real literalmente. Veja `revisar_pensamento.py` como referência desse padrão.
3. **Sempre resetar `status_processamento = 'pendente'` e limpar registros derivados antes de reprocessar** algo que já rodou (evita duplicar ou misturar dado antigo com novo).
4. **Migrações de schema**: use `NOTIFY pgrst, 'reload schema';` depois de `alter table` no Supabase, senão a API REST não reconhece a coluna nova imediatamente (já causou erro `PGRST204` mais de uma vez).
5. **`SUPABASE_URL` nunca deve ter `/rest/v1/` no final** — a lib já adiciona isso sozinha. Esse erro específico (`PGRST125`) já aconteceu 3 vezes neste projeto.
6. **Timeout/concorrência do Stockfish**: o motor roda como subprocess único; qualquer novo endpoint/script que o use precisa de lock de concorrência (`threading.Lock`) se houver risco de chamadas simultâneas — já causou travamento silencioso sem esse cuidado.
7. **Não crie tags novas no vocabulário controlado sem antes confirmar, via query real no banco, que o conceito realmente não está coberto** — já aconteceu de supor uma lacuna que não existia.

---

## 8. Variáveis de ambiente (nomes, não valores — valores estão em `.env` e `env.yaml`, nunca commitados)

`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, `LICHESS_USERNAME`, `LICHESS_TOKEN`, `LICHESS_STUDY_TOKEN`, `LICHESS_GAMES_LIMIT`, `CHESSCOM_USERNAME`, `CHESSCOM_MONTHS_LIMIT`, `YOUTUBE_API_KEY`, `STOCKFISH_PATH`, `API_SECRET_KEYS` (formato `nome:chave,nome:chave`), `ALLOWED_ORIGINS`.

---

## 9. O que NÃO fazer

- Não tente reconstruir integração com ChessTempo (sem API pública, já investigado).
- Não gaste tempo tentando resolver o Gemini Code Assist na IDE do dono do projeto — é uma descontinuação permanente do Google (desde 18/06/2026), não um bug local. Ele está usando outro assistente de IA para código (você, provavelmente).
- Não apague partidas antigas sem anotação de pensamento — elas continuam válidas para as estatísticas do hexágono, só não têm o campo `tipo_erro`/`checklist_rotina` preenchido, e isso é esperado, não é erro.
