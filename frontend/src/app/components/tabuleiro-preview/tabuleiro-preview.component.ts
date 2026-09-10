import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';

interface CasaTabuleiro {
  /** Código do arquivo SVG da peça (ex: "wK", "bP"), ou '' se a casa estiver vazia. */
  peca: string;
  clara: boolean;
}

/** Conjunto "cburnett" (Colin M. L. Burnett, GPL/CC-BY-SA), mesmo usado pelo Lichess. */
const PIECES_BASE_URL = 'pieces/cburnett';

const PECAS_BRANCAS: Record<string, string> = {
  K: 'wK',
  Q: 'wQ',
  R: 'wR',
  B: 'wB',
  N: 'wN',
  P: 'wP'
};

const PECAS_PRETAS: Record<string, string> = {
  k: 'bK',
  q: 'bQ',
  r: 'bR',
  b: 'bB',
  n: 'bN',
  p: 'bP'
};

@Component({
  selector: 'app-tabuleiro-preview',
  standalone: true,
  templateUrl: './tabuleiro-preview.component.html'
})
export class TabuleiroPreviewComponent implements OnChanges {
  /** FEN completa ou só o campo de colocação de peças. Vazio/inválido -> tabuleiro vazio. */
  @Input() fen = '';

  /** Exposto para o template montar `src="{{ piecesBaseUrl }}/{{ casa.peca }}.svg"`. */
  readonly piecesBaseUrl = PIECES_BASE_URL;

  casas: CasaTabuleiro[] = this.tabuleiroVazio();

  ngOnChanges(changes: SimpleChanges): void {
    if ('fen' in changes) {
      this.casas = this.parseFen(this.fen);
    }
  }

  private tabuleiroVazio(): CasaTabuleiro[] {
    const casas: CasaTabuleiro[] = [];
    for (let rank = 0; rank < 8; rank++) {
      for (let file = 0; file < 8; file++) {
        casas.push({ peca: '', clara: (rank + file) % 2 === 0 });
      }
    }
    return casas;
  }

  /** Faz parse só do campo de colocação de peças (1º campo do FEN); tolera FEN incompleta. */
  private parseFen(fen: string): CasaTabuleiro[] {
    const vazio = this.tabuleiroVazio();
    const colocacao = (fen ?? '').trim().split(/\s+/)[0];
    if (!colocacao) {
      return vazio;
    }

    const linhas = colocacao.split('/');
    if (linhas.length !== 8) {
      return vazio;
    }

    const casas = this.tabuleiroVazio();
    for (let rank = 0; rank < 8; rank++) {
      let file = 0;
      for (const char of linhas[rank]) {
        if (file > 7) {
          return vazio;
        }
        if (/^[1-8]$/.test(char)) {
          file += Number(char);
          continue;
        }
        const peca = PECAS_BRANCAS[char] ?? PECAS_PRETAS[char];
        if (!peca) {
          return vazio;
        }
        casas[rank * 8 + file].peca = peca;
        file += 1;
      }
      if (file !== 8) {
        return vazio;
      }
    }
    return casas;
  }
}
