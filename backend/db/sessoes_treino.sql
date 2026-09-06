create table if not exists sessoes_treino (
    id bigint generated always as identity primary key,
    diagnostico_gargalo text not null,
    modulos jsonb not null,
    data_prescrita timestamptz not null default now(),
    data_concluida timestamptz
);

alter table sessoes_treino
    add column if not exists data_concluida timestamptz;
