-- Fase B efetivamente concluída: fecha P-13 removendo o acesso anônimo às 7
-- tabelas que ainda serviam o corpus do dono pra qualquer portador da chave
-- pública (policies `to anon using(true)` de D-16, mantidas de propósito até
-- agora — ver D-22 e P-13 em docs/ESTADO.md). Login passa a ser obrigatório
-- pro dashboard (authGuard ligado em app.routes.ts), então o fluxo anônimo
-- que essas policies existiam pra sustentar deixa de existir.
--
-- As policies de `authenticated` isoladas por dono (D-19) NÃO mudam.
--
-- Ver D-23 em docs/DECISOES.md.

-- ============================================================
-- 1. Remove as 7 policies de leitura pública (anon, using(true))
-- ============================================================

drop policy if exists "Permitir leitura publica de partidas" on partidas;
drop policy if exists "Permitir leitura publica de lances_criticos" on lances_criticos;
drop policy if exists "Permitir leitura publica de diagnosticos" on diagnosticos;
drop policy if exists "Permitir leitura publica de revisao_exercicio_avulso" on revisao_exercicio_avulso;
drop policy if exists "Permitir leitura publica de resumo_partida" on resumo_partida;
drop policy if exists "Permitir leitura publica de analises_hexagono" on analises_hexagono;
drop policy if exists "Permitir leitura publica de sessoes_treino" on sessoes_treino;

-- ============================================================
-- 2. sessoes_treino tinha TAMBÉM um UPDATE anônimo (using(true) E
--    with_check(true)) para o botão "Marcar como concluída" — e NENHUMA
--    policy de UPDATE para `authenticated` existia até agora, porque o
--    fluxo logado nunca precisou (todo mundo usava anon). Sem substituir,
--    o botão quebra pra usuário logado assim que o anon for removido.
-- ============================================================

drop policy if exists "Permitir atualizar data_concluida" on sessoes_treino;

drop policy if exists "Atualizacao authenticated isolada por dono: sessoes_treino"
    on sessoes_treino;
create policy "Atualizacao authenticated isolada por dono: sessoes_treino"
    on sessoes_treino for update
    to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- ============================================================
-- 3. NÃO mexido aqui, e por quê
-- ============================================================
-- revisao_exercicio_avulso ainda tem uma policy de INSERT `to anon` com
-- with_check(true) ("Permitir insercao publica de revisao_exercicio_avulso").
-- Não é o mesmo problema que motivou esta migration (não vaza leitura) e o
-- frontend nunca insere nessa tabela direto — toda escrita passa pelo
-- FastAPI (POST /revisar-avulso/salvar), que já resolve o dono real (D-17).
-- Fica registrado como achado separado em D-23, não corrigido aqui: é escrita
-- anônima direta no Postgres, bypassando o backend por completo, e merece
-- avaliação própria antes de mexer.

-- ============================================================
-- 4. Reload do schema para o PostgREST enxergar as mudanças
-- ============================================================
NOTIFY pgrst, 'reload schema';
