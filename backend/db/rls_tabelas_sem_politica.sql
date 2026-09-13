-- Fecha as 6 tabelas que estavam SEM RLS nenhum (a P-2 histórica).
--
-- Incidente: com `rls_ligado = false`, qualquer portador da chave `anon` —
-- que é pública, vai no bundle do frontend — lia essas tabelas inteiras,
-- incluindo texto pessoal (`pergunta_texto`, `texto_pensamento`). Confirmado
-- por curl real antes desta migration: anon, uma conta de teste sem dado
-- próprio e a conta dona recebiam TODAS as mesmas linhas.
--
-- Mesmo padrão de D-19: raiz filtra por user_id = auth.uid(); filha filtra
-- por exists subindo a cadeia de FK até partidas.user_id.
--
-- NENHUMA policy de `anon` é criada aqui, de propósito: são 6 tabelas de dado
-- pessoal, e manter `using(true)` pra anon seria manter o vazamento. O
-- frontend só lê duas delas direto (perguntas_pendentes e
-- anotacoes_pensamento), ambas no cartão "Perguntas pendentes" — que passa a
-- exigir login. As outras 4 nenhuma tela lê: só o backend toca nelas, e ele
-- usa a service role key, que ignora RLS.
--
-- Ver D-22 em docs/DECISOES.md.

-- ============================================================
-- 1. TABELA RAIZ — user_id = auth.uid()
-- ============================================================

-- puzzle_atividade (tabela raiz do D-14, com user_id próprio)
alter table puzzle_atividade enable row level security;
drop policy if exists "Leitura authenticated isolada por dono: puzzle_atividade"
    on puzzle_atividade;
create policy "Leitura authenticated isolada por dono: puzzle_atividade"
    on puzzle_atividade for select
    to authenticated
    using (user_id = auth.uid());

-- ============================================================
-- 2. TABELAS FILHA — exists até partidas.user_id
-- ============================================================

-- anotacoes_pensamento → partidas.user_id
-- Precisa de insert/update além de select: é a única escrita que o frontend
-- faz direto no Postgres (upsert de resposta em `responderPergunta`).
alter table anotacoes_pensamento enable row level security;
drop policy if exists "Leitura authenticated isolada por dono: anotacoes_pensamento"
    on anotacoes_pensamento;
create policy "Leitura authenticated isolada por dono: anotacoes_pensamento"
    on anotacoes_pensamento for select
    to authenticated
    using (
        exists (
            select 1
            from partidas
            where partidas.id = anotacoes_pensamento.partida_id
              and partidas.user_id = auth.uid()
        )
    );

drop policy if exists "Insercao authenticated isolada por dono: anotacoes_pensamento"
    on anotacoes_pensamento;
create policy "Insercao authenticated isolada por dono: anotacoes_pensamento"
    on anotacoes_pensamento for insert
    to authenticated
    with check (
        exists (
            select 1
            from partidas
            where partidas.id = anotacoes_pensamento.partida_id
              and partidas.user_id = auth.uid()
        )
    );

drop policy if exists "Atualizacao authenticated isolada por dono: anotacoes_pensamento"
    on anotacoes_pensamento;
create policy "Atualizacao authenticated isolada por dono: anotacoes_pensamento"
    on anotacoes_pensamento for update
    to authenticated
    using (
        exists (
            select 1
            from partidas
            where partidas.id = anotacoes_pensamento.partida_id
              and partidas.user_id = auth.uid()
        )
    )
    with check (
        exists (
            select 1
            from partidas
            where partidas.id = anotacoes_pensamento.partida_id
              and partidas.user_id = auth.uid()
        )
    );

-- revisoes_pensamento → partidas.user_id
alter table revisoes_pensamento enable row level security;
drop policy if exists "Leitura authenticated isolada por dono: revisoes_pensamento"
    on revisoes_pensamento;
create policy "Leitura authenticated isolada por dono: revisoes_pensamento"
    on revisoes_pensamento for select
    to authenticated
    using (
        exists (
            select 1
            from partidas
            where partidas.id = revisoes_pensamento.partida_id
              and partidas.user_id = auth.uid()
        )
    );

-- tempos_lance → partidas.user_id
alter table tempos_lance enable row level security;
drop policy if exists "Leitura authenticated isolada por dono: tempos_lance"
    on tempos_lance;
create policy "Leitura authenticated isolada por dono: tempos_lance"
    on tempos_lance for select
    to authenticated
    using (
        exists (
            select 1
            from partidas
            where partidas.id = tempos_lance.partida_id
              and partidas.user_id = auth.uid()
        )
    );

-- metricas_lichess_partida → partidas.user_id
alter table metricas_lichess_partida enable row level security;
drop policy if exists "Leitura authenticated isolada por dono: metricas_lichess_partida"
    on metricas_lichess_partida;
create policy "Leitura authenticated isolada por dono: metricas_lichess_partida"
    on metricas_lichess_partida for select
    to authenticated
    using (
        exists (
            select 1
            from partidas
            where partidas.id = metricas_lichess_partida.partida_id
              and partidas.user_id = auth.uid()
        )
    );

-- ============================================================
-- 3. TABELA NETA — perguntas_pendentes → lances_criticos → partidas.user_id
-- ============================================================

alter table perguntas_pendentes enable row level security;
drop policy if exists "Leitura authenticated isolada por dono: perguntas_pendentes"
    on perguntas_pendentes;
create policy "Leitura authenticated isolada por dono: perguntas_pendentes"
    on perguntas_pendentes for select
    to authenticated
    using (
        exists (
            select 1
            from lances_criticos
            join partidas on partidas.id = lances_criticos.partida_id
            where lances_criticos.id = perguntas_pendentes.lance_id
              and partidas.user_id = auth.uid()
        )
    );

-- O frontend marca a pergunta como RESPONDIDA depois de salvar a anotação.
drop policy if exists "Atualizacao authenticated isolada por dono: perguntas_pendentes"
    on perguntas_pendentes;
create policy "Atualizacao authenticated isolada por dono: perguntas_pendentes"
    on perguntas_pendentes for update
    to authenticated
    using (
        exists (
            select 1
            from lances_criticos
            join partidas on partidas.id = lances_criticos.partida_id
            where lances_criticos.id = perguntas_pendentes.lance_id
              and partidas.user_id = auth.uid()
        )
    )
    with check (
        exists (
            select 1
            from lances_criticos
            join partidas on partidas.id = lances_criticos.partida_id
            where lances_criticos.id = perguntas_pendentes.lance_id
              and partidas.user_id = auth.uid()
        )
    );

-- ============================================================
-- 4. NÃO mexidas aqui, e por quê
-- ============================================================
-- explicacoes_posicao, livros_chunks e indice_conceitual aparecem na mesma
-- varredura (RLS ligado, zero policies), mas NÃO vazam: sem nenhuma policy, o
-- Postgres nega por padrão — confirmado por curl (0 linhas para anon, para
-- conta sem dado e para a conta dona). Ficam fechadas de propósito:
--   - explicacoes_posicao: o histórico do Explicador chega pelo FastAPI
--     (service role), nenhuma tela lê esta tabela direto.
--   - livros_chunks / indice_conceitual: corpus de RAG, sem dono por linha
--     (não têm user_id nem caminho até partidas) — isolamento por usuário não
--     se aplica. Só o backend lê, via service role.

-- ============================================================
-- 5. Reload do schema para o PostgREST enxergar as mudanças
-- ============================================================
NOTIFY pgrst, 'reload schema';
