-- D-67: consultas feitas durante uma partida em andamento, espelhada à mão na
-- tela "Consulta ao vivo". Feature exclusiva do dono do projeto (a liberação é
-- por CONSULTA_AO_VIVO_USUARIOS no servidor, não por esta tabela).
--
-- Cada linha é UM momento de dúvida: a partida até ali, o que o jogador disse
-- estar pensando e a resposta em camadas. É o único dado do sistema que registra
-- a dúvida no momento em que ela acontece — todo o resto só vê a partida depois
-- que ela acabou.
--
-- `partida_espelho_id` agrupa as consultas de uma mesma partida espelhada. É
-- gerado pela tela ao começar uma partida nova, e serve ao teto de consultas
-- por partida. Não é FK: a partida real só chega depois, pela coleta, e casar
-- as duas é a fase seguinte (F5.3).
--
-- `lances_san` guarda a partida inteira até a consulta, não só a FEN: é o que
-- permite casar depois com a partida coletada, lance a lance.

create table if not exists public.consultas_ao_vivo (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  partida_espelho_id uuid not null,
  plataforma text not null check (plataforma in ('LICHESS', 'CHESSCOM', 'OUTRA')),
  adversario text,
  cor_jogador text not null check (cor_jogador in ('BRANCAS', 'PRETAS')),
  fen_inicial text not null,
  lances_san text[] not null default '{}',
  numero_lance integer not null,
  fen text not null,
  pensamento_situacao text,
  pensamento_candidatos text,
  pensamento_trava text,
  resposta jsonb not null,
  gerado_por text not null check (gerado_por in ('gemini', 'fallback')),
  criado_em timestamptz not null default now()
);

create index if not exists consultas_ao_vivo_user_partida_idx
  on public.consultas_ao_vivo (user_id, partida_espelho_id);

alter table public.consultas_ao_vivo enable row level security;

-- Mesmo padrão de fila_treino_espacado: o backend escreve com service role, e a
-- policy só existe como defesa em profundidade para leitura direta.
create policy "usuario le as proprias consultas ao vivo" on public.consultas_ao_vivo
  for select to authenticated
  using (user_id = (select auth.uid()));

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
