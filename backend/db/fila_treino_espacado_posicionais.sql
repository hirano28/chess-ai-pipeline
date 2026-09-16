-- D-55: `fila_treino_espacado` ganha a TERCEIRA origem possível. O D-48 trouxe
-- os lances críticos do próprio usuário, o D-49 os exercícios táticos de
-- catálogo, e agora entram os exercícios posicionais de partidas OTB reais
-- (ver exercicios_posicionais.sql).
--
-- Mesma decisão do D-49, pelo mesmo motivo: uma fila só, um motor SM-2 só, um
-- "feitas hoje" só. Três telas de treino fragmentariam o progresso em três
-- contagens, que é pior do que o próprio usuário pediu.
--
-- O XOR de duas colunas vira "exatamente uma de três" com num_nonnulls(), que
-- é builtin do Postgres e lê melhor que a cadeia de <> encadeados.
--
-- `on delete restrict` igual ao `exercicio_id`: reimportar/limpar o catálogo
-- não pode arrastar em silêncio o progresso de SM-2 de quem já treinou.

alter table public.fila_treino_espacado
    add column if not exists posicional_id uuid
        references public.exercicios_posicionais(id) on delete restrict;

do $$
begin
    -- O check de origem do D-49 precisa aceitar o novo valor.
    if exists (
        select 1 from pg_constraint where conname = 'fila_treino_espacado_origem_check'
    ) then
        alter table public.fila_treino_espacado
            drop constraint fila_treino_espacado_origem_check;
    end if;
    alter table public.fila_treino_espacado
        add constraint fila_treino_espacado_origem_check
            check (origem in ('lance_critico', 'exercicio_tatico', 'exercicio_posicional'));

    -- E o XOR de duas colunas vira "exatamente uma de três".
    if exists (
        select 1 from pg_constraint where conname = 'fila_treino_espacado_origem_xor_check'
    ) then
        alter table public.fila_treino_espacado
            drop constraint fila_treino_espacado_origem_xor_check;
    end if;
    alter table public.fila_treino_espacado
        add constraint fila_treino_espacado_origem_xor_check
            check (num_nonnulls(lance_id, exercicio_id, posicional_id) = 1);

    if not exists (
        select 1 from pg_constraint where conname = 'fila_treino_espacado_user_posicional_key'
    ) then
        alter table public.fila_treino_espacado
            add constraint fila_treino_espacado_user_posicional_key
                unique (user_id, posicional_id);
    end if;
end $$;

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
