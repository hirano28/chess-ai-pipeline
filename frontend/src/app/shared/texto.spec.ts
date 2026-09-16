import { describe, it, expect } from 'vitest';
import { segmentosDeNegrito } from './texto';

describe('segmentosDeNegrito', () => {
  it('separa os trechos em negrito do texto normal', () => {
    expect(segmentosDeNegrito('a **Tática** permanece')).toEqual([
      { texto: 'a ', negrito: false },
      { texto: 'Tática', negrito: true },
      { texto: ' permanece', negrito: false }
    ]);
  });

  it('trata vários negritos no mesmo parágrafo', () => {
    const segmentos = segmentosDeNegrito('**Tática** e **Cálculo**');
    expect(segmentos.filter((s) => s.negrito).map((s) => s.texto)).toEqual([
      'Tática',
      'Cálculo'
    ]);
  });

  it('texto sem marcação volta como um segmento só', () => {
    expect(segmentosDeNegrito('sem nenhuma marcação')).toEqual([
      { texto: 'sem nenhuma marcação', negrito: false }
    ]);
  });

  it('não engole asterisco solto nem par não fechado', () => {
    // Não era markdown de propósito: preservar é o comportamento certo.
    expect(segmentosDeNegrito('3 ** 4 = ?')).toEqual([{ texto: '3 ** 4 = ?', negrito: false }]);
    expect(segmentosDeNegrito('abre **mas não fecha')).toEqual([
      { texto: 'abre **mas não fecha', negrito: false }
    ]);
  });

  it('string vazia não quebra', () => {
    expect(segmentosDeNegrito('')).toEqual([{ texto: '', negrito: false }]);
  });
});
