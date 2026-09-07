alter table tempos_lance
    add column if not exists cor text;

alter table tempos_lance
    drop constraint if exists tempos_lance_partida_id_numero_lance_key;

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'tempos_lance_cor_check'
    ) then
        alter table tempos_lance
            add constraint tempos_lance_cor_check
                check (cor in ('BRANCAS', 'PRETAS'));
    end if;

    if not exists (
        select 1 from pg_constraint where conname = 'tempos_lance_partida_lance_cor_unique'
    ) then
        alter table tempos_lance
            add constraint tempos_lance_partida_lance_cor_unique
                unique (partida_id, numero_lance, cor);
    end if;
end $$;
