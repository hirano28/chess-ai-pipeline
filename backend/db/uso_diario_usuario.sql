-- D-32: limite de uso diário por usuário nas rotas caras da API
-- (/analisar-pgn, /revisar-avulso, /reconhecer-posicao, /explicar-posicao).
-- Uma linha por (user_id, data, rota); `rota` é texto livre em vez de uma
-- rota por coluna para que uma rota nova no futuro não exija migração.

create table if not exists public.uso_diario_usuario (
  user_id uuid not null references auth.users(id) on delete cascade,
  data date not null,
  rota text not null,
  contagem integer not null default 0,
  primary key (user_id, data, rota)
);

comment on table public.uso_diario_usuario is
  'Contador de chamadas por usuário/dia/rota, usado para o limite diário das '
  'rotas caras da API (D-32). Incrementado só via incrementar_uso_diario().';

alter table public.uso_diario_usuario enable row level security;

-- Mesmo padrão de D-19/D-28: cada usuário só enxerga a própria linha. Sem
-- policy de insert/update para `authenticated` — a única escrita é via
-- incrementar_uso_diario(), chamada pelo backend com a service role.
create policy "usuario le o proprio uso" on public.uso_diario_usuario
  for select to authenticated
  using (user_id = auth.uid());

-- Incremento atômico (INSERT ... ON CONFLICT DO UPDATE): evita a corrida em
-- que 2 requisições concorrentes do mesmo usuário leriam a mesma contagem e
-- as duas passariam pelo limite. `data` é calculada em America/Sao_Paulo, não
-- UTC puro, para o limite resetar à meia-noite local do usuário, não às 21h
-- de Brasília (UTC-3).
create or replace function public.incrementar_uso_diario(p_user_id uuid, p_rota text)
returns integer
language sql
security definer
set search_path = public
as $$
  insert into public.uso_diario_usuario (user_id, data, rota, contagem)
  values (p_user_id, (now() at time zone 'America/Sao_Paulo')::date, p_rota, 1)
  on conflict (user_id, data, rota)
  do update set contagem = uso_diario_usuario.contagem + 1
  returning contagem;
$$;

comment on function public.incrementar_uso_diario(uuid, text) is
  'Incrementa atomicamente o contador de uso diário (D-32) e devolve a nova '
  'contagem. Dia calculado em America/Sao_Paulo. Chamada só pelo backend '
  '(service role) - EXECUTE revogado de anon/authenticated para que ninguém '
  'incremente o contador de outro usuário direto via RPC.';

-- Por padrão o Postgres concede EXECUTE em funções novas a PUBLIC. Sem essa
-- revogação, qualquer usuário autenticado poderia chamar
-- POST /rest/v1/rpc/incrementar_uso_diario com o p_user_id de outra pessoa e
-- esgotar o limite diário dela (nada a ver com RLS, que é por linha, não por
-- função).
revoke execute on function public.incrementar_uso_diario(uuid, text) from public, anon, authenticated;

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
