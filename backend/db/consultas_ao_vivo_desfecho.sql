-- D-68: o desfecho de cada consulta ao vivo — o que o jogador jogou DEPOIS de
-- pedir ajuda, e quanto isso custou.
--
-- Sem isto a consulta é um fim em si: o sistema registra a dúvida e nunca fica
-- sabendo o que aconteceu com ela. `casar_consultas_ao_vivo.py` roda no pipeline
-- diário, depois da coleta e do Stockfish, e procura a partida real que passou
-- pela posição consultada.
--
-- `casamento_status`:
--   'pendente'    — a partida ainda não foi coletada (o normal no mesmo dia);
--   'casada'      — achada; os campos de desfecho estão preenchidos;
--   'sem_partida' — procurada por dias sem sucesso (partida em outro site, OTB,
--                   variante não coletada). Parar de procurar é o certo: a
--                   ausência também é informação, e insistir para sempre gastaria
--                   uma consulta ao banco por dia por nada.
--
-- `partida_externa_id` vem da sincronização com o Lichess/Chess.com (D-69) e,
-- quando existe, casa direto por `partidas.external_id` sem depender da janela
-- de horário.
--
-- FKs com `on delete set null`: reprocessar uma partida (R7) apaga os lances
-- críticos e pode apagar a partida; a consulta continua existindo, só perde o
-- vínculo — e volta a ser casável.

alter table public.consultas_ao_vivo
    add column if not exists partida_externa_id text,
    add column if not exists casamento_status text not null default 'pendente',
    add column if not exists partida_id uuid references public.partidas(id) on delete set null,
    add column if not exists lance_jogado text,
    add column if not exists queda_win_percent_jogado numeric,
    add column if not exists lance_jogado_era_candidato boolean,
    add column if not exists lance_jogado_era_o_melhor boolean,
    add column if not exists lance_critico_id uuid references public.lances_criticos(id) on delete set null,
    add column if not exists casada_em timestamptz;

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'consultas_ao_vivo_casamento_status_check'
    ) then
        alter table public.consultas_ao_vivo
            add constraint consultas_ao_vivo_casamento_status_check
                check (casamento_status in ('pendente', 'casada', 'sem_partida'));
    end if;
end $$;

-- Índices das FKs (a lição do `posicional_id` sem índice) e do filtro diário.
create index if not exists consultas_ao_vivo_partida_id_idx
  on public.consultas_ao_vivo (partida_id);
create index if not exists consultas_ao_vivo_lance_critico_id_idx
  on public.consultas_ao_vivo (lance_critico_id);
create index if not exists consultas_ao_vivo_pendentes_idx
  on public.consultas_ao_vivo (casamento_status) where casamento_status = 'pendente';

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
