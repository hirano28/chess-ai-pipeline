/** Preparo de texto gerado pelos agentes para exibição. */

export interface SegmentoTexto {
  texto: string;
  negrito: boolean;
}

/**
 * Quebra um parágrafo em segmentos normais e em negrito, a partir da marcação
 * `**assim**` que o Gemini usa nas narrativas.
 *
 * Os prompts não proíbem markdown e o modelo usa negrito com frequência, então
 * a narrativa chegava na tela com os asteriscos à mostra ("a **Tática**
 * permanece como o seu gargalo"). Devolver segmentos — em vez de HTML — deixa
 * o template renderizar com `<strong>` sem `innerHTML`, então nada que venha do
 * modelo é interpretado como marcação.
 *
 * Só trata negrito: é a única marcação que apareceu de verdade nas narrativas.
 * Asterisco solto ou par não fechado fica como está, que é o comportamento
 * certo para um texto que não era markdown de propósito.
 */
export function segmentosDeNegrito(texto: string): SegmentoTexto[] {
  const segmentos: SegmentoTexto[] = [];
  const padrao = /\*\*(.+?)\*\*/g;
  let ultimoFim = 0;

  for (const achado of texto.matchAll(padrao)) {
    const inicio = achado.index ?? 0;
    if (inicio > ultimoFim) {
      segmentos.push({ texto: texto.slice(ultimoFim, inicio), negrito: false });
    }
    segmentos.push({ texto: achado[1], negrito: true });
    ultimoFim = inicio + achado[0].length;
  }

  if (ultimoFim < texto.length) {
    segmentos.push({ texto: texto.slice(ultimoFim), negrito: false });
  }

  return segmentos.length > 0 ? segmentos : [{ texto, negrito: false }];
}
