import { beforeEach, describe, expect, it } from 'vitest';
import { Chess } from 'chess.js';
import {
  carregarPartida,
  lerPgnOuFen,
  novaPartida,
  reconstruirJogo,
  resolverLanceDigitado,
  salvarPartida,
  traduzirLancePt
} from './partida-espelho';

describe('partida-espelho (D-67)', () => {
  beforeEach(() => localStorage.clear());

  describe('traduzirLancePt', () => {
    it('troca a letra da peça portuguesa pela inglesa', () => {
      expect(traduzirLancePt('Cf3')).toBe('Nf3');
      expect(traduzirLancePt('Dxd5+')).toBe('Qxd5+');
      expect(traduzirLancePt('Tae1')).toBe('Rae1');
      expect(traduzirLancePt('Re2')).toBe('Ke2');
    });

    it('traduz a promoção e o roque escrito com zeros', () => {
      expect(traduzirLancePt('exd8=D')).toBe('exd8=Q');
      expect(traduzirLancePt('0-0-0')).toBe('O-O-O');
    });
  });

  describe('resolverLanceDigitado', () => {
    it('aceita português e inglês e devolve SAN canônico', () => {
      const jogo = new Chess();
      expect(resolverLanceDigitado(jogo, 'e4')).toBe('e4');
      expect(resolverLanceDigitado(jogo, 'Cf3')).toBe('Nf3');
      expect(resolverLanceDigitado(jogo, 'Nf3')).toBe('Nf3');
    });

    it('lance ilegal devolve null sem mexer no jogo', () => {
      const jogo = new Chess();
      expect(resolverLanceDigitado(jogo, 'Dh5')).toBeNull();
      expect(jogo.history()).toEqual([]);
    });

    it('"R" é Rei primeiro e Torre só se o rei não puder', () => {
      // Só a torre de h1 pode ir a g1 nesta posição: "Rg1" cai no inglês.
      const soTorre = new Chess('4k3/8/8/8/8/8/8/4K2R w - - 0 1');
      expect(resolverLanceDigitado(soTorre, 'Rg1')).toBe('Rg1');
      // Aqui o rei pode ir a d2, então "Rd2" é lido como rei.
      const rei = new Chess('4k3/8/8/8/8/8/8/R3K3 w - - 0 1');
      expect(resolverLanceDigitado(rei, 'Rd2')).toBe('Kd2');
    });
  });

  describe('lerPgnOuFen', () => {
    it('lê os lances de um PGN', () => {
      const lido = lerPgnOuFen('[Event "Casual"]\n\n1. e4 e5 2. Nf3 Nc6 *');
      expect(lido.lances).toEqual(['e4', 'e5', 'Nf3', 'Nc6']);
      expect(lido.fenInicial).toBeNull();
    });

    it('lê uma FEN solta como posição inicial sem lances', () => {
      const lido = lerPgnOuFen('4k3/8/8/8/8/8/8/4K2R w - - 0 1');
      expect(lido.lances).toEqual([]);
      expect(lido.fenInicial).toContain('4K2R');
    });

    it('texto vazio ou ilegível dá erro legível', () => {
      expect(() => lerPgnOuFen('   ')).toThrow('Cole um PGN');
      expect(() => lerPgnOuFen('1. e4 Qxh8')).toThrow();
    });
  });

  describe('armazenamento', () => {
    it('salva e recupera a partida', () => {
      const partida = { ...novaPartida('PRETAS', 'CHESSCOM', 'Bot 5'), lances: ['e4'] };
      salvarPartida(partida);
      expect(carregarPartida()).toEqual(partida);
    });

    it('conteúdo corrompido volta null em vez de quebrar a tela', () => {
      localStorage.setItem('consulta-ao-vivo:partida', '{"id": 1');
      expect(carregarPartida()).toBeNull();
      localStorage.setItem('consulta-ao-vivo:partida', JSON.stringify({ id: 'x', lances: [], cor: 'VERDES' }));
      expect(carregarPartida()).toBeNull();
    });
  });

  it('reconstruirJogo para no primeiro lance inválido', () => {
    const partida = { ...novaPartida('BRANCAS', 'LICHESS', ''), lances: ['e4', 'e5', 'Qxh8', 'Nf3'] };
    expect(reconstruirJogo(partida).history()).toEqual(['e4', 'e5']);
  });

  it('cada partida nova tem um id próprio em formato uuid', () => {
    const a = novaPartida('BRANCAS', 'LICHESS', '').id;
    const b = novaPartida('BRANCAS', 'LICHESS', '').id;
    expect(a).not.toBe(b);
    expect(a).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
  });
});
