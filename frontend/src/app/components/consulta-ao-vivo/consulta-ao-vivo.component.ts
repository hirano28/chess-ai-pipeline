import { Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { Chess } from 'chess.js';
import {
  ConsultaAoVivo,
  ConsultaAoVivoService,
  CorJogador,
  PlataformaEspelho
} from '../../services/consulta-ao-vivo.service';
import {
  LanceTabuleiro,
  TabuleiroInterativoComponent
} from '../tabuleiro-interativo/tabuleiro-interativo.component';
import {
  PartidaEspelho,
  carregarPartida,
  lerPgnOuFen,
  novaPartida,
  reconstruirJogo,
  resolverLanceDigitado,
  salvarPartida
} from './partida-espelho';

/** Até onde o jogador já abriu a resposta de uma consulta. */
export type NivelRevelado = 1 | 2 | 3;

export interface ConsultaExibida {
  chave: string;
  dados: ConsultaAoVivo;
}

/**
 * Consulta ao vivo (D-67): espelhar uma partida em andamento e pedir ajuda
 * para PENSAR quando travar. Exclusiva do dono do projeto.
 *
 * A resposta chega inteira, mas é aberta em camadas: primeiro o que pensar,
 * depois as ideias candidatas, e só por último o lance do motor. Pular direto
 * para a terceira é possível — a tela só não oferece isso como primeiro passo.
 */
@Component({
  selector: 'app-consulta-ao-vivo',
  standalone: true,
  imports: [TabuleiroInterativoComponent],
  templateUrl: './consulta-ao-vivo.component.html'
})
export class ConsultaAoVivoComponent implements OnInit {
  private readonly service = inject(ConsultaAoVivoService);

  readonly partida = signal<PartidaEspelho>(novaPartida('BRANCAS', 'LICHESS', ''));
  readonly consultas = signal<ConsultaExibida[]>([]);
  readonly revelado = signal<Record<string, NivelRevelado>>({});
  readonly limitePorPartida = signal(3);

  readonly lanceDigitado = signal('');
  readonly erroLance = signal<string | null>(null);

  readonly situacao = signal('');
  readonly candidatos = signal('');
  readonly trava = signal('');
  readonly mostrarPensamento = signal(false);

  readonly consultando = signal(false);
  readonly erroConsulta = signal<string | null>(null);

  readonly configurando = signal(false);
  readonly textoPgn = signal('');
  readonly erroPgn = signal<string | null>(null);

  readonly jogo = computed<Chess>(() => reconstruirJogo(this.partida()));
  readonly fen = computed(() => this.jogo().fen());
  readonly corDaVez = computed<CorJogador>(() => (this.jogo().turn() === 'w' ? 'BRANCAS' : 'PRETAS'));
  readonly vezDoJogador = computed(() => this.corDaVez() === this.partida().cor);
  readonly fimDeJogo = computed(() => this.jogo().isGameOver());
  readonly ultimoLance = computed(() => {
    const historico = this.jogo().history({ verbose: true });
    const ultimo = historico[historico.length - 1];
    return ultimo ? { from: ultimo.from, to: ultimo.to } : null;
  });

  /** "1. e4 e5 2. Nf3" em pares, com o número certo mesmo partindo de FEN. */
  readonly listaDeLances = computed(() => {
    const inicial = this.partida().fenInicial ? new Chess(this.partida().fenInicial!) : new Chess();
    let numero = inicial.moveNumber();
    let vezDasBrancas = inicial.turn() === 'w';
    const pares: { numero: number; brancas: string | null; pretas: string | null }[] = [];
    for (const lance of this.partida().lances) {
      if (vezDasBrancas) {
        pares.push({ numero, brancas: lance, pretas: null });
      } else {
        const atual = pares[pares.length - 1];
        if (atual && atual.pretas === null && atual.numero === numero) {
          atual.pretas = lance;
        } else {
          pares.push({ numero, brancas: null, pretas: lance });
        }
        numero += 1;
      }
      vezDasBrancas = !vezDasBrancas;
    }
    return pares;
  });

  readonly consultasRestantes = computed(() =>
    Math.max(0, this.limitePorPartida() - this.consultas().length)
  );

  readonly podeConsultar = computed(
    () =>
      this.vezDoJogador() &&
      !this.fimDeJogo() &&
      !this.consultando() &&
      this.consultasRestantes() > 0
  );

  /** Por que o botão de consulta está desligado, dito em uma frase. */
  readonly motivoSemConsulta = computed<string | null>(() => {
    if (this.fimDeJogo()) {
      return 'A partida terminou.';
    }
    if (this.consultasRestantes() === 0) {
      return 'As consultas desta partida acabaram — daqui em diante, a decisão é sua.';
    }
    if (!this.vezDoJogador()) {
      return 'É a vez do adversário: espelhe o lance dele primeiro.';
    }
    return null;
  });

  constructor() {
    effect(() => salvarPartida(this.partida()));
  }

  async ngOnInit(): Promise<void> {
    const salva = carregarPartida();
    if (salva) {
      this.partida.set(salva);
    }
    const acesso = await this.service.acesso();
    if (acesso.limitePorPartida > 0) {
      this.limitePorPartida.set(acesso.limitePorPartida);
    }
    if (salva) {
      await this.carregarConsultas(salva.id);
    }
  }

  private async carregarConsultas(partidaId: string): Promise<void> {
    const resposta = await this.service.listarDaPartida(partidaId);
    if (resposta.success && resposta.dados) {
      const exibidas = resposta.dados
        .map((dados, indice) => ({ chave: dados.id ?? `carregada-${indice}`, dados }))
        .reverse();
      this.consultas.set(exibidas);
      // Consulta de antes da recarga volta toda aberta: o jogador já a viu.
      this.revelado.set(Object.fromEntries(exibidas.map((c) => [c.chave, 3 as NivelRevelado])));
    }
  }

  jogarDoTabuleiro(lance: LanceTabuleiro): void {
    const copia = new Chess(this.fen());
    try {
      const feito = copia.move({ from: lance.from, to: lance.to, promotion: lance.promotion });
      this.acrescentarLance(feito.san);
    } catch {
      this.erroLance.set('Lance ilegal nessa posição.');
    }
  }

  jogarDoTexto(): void {
    const texto = this.lanceDigitado().trim();
    if (!texto) {
      return;
    }
    const san = resolverLanceDigitado(this.jogo(), texto);
    if (!san) {
      this.erroLance.set(`"${texto}" não é um lance legal nessa posição.`);
      return;
    }
    this.acrescentarLance(san);
    this.lanceDigitado.set('');
  }

  private acrescentarLance(san: string): void {
    this.erroLance.set(null);
    this.partida.update((p) => ({ ...p, lances: [...p.lances, san] }));
  }

  desfazer(): void {
    this.erroLance.set(null);
    this.partida.update((p) => ({ ...p, lances: p.lances.slice(0, -1) }));
  }

  definirCor(cor: CorJogador): void {
    this.partida.update((p) => ({ ...p, cor }));
  }

  definirPlataforma(plataforma: PlataformaEspelho): void {
    this.partida.update((p) => ({ ...p, plataforma }));
  }

  definirAdversario(adversario: string): void {
    this.partida.update((p) => ({ ...p, adversario }));
  }

  /** Começa uma partida nova: id novo, lances e consultas zerados. */
  comecarNovaPartida(): void {
    const atual = this.partida();
    if (atual.lances.length > 0 && !confirm('Começar uma partida nova? A atual deixa de ser espelhada.')) {
      return;
    }
    this.partida.set(novaPartida(atual.cor, atual.plataforma, atual.adversario));
    this.consultas.set([]);
    this.revelado.set({});
    this.limparPensamento();
    this.erroConsulta.set(null);
    this.erroLance.set(null);
  }

  /** Substitui os lances pelos de um PGN colado (a partida continua a mesma). */
  aplicarPgn(): void {
    try {
      const lido = lerPgnOuFen(this.textoPgn());
      this.partida.update((p) => ({ ...p, fenInicial: lido.fenInicial, lances: lido.lances }));
      this.textoPgn.set('');
      this.erroPgn.set(null);
      this.configurando.set(false);
    } catch (erro) {
      this.erroPgn.set(erro instanceof Error ? erro.message : 'Não consegui ler esse texto.');
    }
  }

  async consultar(): Promise<void> {
    if (!this.podeConsultar()) {
      return;
    }
    this.consultando.set(true);
    this.erroConsulta.set(null);
    const partida = this.partida();
    const pensamento = {
      situacao: this.situacao().trim() || null,
      candidatos: this.candidatos().trim() || null,
      trava: this.trava().trim() || null
    };
    const temPensamento = Object.values(pensamento).some((valor) => valor !== null);

    const resposta = await this.service.consultar({
      partida_espelho_id: partida.id,
      lances: partida.lances,
      fen_inicial: partida.fenInicial,
      cor_jogador: partida.cor,
      plataforma: partida.plataforma,
      adversario: partida.adversario.trim() || null,
      pensamento: temPensamento ? pensamento : null
    });
    this.consultando.set(false);

    if (!resposta.success || !resposta.dados) {
      this.erroConsulta.set(resposta.error ?? 'Não foi possível consultar a posição.');
      return;
    }

    const chave = resposta.dados.id ?? `local-${Date.now()}`;
    this.consultas.update((lista) => [{ chave, dados: resposta.dados! }, ...lista]);
    this.revelado.update((mapa) => ({ ...mapa, [chave]: 1 }));
    // O servidor é quem sabe quantas sobram; a lista local só cobre esta aba.
    this.limitePorPartida.set(this.consultas().length + resposta.dados.consultas_restantes);
    this.limparPensamento();
  }

  private limparPensamento(): void {
    this.situacao.set('');
    this.candidatos.set('');
    this.trava.set('');
    this.mostrarPensamento.set(false);
  }

  nivel(chave: string): NivelRevelado {
    return this.revelado()[chave] ?? 1;
  }

  revelar(chave: string, nivel: NivelRevelado): void {
    this.revelado.update((mapa) => ({ ...mapa, [chave]: Math.max(this.nivel(chave), nivel) as NivelRevelado }));
  }

  rotuloCor(cor: CorJogador): string {
    return cor === 'BRANCAS' ? 'Brancas' : 'Pretas';
  }
}
