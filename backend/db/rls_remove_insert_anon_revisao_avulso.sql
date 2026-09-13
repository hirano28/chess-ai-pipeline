-- Fecha o último vestígio de acesso anônimo no schema, registrado como achado
-- em D-23 e não corrigido naquela migration: `revisao_exercicio_avulso` tinha
-- uma policy de INSERT `to anon` (with_check(true)) sem consumidor legítimo —
-- confirmado que o frontend nunca escreve nessa tabela direto (busca em todo
-- `frontend/src` por `.from('revisao_exercicio_avulso')` não achou nada); toda
-- escrita real passa por POST /revisar-avulso/salvar, que usa a service role
-- key e ignora RLS por definição.
--
-- Ver D-24 em docs/DECISOES.md.

drop policy if exists "Permitir insercao publica de revisao_exercicio_avulso"
    on revisao_exercicio_avulso;

NOTIFY pgrst, 'reload schema';
