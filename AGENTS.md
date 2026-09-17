---
doc: AGENTS.md
papel: PONTO DE ENTRADA CANÔNICO para qualquer agente de IA neste repositório
vale_para: Claude Code, Gravity/Antigravity, Cursor, Codex e qualquer outro
verificado_em: 2026-09-16
---

# AGENTS.md — Contrato de trabalho para agentes de IA

Este é o **único ponto de entrada canônico**. `CLAUDE.md` aponta para cá; todo
outro documento de conhecimento vive em `docs/` e é referenciado pelo roteador
da seção 3. Se dois arquivos se contradisserem, **este vence**.

Projeto: pipeline de treino de xadrez de Edson Hirano (`hirano28`), hoje com um
único usuário real de dado (todo o acervo de partidas pertence a
`edson.hirano.dev@gmail.com`).

**O código é multiusuário desde o D-28** e o objetivo declarado é chegar a
produto de mercado. Não trate nada aqui como "ferramenta pessoal, pode
simplificar": o pipeline em lote percorre `perfis_usuario` e atribui `user_id`
linha a linha, as tabelas raiz têm RLS isolada por dono, e as rotas da API
tiram o dono da sessão sem fallback. Uma escrita que assuma "só existe um
usuário" é bug de vazamento esperando o segundo cadastro. O que ainda **não**
existe é o resto de um produto comercial — cobrança, planos, onboarding de
desconhecido, suporte —, e é isso que separa o estado atual do objetivo.

---

## 1. O que o sistema faz, em um parágrafo

Partidas jogadas no Lichess e no Chess.com são coletadas automaticamente, o
Stockfish acha os lances ruins, o Gemini diagnostica a causa de cada erro usando
um vocabulário fechado de 16 tags, a estatística agregada aponta o gargalo atual,
um RAG sobre livros de xadrez cita a teoria pertinente, e uma sprint de treino é
prescrita — e, desde o D-54, **executada dentro do produto**, o que é o que fecha
o loop adaptativo. O treino tem duas formas: a fila diária de repetição espaçada
(SM-2 sobre os próprios erros do jogador, mais dois catálogos de exercícios) e a
sessão de treino focado, que é o formato longo com começo e fim. Em paralelo,
três ferramentas web interativas (Laboratório de Raciocínio, Explicador de
Posição, Analisador de Partida) dão feedback sob demanda.

Duas metades, portanto: **diagnosticar** (o pipeline acima) e **treinar**
(D-48 em diante). Um agente que só leu a primeira metade vai propor de novo
coisas que já existem.

---

## 2. Antes de escrever qualquer código

1. **Leia o arquivo que o roteador (seção 3) indicar para a sua tarefa.** Não leia
   tudo: os documentos são autocontidos e feitos para leitura seletiva.
2. **Não confie em número, contagem ou status que esteja em qualquer documento sem
   data de verificação.** Estado factual muda; ele mora em `docs/ESTADO.md` e só lá.
3. **Confirme o formato real de qualquer API externa antes de escrever o parser.**
   Já assumimos errado o formato de resposta do Lichess e do Chess.com mais de uma
   vez. Faça uma chamada real e imprima antes de codificar a lógica definitiva.

---

## 3. Roteador — qual documento ler para cada tarefa

| Sua tarefa | Leia |
|---|---|
| Entender componentes, fluxo de dados, endpoints, deploy | `docs/ARQUITETURA.md` |
| Mexer em tabela, coluna, query, migração, vocabulário de tags | `docs/BANCO.md` |
| Rodar/depurar script, pipeline, teste, variável de ambiente | `docs/OPERACAO.md` |
| Saber **por que** algo foi feito daquele jeito antes de mudar | `docs/DECISOES.md` |
| Saber o estado real hoje (números, pendências, o que está quebrado) | `docs/ESTADO.md` |
| Planejar próximas fases do produto | `docs/ROADMAP_EVOLUCAO.md` — as Fases 12–18 dele **já foram entregues**; leia o cabeçalho antes de tratar qualquer item como pendente |
| Entender a rotina de uso pela ótica do dono (humano, não agente) | `docs/GUIA_DO_PROJETO.md` |
| Mexer na rubrica dos 8 passos | `docs/GUIA_GUESS_THE_MOVE.md` — **leia a regra R9 antes** |

---

## 4. Regras invioláveis

Cada regra tem um ID estável (R1…R10). Cite o ID em commits e comentários quando
a regra for o motivo de uma escolha.

**R1 — Vocabulário de 16 tags é fechado.** As tags de `diagnosticos.tags_falha`
são exatamente: `calculo_tatico_deficiente`, `seguranca_do_rei`,
`perda_de_iniciativa`, `erro_tecnico_de_final`, `fraqueza_estrutural_de_peoes`,
`negligencia_profilatica`, `gestao_de_tempo_ruim`,
`abertura_de_linhas_desfavoravel`, `simplificacao_prematura`,
`avaliacao_posicional_incorreta`, `troca_desfavoravel`,
`falta_de_coordenacao_de_pecas`, `ataque_prematuro`, `passividade_excessiva`,
`visao_em_tunel`, `perda_de_material`. Não crie tag nova sem antes provar com
query real no banco que o conceito não está coberto — já supusemos uma lacuna
que não existia.

