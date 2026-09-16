-- D-54: a sessão de treino deixa de ser um texto prescrito e passa a ser algo
-- que EXECUTA. Motivo medido, não suposto: em 16/09/2026 a tabela tinha 5
-- sessões prescritas pelo Agente 3, 0 concluídas e 0 com eficácia medida —
-- `backend/agentes/medir_eficacia.py` só olha sessões com `data_concluida`
-- preenchida, então o agente que mede se o treino funcionou nunca teve o que
-- medir. O loop adaptativo do produto nunca fechou uma única vez.
--
-- A causa é que a sessão só continha módulos de leitura (livro/capítulo/página)
-- e um botão manual de "marcar como concluída" que ninguém aperta. As colunas
-- abaixo permitem iniciar a sessão, acompanhar bloco a bloco e concluí-la
-- SOZINHA quando o último bloco termina — é a conclusão automática que liga o
-- medir_eficacia pela primeira vez.
--
-- Nenhuma coluna de categoria é criada de propósito: `diagnostico_gargalo` já
-- guarda "CATEGORIA: título" e `medir_eficacia.categoria_do_diagnostico()` já
-- parseia esse formato desde o D-19. Derivar em tempo de leitura faz as 5
-- sessões antigas funcionarem na tela nova sem backfill nenhum (mesmo
-- raciocínio do D-51 sobre juntar FEN na leitura em vez de reprocessar).

alter table public.sessoes_treino
    add column if not exists data_iniciada timestamptz;

alter table public.sessoes_treino
    add column if not exists progresso jsonb not null default '{}'::jsonb;

comment on column public.sessoes_treino.data_iniciada is
  'Quando o usuário clicou "Iniciar sessão" (POST /sessoes/{id}/iniciar). '
  'Null = prescrita mas nunca aberta. É nesse momento que os exercícios do '
  'bloco de prática entram em fila_treino_espacado.';

comment on column public.sessoes_treino.progresso is
  'Estado da execução (D-54): {"blocos_concluidos": [0,1], "fila_ids": [12,13]}. '
  '`blocos_concluidos` são índices dos módulos de estudo marcados como lidos; '
  '`fila_ids` são as linhas de fila_treino_espacado criadas para o bloco de '
  'prática desta sessão — o progresso da prática é contado em tempo de leitura '
  'a partir de total_revisoes dessas linhas, não duplicado aqui.';

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
