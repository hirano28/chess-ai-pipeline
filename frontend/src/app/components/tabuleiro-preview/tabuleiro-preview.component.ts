import { Component, Input, OnChanges, OnInit, SimpleChanges, signal } from '@angular/core';

export interface CasaTabuleiro {
  /** Código do arquivo SVG da peça (ex: "wK", "bP"), ou '' se a casa estiver vazia. */
  peca: string;
  clara: boolean;
  rankLabel?: string;
  fileLabel?: string;
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
export class TabuleiroPreviewComponent implements OnInit, OnChanges {
  /** FEN completa ou só o campo de colocação de peças. Vazio/inválido -> tabuleiro vazio. */
  @Input() fen = '';

  /** true = versão compacta (sem legenda, tabuleiro menor) para uso como miniatura clicável em listas. */
  @Input() miniatura = false;

  /** Orientação do tabuleiro: BRANCAS (padrão) ou PRETAS. */
  @Input() orientacao: 'BRANCAS' | 'PRETAS' = 'BRANCAS';

  /** Exibir coordenadas de rank e file (1-8 e a-h) nas bordas. */
  @Input() mostrarCoordenadas = true;

  /** Exibir barra de ferramentas com indicador de vez e botão de virar tabuleiro. */
  @Input() mostrarBarraFerramentas = true;

  /** Orientação atualmente ativa (pode ser alternada pelo usuário via botão de virar). */
  readonly orientacaoAtiva = signal<'BRANCAS' | 'PRETAS'>('BRANCAS');

  /** Vez de jogar extraída do 2º campo da FEN ('BRANCAS' | 'PRETAS' | null). */
  readonly vezDeJogar = signal<'BRANCAS' | 'PRETAS' | null>(null);

  /** Exposto para o template montar `src="{{ piecesBaseUrl }}/{{ casa.peca }}.svg"`. */
  readonly piecesBaseUrl = PIECES_BASE_URL;

  casas: CasaTabuleiro[] = this.tabuleiroVazio();

  ngOnInit(): void {
    this.orientacaoAtiva.set(this.orientacao);
    this.atualizarVezDeJogar();
    this.casas = this.parseFen(this.fen);
  }

  ngOnChanges(changes: SimpleChanges): void {
    if ('orientacao' in changes) {
      this.orientacaoAtiva.set(this.orientacao);
    }
    if ('fen' in changes || 'orientacao' in changes || 'mostrarCoordenadas' in changes) {
      this.atualizarVezDeJogar();
      this.casas = this.parseFen(this.fen);
    }
  }

  alternarOrientacao(): void {
    this.orientacaoAtiva.set(this.orientacaoAtiva() === 'BRANCAS' ? 'PRETAS' : 'BRANCAS');
    this.casas = this.parseFen(this.fen);
  }

  private atualizarVezDeJogar(): void {
    const partes = (this.fen ?? '').trim().split(/\s+/);
    if (partes.length > 1) {
      const turno = partes[1].toLowerCase();
      if (turno === 'w') {
        this.vezDeJogar.set('BRANCAS');
        return;
      }
      if (turno === 'b') {
        this.vezDeJogar.set('PRETAS');
        return;
      }
    }
    this.vezDeJogar.set(null);
  }

  private tabuleiroVazio(): CasaTabuleiro[] {
    const casas: CasaTabuleiro[] = [];
    const pretas = this.orientacaoAtiva() === 'PRETAS';
    for (let r = 0; r < 8; r++) {
      for (let f = 0; f < 8; f++) {
        const rankNum = pretas ? r + 1 : 8 - r;
        const fileNum = pretas ? 8 - f : f + 1;
        const clara = (rankNum + fileNum) % 2 !== 0;

        let rankLabel: string | undefined;
        let fileLabel: string | undefined;

        if (this.mostrarCoordenadas && !this.miniatura) {
          if (f === 0) {
            rankLabel = String(rankNum);
          }
          if (r === 7) {
            fileLabel = String.fromCharCode(96 + fileNum);
          }
        }

        casas.push({ peca: '', clara, rankLabel, fileLabel });
      }
    }
    return casas;
  }

  /** Faz parse do FEN e gera o grid de 64 casas conforme a orientação ativa. */
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

    // Matriz canônica [8][8]: rank 8 no topo [0], file a na esquerda [0]
    const matriz: string[][] = Array.from({ length: 8 }, () => Array(8).fill(''));
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
        matriz[rank][file] = peca;
        file += 1;
      }
      if (file !== 8) {
        return vazio;
      }
    }

    // Array linear de 64 casas conforme a orientação ativa
    const casas: CasaTabuleiro[] = [];
    const pretas = this.orientacaoAtiva() === 'PRETAS';

    for (let r = 0; r < 8; r++) {
      for (let f = 0; f < 8; f++) {
        const origRank = pretas ? 7 - r : r;
        const origFile = pretas ? 7 - f : f;

        const rankNum = pretas ? r + 1 : 8 - r;
        const fileNum = pretas ? 8 - f : f + 1;
        const clara = (rankNum + fileNum) % 2 !== 0;

        let rankLabel: string | undefined;
        let fileLabel: string | undefined;

        if (this.mostrarCoordenadas && !this.miniatura) {
          if (f === 0) {
            rankLabel = String(rankNum);
          }
          if (r === 7) {
            fileLabel = String.fromCharCode(96 + fileNum);
          }
        }

        casas.push({
          peca: matriz[origRank][origFile],
          clara,
          rankLabel,
          fileLabel
        });
      }
    }

    return casas;
  }
}
