-- D-48: fila de repetição espaçada (estilo SM-2) sobre os próprios lances
-- críticos do usuário. Populada em lote por
-- backend/agentes/popular_fila_treino_espacado.py (loop por usuário, D-28),
-- lida/atualizada via GET /treino/fila e POST /treino/{id}/responder.
--
-- `lance_id` aponta para lances_criticos, não para diagnosticos: a posição
-- (fen_antes_lance) mora lá. A citação de livro é resolvida UMA VEZ na
-- população (buscar_conceitos, sem custo de LLM) e cacheada aqui, para o
-- endpoint de resposta não precisar consultar indice_conceitual toda vez.
--
-- `on delete cascade`: quando uma partida é reprocessada (R6 em AGENTS.md
-- apaga lances_criticos antigos antes de gerar novos, D-39), a linha da fila
-- correspondente some junto, em vez de virar FK quebrada ou lixo órfão.
--
-- D-49 tornou `lance_id` opcional e acrescentou um segundo tipo de origem
-- (exercícios do catálogo tático) - ver backend/db/fila_treino_espacado_exercicios.sql.

create table if not exists public.fila_treino_espacado (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  lance_id uuid not null references public.lances_criticos(id) on delete cascade,
  proxima_revisao_data date not null,
  intervalo_dias integer not null default 0,
  fator_facilidade numeric not null default 2.5,
  repeticoes integer not null default 0,
  total_revisoes integer not null default 0,
  ultima_qualidade smallint,
  livro_citado text,
  capitulo_citado text,
  pagina_citada integer,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  unique (user_id, lance_id)
);

comment on table public.fila_treino_espacado is
  'Fila de repetição espaçada (D-48) sobre os lances críticos PICO já '
  'diagnosticados do usuário. Agendamento SM-2 simplificado: repeticoes/'
  'fator_facilidade/intervalo_dias seguem o algoritmo clássico, qualidade '
  '0-5 derivada de classificar_qualidade_lance (BOM=5, SUBOTIMO=3, RUIM=1). '
  'D-49 acrescentou uma segunda origem possível (exercícios de catálogo) - '
  'ver fila_treino_espacado_exercicios.sql.';

comment on column public.fila_treino_espacado.livro_citado is
  'Citação resolvida uma vez na população via buscar_conceitos() '
  '(agente3_prescritor.py) - null quando a categoria não tem conceito '
  'indexado; não é erro, o frontend só omite o bloco de citação.';

alter table public.fila_treino_espacado enable row level security;

-- Defesa em profundidade, igual a uso_diario_usuario (D-32): o backend usa a
-- service role e ignora RLS mesmo assim, mas a policy garante que ninguém
-- mais enxergue a fila alheia se algum dia essa tabela for lida direto do
-- frontend via SupabaseService.client. Sem policy de insert/update para
-- `authenticated` - só o script de população e a API (service role) escrevem.
create policy "usuario le a propria fila de treino" on public.fila_treino_espacado
  for select to authenticated
  using (user_id = auth.uid());

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
