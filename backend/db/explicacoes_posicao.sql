-- Tabela para persistir o resultado do Explicador de Posição.
-- Fecha a pendência P-10 (ESTADO.md): antes desta tabela, /explicar-posicao
-- gerava a explicação (Stockfish + Gemini) e a descartava assim que a
-- resposta HTTP voltava - sem histórico, sem poder reabrir uma explicação
-- anterior. Schema similar a revisao_exercicio_avulso: fen + resultado
-- completo + created_at.
--
-- 'resultado' guarda o dict inteiro devolvido por explicar_posicao() (mesmo
-- shape de ExplicarPosicaoResponse), incluindo fen/lado_analisado - lado_
-- analisado também vira coluna própria só para filtrar/exibir sem precisar
-- desempacotar o jsonb.

create table if not exists explicacoes_posicao (
    id uuid primary key default gen_random_uuid(),
    fen text not null,
    lado_analisado text,
    resultado jsonb not null,
    created_at timestamptz not null default now()
);

-- RLS habilitado sem policy: só o backend (service role, que ignora RLS)
-- grava e lê esta tabela - nenhum cliente com a chave anon a acessa direto,
-- então isso não bloqueia nada em uso real e evita que esta tabela nova
-- entre para a lista de tabelas expostas (ver P-2 em ESTADO.md).
alter table explicacoes_posicao enable row level security;

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
