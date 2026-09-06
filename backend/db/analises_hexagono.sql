create table if not exists analises_hexagono (
    id bigint generated always as identity primary key,
    data_analise timestamptz not null default now(),
    metricas jsonb not null,
    narrativa text,
    gargalo_sistemico_atual text
);
