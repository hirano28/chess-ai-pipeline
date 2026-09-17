import { Component, computed, input, output, signal } from '@angular/core';
import { Chess, Square } from 'chess.js';

/** Lance escolhido no tabuleiro, em coordenadas. Quem usa decide o que fazer com ele. */
export interface LanceTabuleiro {
  from: string;
  to: string;
  promotion?: string;
}

interface CasaInterativa {
  nome: string;
  peca: string;
  clara: boolean;
  rankLabel?: string;
  fileLabel?: string;
  selecionada: boolean;
  destino: boolean;
  captura: boolean;
  ultimoLance: boolean;
}

const PIECES_BASE_URL = 'pieces/cburnett';
const NOMES_PECAS: Record<string, string> = {
  p: 'peão',
  n: 'cavalo',
  b: 'bispo',
  r: 'torre',
  q: 'dama',
  k: 'rei'
};
const ARQUIVOS = 'abcdefgh';

/**
 * Tabuleiro em que se joga clicando: peça, depois casa (D-67).
 *
 * Existe para espelhar uma partida em andamento sem digitar cada lance. Não
 * guarda a partida — recebe a FEN e devolve o lance escolhido; a legalidade
 * vem do chess.js, então um clique nunca produz um lance impossível. Mesmo
 * conjunto de peças e mesmas cores do `tabuleiro-preview`.
 */
@Component({
  selector: 'app-tabuleiro-interativo',
  standalone: true,
  templateUrl: './tabuleiro-interativo.component.html'
})
export class TabuleiroInterativoComponent {
  readonly fen = input.required<string>();
  readonly orientacao = input<'BRANCAS' | 'PRETAS'>('BRANCAS');
  readonly ultimoLance = input<{ from: string; to: string } | null>(null);
  /** Enquanto uma consulta está em andamento, o tabuleiro não aceita lance. */
  readonly bloqueado = input(false);

  readonly lanceJogado = output<LanceTabuleiro>();

  readonly selecionada = signal<string | null>(null);
  readonly promocaoPendente = signal<{ from: string; to: string } | null>(null);
  readonly piecesBaseUrl = PIECES_BASE_URL;
  readonly opcoesPromocao = ['q', 'r', 'b', 'n'];

  private readonly jogo = computed<Chess | null>(() => {
    try {
      return new Chess(this.fen());
    } catch {
      return null;
    }
  });

  readonly corDaVez = computed<'w' | 'b'>(() => this.jogo()?.turn() ?? 'w');

  private readonly destinos = computed(() => {
    const jogo = this.jogo();
    const origem = this.selecionada();
    if (!jogo || !origem) {
      return new Map<string, { captura: boolean; promocao: boolean }>();
    }
    const mapa = new Map<string, { captura: boolean; promocao: boolean }>();
    for (const lance of jogo.moves({ square: origem as Square, verbose: true })) {
      mapa.set(lance.to, {
        captura: Boolean(lance.captured),
        promocao: Boolean(lance.promotion)
      });
    }
    return mapa;
  });

  readonly casas = computed<CasaInterativa[]>(() => {
    const jogo = this.jogo();
    const pretas = this.orientacao() === 'PRETAS';
    const destinos = this.destinos();
    const ultimo = this.ultimoLance();
    const casas: CasaInterativa[] = [];

    for (let linha = 0; linha < 8; linha++) {
      for (let coluna = 0; coluna < 8; coluna++) {
        const rank = pretas ? linha + 1 : 8 - linha;
        const arquivo = pretas ? 7 - coluna : coluna;
        const nome = `${ARQUIVOS[arquivo]}${rank}`;
        const peca = jogo?.get(nome as Square);
        const destino = destinos.get(nome);
        casas.push({
          nome,
          peca: peca ? `${peca.color}${peca.type.toUpperCase()}` : '',
          clara: (rank + arquivo) % 2 === 0,
          rankLabel: coluna === 0 ? String(rank) : undefined,
          fileLabel: linha === 7 ? ARQUIVOS[arquivo] : undefined,
          selecionada: this.selecionada() === nome,
          destino: Boolean(destino),
          captura: Boolean(destino?.captura),
          ultimoLance: ultimo !== null && (ultimo.from === nome || ultimo.to === nome)
        });
      }
    }
    return casas;
  });

  descricaoCasa(casa: CasaInterativa): string {
    if (!casa.peca) {
      return casa.destino ? `${casa.nome}, mover para cá` : casa.nome;
    }
    const cor = casa.peca[0] === 'w' ? 'branco' : 'preto';
    const nome = NOMES_PECAS[casa.peca[1].toLowerCase()] ?? 'peça';
    const sufixo = casa.captura ? ', capturar' : casa.selecionada ? ', selecionada' : '';
    return `${casa.nome}, ${nome} ${cor}${sufixo}`;
  }

  clicar(casa: CasaInterativa): void {
    if (this.bloqueado() || this.promocaoPendente()) {
      return;
    }
    const origem = this.selecionada();
    const destino = this.destinos().get(casa.nome);

    if (origem && destino) {
      if (destino.promocao) {
        this.promocaoPendente.set({ from: origem, to: casa.nome });
        return;
      }
      this.selecionada.set(null);
      this.lanceJogado.emit({ from: origem, to: casa.nome });
      return;
    }

    const ehDaVez = casa.peca !== '' && casa.peca[0] === this.corDaVez();
    this.selecionada.set(ehDaVez && origem !== casa.nome ? casa.nome : null);
  }

  escolherPromocao(peca: string): void {
    const pendente = this.promocaoPendente();
    if (!pendente) {
      return;
    }
    this.promocaoPendente.set(null);
    this.selecionada.set(null);
    this.lanceJogado.emit({ ...pendente, promotion: peca });
  }

  cancelarPromocao(): void {
    this.promocaoPendente.set(null);
  }

  imagemPromocao(peca: string): string {
    return `${this.piecesBaseUrl}/${this.corDaVez()}${peca.toUpperCase()}.svg`;
  }
}
