alter table lances_criticos
    add column if not exists tipo_evento text not null default 'PICO';

alter table lances_criticos
    add column if not exists numero_lance_fim integer;
