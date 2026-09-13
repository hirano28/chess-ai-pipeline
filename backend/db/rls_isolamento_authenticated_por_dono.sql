-- Fase B.3, segunda parte: isolamento RLS por dono nas tabelas do dashboard.
--
-- Substitui as policies de D-16 (`using(true)`) por filtro real de dono.
-- Só as policies de `authenticated` mudam; as de `anon` ficam intactas.
--
-- Tabelas raiz (com user_id próprio): condição direta user_id = auth.uid().
-- Tabelas filha (sem user_id): condição exists subindo a cadeia de FK até
-- partidas.user_id.
--
-- Ver D-19 em docs/DECISOES.md.

-- ============================================================
-- 1. TABELAS RAIZ — user_id = auth.uid()
-- ============================================================

-- analises_hexagono
drop policy if exists "Permitir leitura authenticated de analises_hexagono"
    on analises_hexagono;
drop policy if exists "Leitura authenticated isolada por dono: analises_hexagono"
    on analises_hexagono;
create policy "Leitura authenticated isolada por dono: analises_hexagono"
    on analises_hexagono for select
    to authenticated
    using (user_id = auth.uid());

-- sessoes_treino
drop policy if exists "Permitir leitura authenticated de sessoes_treino"
    on sessoes_treino;
drop policy if exists "Leitura authenticated isolada por dono: sessoes_treino"
    on sessoes_treino;
create policy "Leitura authenticated isolada por dono: sessoes_treino"
    on sessoes_treino for select
    to authenticated
    using (user_id = auth.uid());

-- partidas
drop policy if exists "Permitir leitura authenticated de partidas"
    on partidas;
drop policy if exists "Leitura authenticated isolada por dono: partidas"
    on partidas;
create policy "Leitura authenticated isolada por dono: partidas"
    on partidas for select
    to authenticated
    using (user_id = auth.uid());

-- revisao_exercicio_avulso
drop policy if exists "Permitir leitura authenticated de revisao_exercicio_avulso"
    on revisao_exercicio_avulso;
drop policy if exists "Leitura authenticated isolada por dono: revisao_exercicio_avulso"
    on revisao_exercicio_avulso for select
    to authenticated
    using (user_id = auth.uid());

-- ============================================================
-- 2. TABELAS FILHA — exists subindo a cadeia de FK
-- ============================================================

-- lances_criticos → partidas.user_id
drop policy if exists "Permitir leitura authenticated de lances_criticos"
    on lances_criticos;
drop policy if exists "Leitura authenticated isolada por dono: lances_criticos"
    on lances_criticos;
create policy "Leitura authenticated isolada por dono: lances_criticos"
    on lances_criticos for select
    to authenticated
    using (
        exists (
            select 1
            from partidas
            where partidas.id = lances_criticos.partida_id
              and partidas.user_id = auth.uid()
        )
    );

-- diagnosticos → lances_criticos.lance_id → partidas.user_id
drop policy if exists "Permitir leitura authenticated de diagnosticos"
    on diagnosticos;
drop policy if exists "Leitura authenticated isolada por dono: diagnosticos"
    on diagnosticos;
create policy "Leitura authenticated isolada por dono: diagnosticos"
    on diagnosticos for select
    to authenticated
    using (
        exists (
            select 1
            from lances_criticos
            join partidas on partidas.id = lances_criticos.partida_id
            where lances_criticos.id = diagnosticos.lance_id
              and partidas.user_id = auth.uid()
        )
    );

-- resumo_partida → partidas.user_id
drop policy if exists "Permitir leitura authenticated de resumo_partida"
    on resumo_partida;
drop policy if exists "Leitura authenticated isolada por dono: resumo_partida"
    on resumo_partida;
create policy "Leitura authenticated isolada por dono: resumo_partida"
    on resumo_partida for select
    to authenticated
    using (
        exists (
            select 1
            from partidas
            where partidas.id = resumo_partida.partida_id
              and partidas.user_id = auth.uid()
        )
    );

-- ============================================================
-- 3. Reload do schema para o PostgREST enxergar as mudanças
-- ============================================================
NOTIFY pgrst, 'reload schema';
