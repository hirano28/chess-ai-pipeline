/**
 * Dirige a aplicação no navegador de verdade: clica, digita e confere o que
 * saiu pela rede (D-83).
 *
 * É o irmão do `capturar-telas.mjs`, e a divisão de trabalho é deliberada:
 * aquele FOTOGRAFA e não afirma nada, porque um script de tour cheio de
 * asserções sobre a UI já existiu aqui e quebrou na primeira mudança de tela.
 * Este aqui afirma — mas só sobre CONTRATO, nunca sobre aparência:
 *
 *   - seletores são `[data-casa]` e `role`/`aria-*`, não classe de estilo;
 *   - a asserção é sobre o corpo da requisição que o clique produziu, não
 *     sobre o texto que apareceu na tela.
 *
 * Isso é o que o teste unitário não alcança. O caso que motivou a ferramenta:
 * no D-82 o "clicar no tabuleiro responde" foi entregue verificado por teste
 * unitário (que chama o método do componente) e por uma chamada direta à API
 * (que não passa pelo navegador). Nenhum dos dois exercita o gesto real —
 * clicar na peça, clicar na casa — nem prova que o `lance_uci` que chega ao
 * backend corresponde às casas clicadas.
 *
 * SEGURO POR PADRÃO: a resposta do card é INTERCEPTADA e respondida com um
 * resultado falso, então rodar isto não suja a sua fila de repetição espaçada.
 * Com `--valendo` a requisição passa e o card é de fato respondido — aí o
 * agendamento do SM-2 muda, e aquela revisão não aconteceu de verdade.
 *
 * Erro de console reprova a execução (exit 1). O `capturar-telas.mjs` só
 * avisa; aqui o silêncio no console faz parte do contrato.
 *
 * Pré-requisitos: os mesmos do capturar-telas.mjs (ver docs/OPERACAO.md §8).
 *
 * Uso:
 *   node tools/dirigir-tela.mjs sessao.json                  # roteiro padrão, seguro
 *   node tools/dirigir-tela.mjs sessao.json treino-clique
 *   node tools/dirigir-tela.mjs sessao.json treino-clique --valendo
 */
import { chromium } from 'playwright';
import { Chess } from 'chess.js';
import fs from 'node:fs';
import path from 'node:path';

const BASE = process.env.BASE_URL ?? 'http://localhost:4200';
const API = process.env.API_URL ?? 'http://localhost:8000';
const PROJETO_SUPABASE = 'pmzmershonrqzwbmhaco';
const CHAVE_SESSAO = `sb-${PROJETO_SUPABASE}-auth-token`;
const ESPERA_MS = Number(process.env.ESPERA_MS ?? 4500);

const argv = process.argv.slice(2);
const valendo = argv.includes('--valendo');
const [caminhoSessao, roteiroPedido = 'treino-clique'] = argv.filter((a) => !a.startsWith('--'));

if (!caminhoSessao) {
  console.error('uso: node tools/dirigir-tela.mjs <sessao.json> [roteiro] [--valendo]');
  process.exit(1);
}

const sessao = JSON.parse(fs.readFileSync(caminhoSessao, 'utf-8'));
const TOKEN = sessao.access_token;
if (!TOKEN) {
  console.error('sessao.json sem access_token — gere de novo com gerar_sessao_local.py');
  process.exit(1);
}

/** Falha o roteiro com uma mensagem que diz o que se esperava e o que veio. */
function conferir(condicao, mensagem) {
  if (!condicao) {
    throw new Error(mensagem);
  }
}

async function api(caminho) {
  const resposta = await fetch(`${API}${caminho}`, {
    headers: { Authorization: `Bearer ${TOKEN}` }
  });
  if (!resposta.ok) {
    throw new Error(`GET ${caminho} respondeu ${resposta.status}`);
  }
  return resposta.json();
}

/**
 * Prova o caminho do D-82: clicar peça + casa responde o card, e o que chega
 * ao backend é o UCI das casas clicadas — não o SAN, que seria ambíguo entre
 * Torre (inglês) e Rei (português).
 */
