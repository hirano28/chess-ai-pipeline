import { describe, it, expect } from 'vitest';
import { orientacaoDoFen } from './fen';

describe('orientacaoDoFen', () => {
  it('devolve PRETAS quando é a vez das pretas', () => {
    expect(
      orientacaoDoFen('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1')
    ).toBe('PRETAS');
  });

  it('devolve BRANCAS quando é a vez das brancas', () => {
    expect(
      orientacaoDoFen('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    ).toBe('BRANCAS');
  });

  it('cai no default BRANCAS para entrada ausente ou malformada', () => {
    expect(orientacaoDoFen(null)).toBe('BRANCAS');
    expect(orientacaoDoFen(undefined)).toBe('BRANCAS');
    expect(orientacaoDoFen('')).toBe('BRANCAS');
    // Só o campo de colocação, sem o campo de turno.
    expect(orientacaoDoFen('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')).toBe('BRANCAS');
    expect(orientacaoDoFen('não é um fen')).toBe('BRANCAS');
  });

  it('tolera espaços extras e caixa alta no campo de turno', () => {
    expect(orientacaoDoFen('  8/8/8/8/8/8/8/8   B - - 0 1  ')).toBe('PRETAS');
  });
});
