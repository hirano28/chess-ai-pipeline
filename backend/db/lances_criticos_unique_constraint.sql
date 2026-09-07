do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'lances_criticos_partida_lance_unique'
    ) then
        alter table lances_criticos
            add constraint lances_criticos_partida_lance_unique
                unique (partida_id, numero_lance);
    end if;
end $$;
