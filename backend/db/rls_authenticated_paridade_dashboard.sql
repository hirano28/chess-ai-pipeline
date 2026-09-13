-- Correção pontual de paridade anon == authenticated nas 6 tabelas de leitura
-- do dashboard "Meu Hexágono" (frontend/src/app/services/supabase.service.ts).
--
-- Descoberta durante o teste manual da Fase B.1 (ver D-15/P-11 em
-- DECISOES.md/ESTADO.md): todas essas tabelas só tinham policy de SELECT
-- para a role `anon` (roles: {anon}), nunca para `authenticated`. O Postgres
-- nega por padrão quando não existe NENHUMA policy aplicável à role da
-- sessão — mesmo com `using(true)` na policy de anon, ela simplesmente não
-- se aplica a quem loga. Resultado: usuário autenticado via Supabase Auth
-- via o dashboard inteiro vazio, enquanto anônimo via tudo normalmente.
--
-- Este arquivo só IGUALA o comportamento: mesma condição (`using(true)`),
-- role nova (`authenticated`), sem filtro nenhum por usuário. NÃO É a Fase
-- B.3 (isolamento por dono, D-14) — quando B.3 travar por usuário, é
-- EXATAMENTE a condição destas policies novas que vai virar
-- `user_id = auth.uid()` (ou o `exists` equivalente subindo a cadeia de FK
-- nas tabelas filha); as policies de `anon` seguem intocadas, como estão
-- hoje, porque nenhuma delas foi tocada aqui.

create policy "Permitir leitura authenticated de analises_hexagono"
    on analises_hexagono for select
    to authenticated
    using (true);

create policy "Permitir leitura authenticated de lances_criticos"
    on lances_criticos for select
    to authenticated
    using (true);

create policy "Permitir leitura authenticated de partidas"
    on partidas for select
    to authenticated
    using (true);

create policy "Permitir leitura authenticated de resumo_partida"
    on resumo_partida for select
    to authenticated
    using (true);

create policy "Permitir leitura authenticated de revisao_exercicio_avulso"
    on revisao_exercicio_avulso for select
    to authenticated
    using (true);

create policy "Permitir leitura authenticated de sessoes_treino"
    on sessoes_treino for select
    to authenticated
    using (true);

-- NOTIFY pgrst, 'reload schema';
