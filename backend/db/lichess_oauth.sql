-- D-33: fundação do OAuth do Lichess (Authorization Code + PKCE).
--
-- Duas tabelas, as duas sem NENHUMA policy de RLS: nem `anon` nem
-- `authenticated`. Só a service role (que ignora RLS) toca nelas, porque o
-- conteúdo das duas é material secreto que não pode chegar ao frontend em
-- hipótese nenhuma - o access_token dá acesso à conta Lichess da pessoa, e o
-- code_verifier é justamente o que impede um atacante de trocar um código
-- interceptado por um token.

-- Token de acesso de cada usuário logado à SUA conta do Lichess.
-- `refresh_token` existe por completude do schema mas é sempre NULL hoje: a
-- doc oficial do Lichess diz explicitamente que refresh tokens não são
-- suportados (o access_token dura ~1 ano) - ver D-33 em DECISOES.md.
create table if not exists public.lichess_oauth_tokens (
  user_id uuid primary key references auth.users(id) on delete cascade,
  access_token text not null,
  refresh_token text,
  expires_at timestamptz,
  scopes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.lichess_oauth_tokens is
  'Access token OAuth de cada usuário para a própria conta do Lichess (D-33). '
  'Sem policy de RLS de propósito: só a service role lê/escreve, o token nunca '
  'chega ao frontend. refresh_token é sempre NULL - o Lichess não emite.';

alter table public.lichess_oauth_tokens enable row level security;

-- Estado temporário de um fluxo OAuth em andamento: guarda o code_verifier do
-- PKCE e AMARRA o `state` ao usuário que iniciou o fluxo.
--
-- Por que uma tabela e não um dicionário em memória: `iniciar` e `callback`
-- são duas requisições HTTP separadas, com o usuário indo ao Lichess no meio -
-- podem cair em instâncias diferentes do Cloud Run, ou o container pode
-- reciclar entre as duas. Guardar em memória quebraria o fluxo de forma não
-- determinística em produção. TTL curto + consumo único (a linha é deletada
-- no callback) mantêm a janela de ataque mínima.
create table if not exists public.lichess_oauth_pkce (
  state text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  code_verifier text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

comment on table public.lichess_oauth_pkce is
  'Estado efêmero de um fluxo OAuth do Lichess em andamento (D-33): amarra o '
  'state (anti-CSRF, aleatório e de uso único) e o code_verifier do PKCE ao '
  'user_id que iniciou. Linha deletada no callback; TTL de 10 minutos.';

alter table public.lichess_oauth_pkce enable row level security;

create index if not exists lichess_oauth_pkce_expires_at_idx
  on public.lichess_oauth_pkce (expires_at);

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
