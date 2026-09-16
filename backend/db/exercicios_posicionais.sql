-- D-55: catálogo de exercícios POSICIONAIS, extraído do banco público de
-- broadcasts do Lichess (partidas OTB reais de torneio, com jogadores
-- titulados). Populado por backend/rag/importar_exercicios_posicionais.py.
--
-- Por que uma tabela separada de `exercicios_taticos` e não uma coluna `fonte`
-- ali: estes exercícios são, por construção, os que NÃO são táticos — o filtro
-- exige que o melhor lance seja quieto (sem captura, sem xeque, sem promoção).
-- Guardá-los numa tabela chamada "exercicios_taticos" seria exatamente o tipo
-- de mentira silenciosa que o D-49 recusou ao deixar ESTRATEGIA vazia em vez
-- de remapear temas de puzzle. Além disso, a procedência (quem jogou, em que
-- torneio, com quanto relógio) só faz sentido aqui e viraria coluna nula na
-- outra tabela — e é justamente ela que permite dizer, depois de o usuário
-- responder, "isto foi Aroshidze x Garriga, Catalunya 2022".
--
-- Igual ao D-49, NÃO guardamos a resposta certa. O Lichess anota "Mistake. a4
-- was best.", mas quem avalia a resposta continua sendo o Stockfish em tempo
-- real (avaliar_lance_avulso). Isso resolve de graça o problema de posição
-- posicional ter vários lances bons: não comparamos com um gabarito, medimos
-- a queda de avaliação — qualquer lance que não perca nada passa.
--
-- Licença: os broadcasts do Lichess são CC BY-SA 4.0 (os puzzles do D-49 são
-- CC0 — não é a mesma licença). Exige atribuição, e por isso a tela de treino
-- credita a origem ao revelar a partida.

create table if not exists public.exercicios_posicionais (
  id uuid primary key default gen_random_uuid(),
  jogo_url text not null,
  -- ply (meio-lance) é a identidade dentro da partida: `numero_lance` sozinho
  -- repetiria quando os dois jogadores erram no mesmo lance cheio.
  ply integer not null,
  numero_lance integer not null,
  fen text not null,
  categoria_hexagono text not null check (categoria_hexagono in (
    'TATICA', 'ESTRATEGIA', 'FINAIS', 'ESTRUTURA_DE_PEOES', 'GESTAO_DE_TEMPO', 'CALCULO'
  )),
  severidade text not null check (severidade in ('Mistake', 'Blunder')),
  -- Quanto o erro real custou, em centipeões, na avaliação do Lichess. Serve
  -- de filtro de qualidade no import e de contexto na revelação.
  queda_centipeoes integer not null,
  -- Relógio de quem errou, em segundos. É o que torna GESTAO_DE_TEMPO possível
  -- (o D-49 concluiu, corretamente, que puzzle não serve: posição estática não
  -- tem relógio). Null quando o PGN não trouxe [%clk].
  segundos_restantes integer,
  brancas text,
  pretas text,
  evento text,
  data_partida date,
  criado_em timestamptz not null default now(),
  unique (jogo_url, ply)
);

comment on table public.exercicios_posicionais is
  'Catálogo de exercícios "ache o melhor lance" em posições NÃO táticas '
  '(D-55), extraídas de partidas OTB reais do banco de broadcasts do Lichess '
  '(CC BY-SA 4.0). Corpus compartilhado, sem user_id, mesmo papel de '
  'exercicios_taticos/indice_conceitual. Alimenta POST /treino/foco/{categoria} '
  'e o bloco de prática das sessões de treino (D-54).';

comment on column public.exercicios_posicionais.segundos_restantes is
  'Relógio real do jogador que errou. Preenchido só na categoria '
  'GESTAO_DE_TEMPO, onde o exercício é cronometrado com o mesmo tempo que ele '
  'tinha — a pressão é o exercício, não um detalhe de exibição.';

create index if not exists idx_exercicios_posicionais_categoria
  on public.exercicios_posicionais (categoria_hexagono);

alter table public.exercicios_posicionais enable row level security;

-- Sem nenhuma policy, de propósito - mesmo padrão de exercicios_taticos,
-- indice_conceitual e livros_chunks (backend/db/rls_tabelas_sem_politica.sql):
-- catálogo compartilhado sem dono por linha; sem policy o Postgres nega tudo
-- por padrão e só o backend, com a service role, lê/escreve.

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
