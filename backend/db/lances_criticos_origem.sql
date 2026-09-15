alter table lances_criticos
    add column if not exists origem text not null default 'GRAVIDADE';

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'lances_criticos_origem_check'
    ) then
        alter table lances_criticos
            add constraint lances_criticos_origem_check
                check (origem in ('GRAVIDADE', 'ANOTACAO'));
    end if;
end $$;

notify pgrst, 'reload schema';