async function treinoClique(page) {
  // A posição vem da API, não da tela: assim o roteiro escolhe um lance legal
  // sem depender de ler o tabuleiro pelo DOM.
  const fila = await api('/treino/fila');
  conferir(fila.itens.length > 0, 'fila de treino vazia — nada para dirigir hoje');

  // Tem que ser `itens[0]`, não o primeiro não-EROSAO da lista: a tela mostra
  // sempre o topo da fila, e escolher um card mais abaixo faria o roteiro
  // clicar num tabuleiro que não é o dele — passando ou falhando por acaso.
  const card = fila.itens[0];
  conferir(
    card.tipo_evento !== 'EROSAO',
    'o card do topo é de trecho (EROSAO), que se resolve em vários lances; ' +
      'este roteiro cobre o card de lance único. Rode de novo noutro dia ou ' +
      'responda o trecho antes.'
  );

  const jogo = new Chess(card.fen);
  const lance = jogo.moves({ verbose: true }).find((m) => !m.promotion);
  conferir(lance, 'nenhum lance simples legal nesta posição');
  const uciEsperado = `${lance.from}${lance.to}`;

  console.log(`  card ${card.fila_id}, ${card.cor_jogada}`);
  console.log(`  vou clicar ${lance.from} -> ${lance.to} (SAN ${lance.san}, UCI ${uciEsperado})`);

  if (valendo) {
    // Aprendido na marra ao construir isto: a ferramenta escolhe o card
    // sozinha (é sempre o topo da fila), então quem roda não tem como ter
    // guardado o estado antes. Sem estas linhas, desfazer vira arqueologia —
    // `proxima_revisao_data` não está em lugar nenhum depois de sobrescrita.
    console.log('');
    console.log(`  ATENÇÃO: o card ${card.fila_id} vai ser respondido DE VERDADE.`);
    console.log('  Para poder desfazer, guarde o estado atual antes de seguir:');
    console.log(
      `    select id, proxima_revisao_data, intervalo_dias, fator_facilidade,\n` +
        `           repeticoes, total_revisoes, ultima_qualidade\n` +
        `      from fila_treino_espacado where id = ${card.fila_id};`
    );
    console.log('');
  }

  let corpoEnviado = null;
  await page.route(`${API}/treino/*/responder`, async (rota) => {
    corpoEnviado = rota.request().postDataJSON();
    if (valendo) {
      await rota.continue();
      return;
    }
    await rota.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        qualidade_lance: 'BOM',
        lance_interpretado: lance.san,
        melhor_lance: lance.san,
        queda_win_percent: 0,
        raiz_conceitual_violada: null,
        tags_falha: [],
        livro_citado: null,
        capitulo_citado: null,
        pagina_citada: null,
        partida_referencia: null,
        partida_url: null,
        fora_do_tempo: false,
        proxima_revisao_data: '2026-01-01',
        repeticoes: 1
      })
    });
  });

  await page.goto(`${BASE}/treino`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(ESPERA_MS);

  const casaOrigem = page.locator(`[data-casa="${lance.from}"]`);
  await casaOrigem.waitFor({ state: 'visible', timeout: 10_000 });

  await casaOrigem.click();
  // Espera o atributo, não lê uma vez só: o clique volta assim que é
  // despachado, e a detecção de mudanças do Angular ainda não escreveu o
  // `aria-pressed` no DOM. Ler direto passa ou falha por milissegundos — foi
  // o que aconteceu na primeira execução desta ferramenta.
  await page
    .locator(`[data-casa="${lance.from}"][aria-pressed="true"]`)
    .waitFor({ state: 'attached', timeout: 5000 })
    .catch(() => {
      throw new Error(`clicar em ${lance.from} não selecionou a casa (aria-pressed)`);
    });

  await page.locator(`[data-casa="${lance.to}"]`).click();
  await page.waitForTimeout(2500);

  conferir(corpoEnviado, 'o clique não gerou requisição para /treino/{id}/responder');
  conferir(
    corpoEnviado.lance_uci === uciEsperado,
    `lance_uci era "${corpoEnviado?.lance_uci}", esperava "${uciEsperado}"`
  );
  conferir(
    corpoEnviado.lance === lance.san,
    `lance (eco em SAN) era "${corpoEnviado?.lance}", esperava "${lance.san}"`
  );

  console.log(`  requisição enviou lance_uci="${corpoEnviado.lance_uci}" lance="${corpoEnviado.lance}"`);

  // A revelação é o que prova que a tela consumiu a resposta, e não só a
  // enviou. O texto é do próprio contrato da API (o painel do melhor lance).
  //
  // O prazo muda com o modo, e por um motivo concreto: respondendo valendo,
  // quem demora é o Stockfish na profundidade de verdade, serializado no lock
  // global (R3). Medido aqui: passa de 12s com folga, e o botão fica em
  // "Avaliando…" o tempo todo. Com a resposta interceptada não há motor, e um
  // prazo longo só serviria para mascarar uma tela travada.
  const prazoRevelacao = valendo ? 120_000 : 10_000;
  await page
    .getByText('Melhor lance do motor')
    .waitFor({ state: 'visible', timeout: prazoRevelacao });
  console.log('  a tela mostrou a revelação do resultado');
}

const ROTEIROS = {
  'treino-clique': treinoClique
};

const roteiro = ROTEIROS[roteiroPedido];
if (!roteiro) {
  console.error(`roteiro desconhecido: ${roteiroPedido}`);
  console.error(`disponíveis: ${Object.keys(ROTEIROS).join(', ')}`);
  process.exit(1);
}

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

const errosDeConsole = [];
page.on('console', (m) => m.type() === 'error' && errosDeConsole.push(m.text()));
page.on('pageerror', (e) => errosDeConsole.push(String(e)));

// A sessão só cola se a origem já estiver carregada (mesma armadilha do
// capturar-telas.mjs: em about:blank o localStorage é de outro domínio).
await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
await page.evaluate(
  ([chave, valor]) => localStorage.setItem(chave, valor),
  [CHAVE_SESSAO, JSON.stringify(sessao)]
);

console.log(`roteiro: ${roteiroPedido}${valendo ? '  [VALENDO — vai gravar de verdade]' : '  [seguro — resposta interceptada]'}`);

let falha = null;
try {
  await roteiro(page);
} catch (erro) {
  falha = erro;
  const arquivo = path.resolve(`falha-${roteiroPedido}.png`);
  await page.screenshot({ path: arquivo, fullPage: true }).catch(() => {});
  console.error(`\nFALHOU: ${erro.message}`);
  console.error(`tela no momento da falha: ${arquivo}`);
}

await ctx.close();
await browser.close();

if (errosDeConsole.length > 0) {
  console.error(`\nerros de console (${errosDeConsole.length}):`);
  for (const erro of [...new Set(errosDeConsole)].slice(0, 10)) {
    console.error('  -', erro.slice(0, 200));
  }
}

const passou = !falha && errosDeConsole.length === 0;
console.log(passou ? '\nOK' : '\nREPROVADO');
process.exit(passou ? 0 : 1);
