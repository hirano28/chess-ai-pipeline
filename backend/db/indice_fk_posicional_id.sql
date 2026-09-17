-- O D-55 acrescentou `fila_treino_espacado.posicional_id` (terceira origem de
-- card, os exercícios posicionais) mas não o índice de cobertura da FK. As
-- outras duas origens ganharam o seu em `indices_fk_faltantes.sql`; esta ficou
-- de fora, e o advisor de performance do Supabase a apontou sozinha em
-- 17/09/2026.
--
-- A unique `(user_id, posicional_id)` já existente NÃO cobre este caso: o
-- índice composto só serve a buscas que começam por `user_id`, e a checagem de
-- FK (e o `on delete restrict` do catálogo) filtra por `posicional_id` puro.

create index if not exists idx_fila_treino_espacado_posicional_id
    on public.fila_treino_espacado (posicional_id);

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