**R2 — Validação anti-alucinação é obrigatória** sempre que o LLM cita dado
técnico verificável (lance SAN, página de livro, nome de capítulo). Padrão:
extrair as menções por regex → comparar com a fonte real → se divergir, retry de
correção → se falhar de novo, fallback não-LLM que formata o dado real
literalmente. Referência de implementação: `backend/agentes/revisar_pensamento.py`.

**R3 — Stockfish é subprocesso único e precisa de lock.** Qualquer endpoint ou
script que possa chamar o motor concorrentemente usa `threading.Lock`
(`_state["engine_lock"]` na API). Sem isso o diálogo com o subprocesso corrompe e
trava em silêncio, sem erro e sem timeout.

**R4 — Multiprocessing usa um único contexto `spawn` explícito.** No Linux/Cloud
Run, `ctx = multiprocessing.get_context("spawn")` e então `ctx.Queue()` **e**
`ctx.Process(...)` a partir do mesmo `ctx`. Misturar com `multiprocessing.Queue()`
global gera `SemLock created in a fork context is being shared with a process in
a spawn context`.

**R5 — Depois de qualquer DDL no Supabase, rode `NOTIFY pgrst, 'reload schema';`**
Sem isso a API REST não enxerga a coluna nova e devolve `PGRST204`.

**R6 — `SUPABASE_URL` nunca termina em `/rest/v1/`.** A biblioteca acrescenta
isso sozinha. O sintoma de errar é `PGRST125: Invalid path`. Já aconteceu 3 vezes.

**R7 — Antes de reprocessar algo, resete `status_processamento = 'pendente'` e
apague os registros derivados.** Caso contrário dado antigo se mistura com novo.

**R8 — Módulo de teste novo precisa ser registrado em 2 lugares**, porque as
listas são mantidas à mão: `docs/OPERACAO.md` (seção 2) e
`.github/workflows/deploy-backend.yml`. Esquecer o segundo faz o CI passar sem
nunca rodar o teste — foi o que aconteceu com `backend.common.test_notacao_pt`.

**R9 — `docs/GUIA_GUESS_THE_MOVE.md` é asset de runtime, não é documentação.**
`backend/agentes/revisar_pensamento.py` lê o arquivo em tempo de execução e parseia
os cabeçalhos `## N. Título`. Precisa haver **exatamente 8 passos numerados, na
ordem 1..8**, porque eles são pareados posicionalmente com `CHECKLIST_KEYS`.
Reordenar, remover, ou acrescentar um cabeçalho numerado quebra a rubrica e o
endpoint `/guia-passos`. O corpo do texto pode ser reescrito à vontade.

**R10 — Cloud Run precisa de `--memory 2Gi --cpu 2 --no-cpu-throttling`.** Com
512 MiB o Stockfish em depth 16 estoura e o container leva `SIGKILL`, deixando a
partida órfã em `processando`. Sem `--no-cpu-throttling` as background tasks
congelam assim que o HTTP 202 é respondido.

---

## 5. Comandos essenciais

```bash
# Testes do backend (a lista completa e atual está em docs/OPERACAO.md)
python -m unittest backend.api.test_api_server   # exemplo de módulo único

# Testes do frontend
cd frontend && npx ng test --no-watch

# Subir localmente
uvicorn backend.api.api_server:app --reload --port 8000
cd frontend && npm start
```

---

## 6. Protocolo de atualização deste conhecimento

Este repositório é trabalhado por **mais de um agente de IA em sessões
alternadas**. O conhecimento só continua útil se todo agente seguir o mesmo
protocolo ao encerrar um trabalho relevante:

1. **Fato factual mudou?** (contagem, status, pendência resolvida) → atualize
   `docs/ESTADO.md` e a data `verificado_em` no topo dele. Só lá.
2. **Decisão de design nova ou revertida?** → acrescente uma entrada `D-n` em
   `docs/DECISOES.md`. Nunca reescreva uma decisão antiga: acrescente a nova
   marcando a anterior como substituída.
3. **Componente, endpoint ou tabela novo?** → `docs/ARQUITETURA.md` ou
   `docs/BANCO.md`.
4. **Comando, variável de ambiente ou armadilha operacional nova?** →
   `docs/OPERACAO.md`.
5. **Regra que outro agente pode violar sem perceber?** → nova regra `Rn` aqui,
   na seção 4.

**Não crie arquivo de handoff por sessão.** Documento cronológico do tipo "o que
fizemos nesta sessão" envelhece em dias, duplica fato e passa a contradizer os
outros — foi exatamente esse o problema que esta estrutura veio resolver. O
histórico cronológico já existe e se chama `git log`.
