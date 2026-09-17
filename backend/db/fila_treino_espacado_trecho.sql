-- D-66: os eventos EROSAO passam a ter formato de treino ("Refazer o trecho").
--
-- Diferente do D-49 e do D-55, este NÃO é um quarto valor de `origem`: um card
-- de erosão continua sendo um lance crítico do próprio usuário, apontado por
-- `lance_id`, com `origem = 'lance_critico'`. O que muda o formato é
-- `lances_criticos.tipo_evento`, que já existe desde o D-27 — inventar uma
-- origem nova aqui duplicaria em duas colunas um fato que só uma delas conhece.
--
-- A única coluna nova é o estado do trecho em andamento. Um card de PICO se
-- resolve numa requisição (uma posição, um lance, um veredito); um de EROSAO
-- leva 8 lances do jogador, cada um com a resposta do motor, e precisa
-- sobreviver a fechar o navegador no meio.
--
-- Por que jsonb e não tabela própria: o progresso é sempre lido e escrito
-- inteiro, junto com a linha da fila, e nunca consultado por dentro. É o mesmo
-- critério que colocou `progresso` como jsonb em sessoes_treino (D-54).
--
-- Nullable de propósito: card que ainda não começou, card de PICO e card
-- anterior ao D-66 têm todos `null` aqui, e `normalizar_progresso`
-- (backend/common/treino_trecho.py) lê os três como "o trecho não começou".

alter table public.fila_treino_espacado
    add column if not exists progresso_trecho jsonb;

comment on column public.fila_treino_espacado.progresso_trecho is
  'D-66: estado do trecho em andamento nos cards de EROSAO — SAN já jogados '
  '(alternando jogador/motor) e as leituras de win_percent antes e depois de '
  'cada lance do jogador. Null em card de PICO, em exercício de catálogo e em '
  'trecho ainda não iniciado. A posição corrente NUNCA vem do cliente: é '
  'reconstruída pelo replay destes SAN sobre lances_criticos.fen_antes_lance.';

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
