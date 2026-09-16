-- D-49: fila_treino_espacado passa a aceitar uma segunda origem além dos
-- lances críticos próprios - exercícios do catálogo tático (importado do
-- Lichess, ver exercicios_taticos.sql e backend/rag/importar_exercicios_taticos.py),
-- inseridos quando o usuário pede treino focado numa categoria fraca
-- (POST /treino/foco/{categoria}). O mesmo motor de SM-2 e os mesmos
-- GET /treino/fila / POST /treino/{id}/responder atendem as duas origens -
-- ver docs/DECISOES.md D-49 para a justificativa de não criar uma fila/tela
-- paralela.
--
-- `exercicio_id` usa `on delete restrict`, diferente do `on delete cascade`
-- de `lance_id`: apagar em massa o catálogo não pode arrastar silenciosamente
-- o progresso de SM-2 de quem já clicou "Focar" - a exclusão deve falhar alto.

alter table public.fila_treino_espacado
    alter column lance_id drop not null;

alter table public.fila_treino_espacado
    add column if not exists exercicio_id uuid references public.exercicios_taticos(id) on delete restrict;

alter table public.fila_treino_espacado
    add column if not exists origem text not null default 'lance_critico';

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'fila_treino_espacado_origem_check'
    ) then
        alter table public.fila_treino_espacado
            add constraint fila_treino_espacado_origem_check
                check (origem in ('lance_critico', 'exercicio_tatico'));
    end if;

    if not exists (
        select 1 from pg_constraint where conname = 'fila_treino_espacado_user_exercicio_key'
    ) then
        alter table public.fila_treino_espacado
            add constraint fila_treino_espacado_user_exercicio_key
                unique (user_id, exercicio_id);
    end if;

    if not exists (
        select 1 from pg_constraint where conname = 'fila_treino_espacado_origem_xor_check'
    ) then
        alter table public.fila_treino_espacado
            add constraint fila_treino_espacado_origem_xor_check
                check ((lance_id is not null) <> (exercicio_id is not null));
    end if;
end $$;

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
