-- D-57: `partidas` ganha a cadência (ritmo de jogo), que faltava desde sempre.
--
-- O porquê está em docs/ESTADO.md §3: 74% do corpus analisado é blitz de 3 a 5
-- minutos, e não havia coluna de cadência — não dava nem para filtrar. Toda
-- conclusão do Hexágono sobre "o gargalo do jogador" saía misturada com o
-- efeito do relógio. A tag mais frequente ser `calculo_tatico_deficiente`
-- podia significar "calcula mal" ou "joga rápido demais", e não havia como
-- distinguir. Esta coluna é o pré-requisito para separar as duas coisas.
--
-- `DESCONHECIDA` é um valor legítimo e frequente: parte das partidas do
-- Lichess vem sem header `TimeControl`. Ver backend/common/cadencia.py sobre
-- por que aqui NÃO existe fallback para 300s (chutar contaminaria justamente a
-- estatística que a coluna veio limpar).

alter table public.partidas
    add column if not exists cadencia text;

alter table public.partidas
    add column if not exists tempo_base_segundos integer;

alter table public.partidas
    add column if not exists incremento_segundos integer;

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'partidas_cadencia_check'
    ) then
        alter table public.partidas
            add constraint partidas_cadencia_check
                check (cadencia is null or cadencia in (
                    'BULLET', 'BLITZ', 'RAPIDA', 'CLASSICA',
                    'CORRESPONDENCIA', 'DESCONHECIDA'
                ));
    end if;
end $$;

comment on column public.partidas.cadencia is
  'Ritmo de jogo derivado do header TimeControl do PGN (D-57), pelos cortes do '
  'Lichess sobre base + 40*incremento. DESCONHECIDA quando o PGN não traz o '
  'header — valor legítimo, não erro. Preenchida no insert (common_ingestao.'
  'insert_game e analisar_pgn_avulso.inserir_partida) e, para o acervo '
  'anterior, por backend/ingestao/backfill_cadencia.py.';

-- Consultar "só as partidas clássicas" é o caso de uso que motivou a coluna.
create index if not exists idx_partidas_cadencia on public.partidas (cadencia);

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
