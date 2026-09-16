-- D-49: catálogo de exercícios táticos importado do dump público de puzzles
-- do Lichess (CC0), taggeado na NOSSA taxonomia (HEXAGON_CATEGORIES, ver
-- backend/agentes/agente2_analista.py), não na taxonomia solta de temas do
-- Lichess. Populado ocasionalmente/manualmente por
-- backend/rag/importar_exercicios_taticos.py — não é dado de usuário, é
-- corpus compartilhado (mesmo papel de indice_conceitual/livros_chunks).
--
-- `fen` já é a posição REAL a resolver: o import aplica o primeiro lance do
-- CSV do Lichess (o "lance de preparo" automático do adversário) ao FEN
-- bruto antes de gravar. Não guardamos a "resposta certa" do puzzle - a
-- qualidade da resposta do usuário é avaliada dinamicamente pelo Stockfish
-- (avaliar_lance_avulso), igual ao que já acontece com lances_criticos.
--
-- GESTAO_DE_TEMPO não tem puzzles: o Lichess não tem tema equivalente a
-- gestão de tempo (posições são estáticas, sem relógio) - achado documentado
-- em D-49/docs/DECISOES.md, não uma omissão.

create table if not exists public.exercicios_taticos (
  id uuid primary key default gen_random_uuid(),
  puzzle_id_lichess text not null unique,
  fen text not null,
  categoria_hexagono text not null check (categoria_hexagono in (
    'TATICA', 'ESTRATEGIA', 'FINAIS', 'ESTRUTURA_DE_PEOES', 'GESTAO_DE_TEMPO', 'CALCULO'
  )),
  temas_lichess text[] not null,
  rating integer,
  popularidade integer,
  criado_em timestamptz not null default now()
);

comment on table public.exercicios_taticos is
  'Catálogo de exercícios táticos (D-49), importado do dump público de '
  'puzzles do Lichess e re-taggeado em HEXAGON_CATEGORIES. Corpus '
  'compartilhado, sem user_id - alimenta POST /treino/foco/{categoria}, que '
  'insere exercícios na fila de repetição espaçada (fila_treino_espacado).';

alter table public.exercicios_taticos enable row level security;

-- Sem nenhuma policy, de propósito - mesmo padrão de indice_conceitual e
-- livros_chunks (backend/db/rls_tabelas_sem_politica.sql): catálogo
-- compartilhado sem dono por linha, sem policy o Postgres nega tudo por
-- padrão. Só o backend, com a service role, lê/escreve esta tabela.

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
