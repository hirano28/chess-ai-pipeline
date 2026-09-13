-- D-28: onboarding de novo usuário (Fase C do multi-tenant).
-- Conta(s) de Lichess/Chess.com de cada usuário logado - fonte que os
-- coletores em backend/ingestao/ usam para saber DE QUEM buscar partidas e a
-- QUEM atribuir o user_id gravado. Pelo menos uma das duas colunas precisa
-- estar preenchida.
create table if not exists public.perfis_usuario (
  user_id uuid primary key references auth.users(id) on delete cascade,
  lichess_username text,
  chesscom_username text,
  updated_at timestamptz not null default now(),
  constraint perfis_usuario_pelo_menos_uma_conta
    check (lichess_username is not null or chesscom_username is not null)
);

comment on table public.perfis_usuario is
  'Conta(s) de Lichess/Chess.com de cada usuário logado - fonte que os coletores '
  'em backend/ingestao/ usam para saber DE QUEM buscar partidas e a QUEM atribuir '
  'o user_id gravado. Pelo menos uma das duas colunas precisa estar preenchida (D-28).';

alter table public.perfis_usuario enable row level security;

-- Mesmo padrão de D-19: cada usuário só enxerga e grava a própria linha.
create policy "usuario le o proprio perfil" on public.perfis_usuario
  for select to authenticated
  using (user_id = auth.uid());

create policy "usuario cria o proprio perfil" on public.perfis_usuario
  for insert to authenticated
  with check (user_id = auth.uid());

create policy "usuario atualiza o proprio perfil" on public.perfis_usuario
  for update to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());
