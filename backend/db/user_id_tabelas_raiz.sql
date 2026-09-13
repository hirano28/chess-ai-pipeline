-- Fundação multi-tenant, Fase A: dono explícito nas 6 tabelas raiz.
--
-- Só as tabelas SEM pai natural ganham user_id. As tabelas filhas herdam o
-- dono pela cadeia de FK que já existe (lances_criticos.partida_id,
-- diagnosticos.lance_id, etc.) — ver D-14 em docs/DECISOES.md.
--
-- A FK para auth.users NÃO entra agora: auth.users está vazia (o Auth do
-- Supabase é Fase B), então nenhuma linha satisfaria a constraint hoje.
-- A adição da FK está no fim deste arquivo, comentada, como Fase B.
--
-- RLS permanece exatamente como está. Isto é preparação de dado, não
-- travamento de acesso.

alter table partidas
    add column if not exists user_id uuid;
alter table analises_hexagono
    add column if not exists user_id uuid;
alter table sessoes_treino
    add column if not exists user_id uuid;
alter table explicacoes_posicao
    add column if not exists user_id uuid;
alter table puzzle_atividade
    add column if not exists user_id uuid;
alter table revisao_exercicio_avulso
    add column if not exists user_id uuid;

-- Backfill do dono único atual (mesmo valor de DEFAULT_USER_ID no ambiente).
update partidas set user_id = '51e682f1-50a7-4360-a40d-f17a5524c49b'
    where user_id is null;
update analises_hexagono set user_id = '51e682f1-50a7-4360-a40d-f17a5524c49b'
    where user_id is null;
update sessoes_treino set user_id = '51e682f1-50a7-4360-a40d-f17a5524c49b'
    where user_id is null;
update explicacoes_posicao set user_id = '51e682f1-50a7-4360-a40d-f17a5524c49b'
    where user_id is null;
update puzzle_atividade set user_id = '51e682f1-50a7-4360-a40d-f17a5524c49b'
    where user_id is null;
update revisao_exercicio_avulso set user_id = '51e682f1-50a7-4360-a40d-f17a5524c49b'
    where user_id is null;

-- Só depois do backfill: nenhuma linha nova pode nascer sem dono.
alter table partidas alter column user_id set not null;
alter table analises_hexagono alter column user_id set not null;
alter table sessoes_treino alter column user_id set not null;
alter table explicacoes_posicao alter column user_id set not null;
alter table puzzle_atividade alter column user_id set not null;
alter table revisao_exercicio_avulso alter column user_id set not null;

-- Fase B (NÃO executar agora — exige conta real em auth.users):
-- alter table partidas add constraint partidas_user_id_fkey
--     foreign key (user_id) references auth.users(id);
-- ...idem para as outras 5 tabelas.

-- NOTIFY pgrst, 'reload schema';
