-- Auditoria de segurança/operação pós-D-49: o advisor de performance do
-- Supabase (unindexed_foreign_keys) apontou 4 FKs sem índice de cobertura -
-- toda query que filtra/junta por essas colunas faz sequential scan.

create index if not exists idx_diagnosticos_lance_id
    on public.diagnosticos (lance_id);

create index if not exists idx_fila_treino_espacado_exercicio_id
    on public.fila_treino_espacado (exercicio_id);

create index if not exists idx_fila_treino_espacado_lance_id
    on public.fila_treino_espacado (lance_id);

create index if not exists idx_lichess_oauth_pkce_user_id
    on public.lichess_oauth_pkce (user_id);

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
