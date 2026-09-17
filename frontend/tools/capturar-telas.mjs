/**
 * Captura screenshots das telas da aplicação rodando localmente (D-53).
 *
 * É uma ferramenta de CAPTURA, não de teste: ela não afirma nada sobre o que
 * viu, só fotografa e salva. Foi essa a escolha depois de um script de tour
 * cheio de asserções quebrar na primeira mudança de UI — quem olha as imagens
 * é quem julga. Por isso também não entra em CI.
 *
 * Existe porque teste unitário não pega defeito visual: a narrativa do Agente 2
 * exibiu markdown cru (`**Tática**`) por vários dias com a suíte inteira verde,
 * e só apareceu quando alguém olhou a tela (D-52).
 *
 * Pré-requisitos (ver docs/OPERACAO.md §8):
 *   1. `uvicorn backend.api.api_server:app --port 8000`
 *   2. `npm start` (o environment.development.ts já aponta pra API local)
 *   3. `python backend/common/gerar_sessao_local.py <email> sessao.json`
 *
 * Uso:
 *   node tools/capturar-telas.mjs sessao.json [pasta-de-saida]
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const BASE = process.env.BASE_URL ?? 'http://localhost:4200';
const PROJETO_SUPABASE = 'pmzmershonrqzwbmhaco';
const CHAVE_SESSAO = `sb-${PROJETO_SUPABASE}-auth-token`;

const [, , caminhoSessao, pastaSaida = 'telas'] = process.argv;
if (!caminhoSessao) {
  console.error('uso: node tools/capturar-telas.mjs <sessao.json> [pasta-de-saida]');
  process.exit(1);
}

const sessao = JSON.parse(fs.readFileSync(caminhoSessao, 'utf-8'));
const SAIDA = path.resolve(pastaSaida);
fs.mkdirSync(SAIDA, { recursive: true });

/** As duas larguras importam: dos 3 defeitos achados no D-52, um era só do
 *  desktop (cartões espremidos) e outro só do celular (navegação sem pista).
 *  `TABLET=1` acrescenta 820px — abaixo do corte de 1024px, onde a navegação
 *  lateral vira gaveta num espaço que ainda tem cara de desktop (D-71). */
const VIEWPORTS = [
  { nome: 'desktop', viewport: { width: 1440, height: 900 } },
  ...(process.env.TABLET ? [{ nome: 'tablet', viewport: { width: 820, height: 1180 } }] : []),
  { nome: 'celular', viewport: { width: 390, height: 844 } }
];

/** D-71: `TEMA=claro` ou `TEMA=escuro` força o tema (mesma chave do
 *  TemaService). Sem a variável, vale o tema do navegador headless — claro. */
const TEMA = process.env.TEMA;
const SUFIXO_TEMA = TEMA ? `-${TEMA}` : '';

/** Rotas com parâmetro (ex.: /sessao/:id) não cabem numa lista fixa — o id
 *  muda a cada execução. `ROTAS_EXTRA="/sessao/abc:sessao,/x:nome"` acrescenta
 *  as que interessarem naquela verificação. */
const ROTAS_EXTRA = (process.env.ROTAS_EXTRA ?? '')
  .split(',')
  .map((entrada) => entrada.trim())
  .filter(Boolean)
  .map((entrada) => {
    const corte = entrada.lastIndexOf(':');
    return corte === -1
      ? { caminho: entrada, nome: entrada.replace(/\W+/g, '-').replace(/^-|-$/g, '') }
      : { caminho: entrada.slice(0, corte), nome: entrada.slice(corte + 1) };
  });

const ROTAS = [
  { caminho: '/', nome: 'visao-geral' },
  { caminho: '/aberturas', nome: 'aberturas' },
  { caminho: '/puzzles', nome: 'puzzles' },
  { caminho: '/plano', nome: 'plano' },
  { caminho: '/treino', nome: 'treino' },
  { caminho: '/laboratorio', nome: 'laboratorio' },
  { caminho: '/explicador', nome: 'explicador' },
  { caminho: '/analisador', nome: 'analisador' },
  { caminho: '/perfil', nome: 'perfil' },
  ...ROTAS_EXTRA
];

/** Espera a tela assentar: as telas buscam dado da API/Supabase ao entrar, e
 *  fotografar cedo demais rende um álbum de esqueletos de carregamento. */
const ESPERA_MS = Number(process.env.ESPERA_MS ?? 4500);

const browser = await chromium.launch();
let capturadas = 0;

for (const { nome: nomeViewport, viewport } of VIEWPORTS) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2 });
  const page = await ctx.newPage();

  const errosDeConsole = [];
  page.on('console', (m) => m.type() === 'error' && errosDeConsole.push(m.text()));
  page.on('pageerror', (e) => errosDeConsole.push(String(e)));

  // A sessão precisa ser gravada com a origem já carregada, senão o
  // localStorage pertence a "about:blank" e o app abre deslogado.
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(
    ([chave, valor, tema]) => {
      localStorage.setItem(chave, valor);
      if (tema) localStorage.setItem('hexagono:tema', tema);
    },
    [CHAVE_SESSAO, JSON.stringify(sessao), TEMA]
  );

  for (const { caminho, nome } of ROTAS) {
    await page.goto(`${BASE}${caminho}`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(ESPERA_MS);
    const arquivo = path.join(SAIDA, `${nomeViewport}${SUFIXO_TEMA}-${nome}.png`);
    await page.screenshot({ path: arquivo, fullPage: true });
    console.log('capturada:', path.relative(process.cwd(), arquivo));
    capturadas += 1;
  }

  await ctx.close();

  if (errosDeConsole.length > 0) {
    console.log(`\nerros de console em ${nomeViewport} (${errosDeConsole.length}):`);
    for (const erro of [...new Set(errosDeConsole)].slice(0, 10)) {
      console.log('  -', erro.slice(0, 200));
    }
  }
}

// A tela de login é a única que precisa de contexto deslogado.
{
  const ctx = await browser.newContext({ viewport: VIEWPORTS[0].viewport, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  if (TEMA) {
    await page.evaluate((tema) => localStorage.setItem('hexagono:tema', tema), TEMA);
    await page.reload({ waitUntil: 'domcontentloaded' });
  }
  await page.waitForTimeout(1500);
  const arquivo = path.join(SAIDA, `desktop${SUFIXO_TEMA}-login.png`);
  await page.screenshot({ path: arquivo, fullPage: true });
  console.log('capturada:', path.relative(process.cwd(), arquivo));
  capturadas += 1;
  await ctx.close();
}

await browser.close();
console.log(`\n${capturadas} telas em ${SAIDA}`);
