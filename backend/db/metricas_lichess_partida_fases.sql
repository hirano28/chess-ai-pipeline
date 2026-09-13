alter table metricas_lichess_partida
    add column if not exists precisao_abertura numeric;

alter table metricas_lichess_partida
    add column if not exists precisao_meiojogo numeric;

alter table metricas_lichess_partida
    add column if not exists precisao_final numeric;
