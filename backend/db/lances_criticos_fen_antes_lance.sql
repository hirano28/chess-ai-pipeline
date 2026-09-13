-- D-27: miniatura de tabuleiro nas perguntas pendentes.
-- FEN da posição imediatamente antes do lance crítico (ou do início da janela,
-- para tipo_evento = EROSAO). Nullable: linhas antigas são preenchidas por
-- backend/db/backfill_fen_lances_criticos.py, linhas novas vêm já preenchidas
-- por backend/analise_engine/analisar_partidas.py.
alter table public.lances_criticos
  add column if not exists fen_antes_lance text;

comment on column public.lances_criticos.fen_antes_lance is
  'FEN da posição imediatamente antes do lance (ou do início da janela, para EROSAO). Alimenta a miniatura de tabuleiro nas perguntas pendentes (D-27).';
