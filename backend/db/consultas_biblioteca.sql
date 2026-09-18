-- D-81: histórico da Biblioteca (pergunta em texto livre respondida com os
-- livros já indexados em `livros_chunks`).
--
-- Mesmo shape de `explicacoes_posicao`: o dict inteiro devolvido pelo módulo
-- vai em `resposta` (jsonb), e a pergunta também vira coluna própria para
-- listar o histórico sem desempacotar o jsonb.
--
-- `user_id uuid not null` SEM foreign key para `auth.users`: é a convenção
-- desta base (nenhuma das tabelas raiz declara essa FK), não um esquecimento.

create table if not exists consultas_biblioteca (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    pergunta text not null,
    resposta jsonb not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_consultas_biblioteca_user_data
    on consultas_biblioteca (user_id, created_at desc);

-- RLS habilitado sem policy, mesmo padrão de `explicacoes_posicao`: só o
-- backend (service role, que ignora RLS) grava e lê - nenhum cliente com a
-- chave anon acessa direto, então isso não bloqueia nada em uso real e evita
-- que a tabela entre para a lista de expostas (ver P-2 em ESTADO.md).
alter table consultas_biblioteca enable row level security;

-- Após rodar no Supabase Dashboard (R5):
-- NOTIFY pgrst, 'reload schema';
