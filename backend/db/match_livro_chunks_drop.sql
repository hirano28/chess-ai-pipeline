-- Auditoria de segurança/operação pós-D-49: `match_livro_chunks` (singular,
-- filtro_livro text - um único livro) é uma versão anterior de
-- `match_livros_chunks` (plural, filtro_livros text[] - vários livros, a
-- versão realmente usada por agente3_prescritor.py). Achado durante a
-- auditoria: existia só no banco, sem nenhum arquivo .sql correspondente no
-- repo (drift não documentado) e sem nenhum call site no código - dead code
-- puro. O advisor de segurança também apontava seu search_path mutável; em
-- vez de corrigir uma função morta, ela sai de vez.

drop function if exists public.match_livro_chunks(vector, text, text[], integer);

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
