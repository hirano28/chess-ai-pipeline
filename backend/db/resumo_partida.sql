-- Tabela para armazenar o resumo narrativo de cada partida.
-- Gerado por gerar_resumo_partida.py a partir dos dados já existentes
-- (lances_criticos + diagnosticos + metricas_lichess + tempos_lance).

create table if not exists resumo_partida (
    id bigint generated always as identity primary key,
    partida_id text not null references partidas(id) on delete cascade,
    narrativa text not null,
    pontos_criticos jsonb not null default '[]',
    momento_chave_estrategico text,
    created_at timestamptz not null default now(),
    constraint resumo_partida_partida_id_unique unique (partida_id)
);

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';

