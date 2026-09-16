-- Auditoria de segurança/operação pós-D-49: o advisor de performance do
-- Supabase (auth_rls_initplan) apontou que toda policy criada em D-19/D-22/
-- D-28/D-32/D-48 chama `auth.uid()` "solto", que o Postgres reavalia LINHA A
-- LINHA em vez de uma vez por query. `(select auth.uid())` vira um initplan,
-- avaliado uma única vez - mesmo resultado, mais rápido em volume. Puramente
-- mecânico: nenhuma regra de isolamento muda, só a forma de escrever a
-- mesma condição. `ALTER POLICY` reescreve USING/WITH CHECK sem precisar de
-- DROP + CREATE (preserva a policy, não há janela sem proteção).

alter policy "Leitura authenticated isolada por dono: analises_hexagono"
    on public.analises_hexagono
    using (user_id = (select auth.uid()));

alter policy "Atualizacao authenticated isolada por dono: anotacoes_pensamento"
    on public.anotacoes_pensamento
    using (exists (
        select 1 from public.partidas
        where partidas.id = anotacoes_pensamento.partida_id
          and partidas.user_id = (select auth.uid())
    ))
    with check (exists (
        select 1 from public.partidas
        where partidas.id = anotacoes_pensamento.partida_id
          and partidas.user_id = (select auth.uid())
    ));

alter policy "Insercao authenticated isolada por dono: anotacoes_pensamento"
    on public.anotacoes_pensamento
    with check (exists (
        select 1 from public.partidas
        where partidas.id = anotacoes_pensamento.partida_id
          and partidas.user_id = (select auth.uid())
    ));

alter policy "Leitura authenticated isolada por dono: anotacoes_pensamento"
    on public.anotacoes_pensamento
    using (exists (
        select 1 from public.partidas
        where partidas.id = anotacoes_pensamento.partida_id
          and partidas.user_id = (select auth.uid())
    ));

alter policy "Leitura authenticated isolada por dono: diagnosticos"
    on public.diagnosticos
    using (exists (
        select 1 from public.lances_criticos
        join public.partidas on partidas.id = lances_criticos.partida_id
        where lances_criticos.id = diagnosticos.lance_id
          and partidas.user_id = (select auth.uid())
    ));

alter policy "usuario le a propria fila de treino"
    on public.fila_treino_espacado
    using (user_id = (select auth.uid()));

alter policy "Leitura authenticated isolada por dono: lances_criticos"
    on public.lances_criticos
    using (exists (
        select 1 from public.partidas
        where partidas.id = lances_criticos.partida_id
          and partidas.user_id = (select auth.uid())
    ));

alter policy "Leitura authenticated isolada por dono: metricas_lichess_partid"
    on public.metricas_lichess_partida
    using (exists (
        select 1 from public.partidas
        where partidas.id = metricas_lichess_partida.partida_id
          and partidas.user_id = (select auth.uid())
    ));

alter policy "Leitura authenticated isolada por dono: partidas"
    on public.partidas
    using (user_id = (select auth.uid()));

alter policy "usuario atualiza o proprio perfil"
    on public.perfis_usuario
    using (user_id = (select auth.uid()))
    with check (user_id = (select auth.uid()));

alter policy "usuario cria o proprio perfil"
    on public.perfis_usuario
    with check (user_id = (select auth.uid()));

alter policy "usuario le o proprio perfil"
    on public.perfis_usuario
    using (user_id = (select auth.uid()));

alter policy "Atualizacao authenticated isolada por dono: perguntas_pendentes"
    on public.perguntas_pendentes
    using (exists (
        select 1 from public.lances_criticos
        join public.partidas on partidas.id = lances_criticos.partida_id
        where lances_criticos.id = perguntas_pendentes.lance_id
          and partidas.user_id = (select auth.uid())
    ))
    with check (exists (
        select 1 from public.lances_criticos
        join public.partidas on partidas.id = lances_criticos.partida_id
        where lances_criticos.id = perguntas_pendentes.lance_id
          and partidas.user_id = (select auth.uid())
    ));

alter policy "Leitura authenticated isolada por dono: perguntas_pendentes"
    on public.perguntas_pendentes
    using (exists (
        select 1 from public.lances_criticos
        join public.partidas on partidas.id = lances_criticos.partida_id
        where lances_criticos.id = perguntas_pendentes.lance_id
          and partidas.user_id = (select auth.uid())
    ));

alter policy "Leitura authenticated isolada por dono: puzzle_atividade"
    on public.puzzle_atividade
    using (user_id = (select auth.uid()));

alter policy "Leitura authenticated isolada por dono: resumo_partida"
    on public.resumo_partida
    using (exists (
        select 1 from public.partidas
        where partidas.id = resumo_partida.partida_id
          and partidas.user_id = (select auth.uid())
    ));

alter policy "Leitura authenticated isolada por dono: revisao_exercicio_avuls"
    on public.revisao_exercicio_avulso
    using (user_id = (select auth.uid()));

alter policy "Leitura authenticated isolada por dono: revisoes_pensamento"
    on public.revisoes_pensamento
    using (exists (
        select 1 from public.partidas
        where partidas.id = revisoes_pensamento.partida_id
          and partidas.user_id = (select auth.uid())
    ));

alter policy "Atualizacao authenticated isolada por dono: sessoes_treino"
    on public.sessoes_treino
    using (user_id = (select auth.uid()))
    with check (user_id = (select auth.uid()));

alter policy "Leitura authenticated isolada por dono: sessoes_treino"
    on public.sessoes_treino
    using (user_id = (select auth.uid()));

alter policy "Leitura authenticated isolada por dono: tempos_lance"
    on public.tempos_lance
    using (exists (
        select 1 from public.partidas
        where partidas.id = tempos_lance.partida_id
          and partidas.user_id = (select auth.uid())
    ));

alter policy "usuario le o proprio uso"
    on public.uso_diario_usuario
    using (user_id = (select auth.uid()));

-- Após rodar no Supabase Dashboard:
-- NOTIFY pgrst, 'reload schema';
