import { Component, OnDestroy, OnInit, computed, effect, inject, signal } from '@angular/core';
import { Chess } from 'chess.js';
import {
  ConsultaAoVivo,
  ConsultaAoVivoService,
  CorJogador,
  EstadoPartidaSincronizada,
  PartidaEmAndamento,
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

export interface ConsultaExibida {
  chave: string;
  dados: ConsultaAoVivo;
}

/** De quanto em quanto tempo a partida sincronizada é atualizada. */
export const INTERVALO_SINCRONIZACAO_MS = 4000;
/** Quanto esperar depois de a plataforma recusar (o Lichess pede um minuto). */
export const ESPERA_APOS_RECUSA_MS = 60000;

/**
 * Consulta ao vivo (D-67): espelhar uma partida em andamento e pedir ajuda
 * para PENSAR quando travar. Exclusiva do dono do projeto.
 *
 * A resposta ensina a avaliar a posição — que tipo de posição é, um roteiro
 * do que olhar e por quê, e o princípio por trás — e não traz lance nenhum
 * (D-70): a decisão continua sendo do jogador.
 *
 * Desde o D-69 a partida também pode vir da plataforma (Lichess ou Chess.com):
 * a tela atualiza sozinha a cada poucos segundos, e o tabuleiro deixa de aceitar
 * lance à mão para não divergir da partida real.
 */
@Component({
  selector: 'app-consulta-ao-vivo',
  standalone: true,
  imports: [TabuleiroInterativoComponent],
  templateUrl: './consulta-ao-vivo.component.html'
})
export class ConsultaAoVivoComponent implements OnInit, OnDestroy {
  private readonly service = inject(ConsultaAoVivoService);

  // --- D-69: sincronização com a partida em andamento -----------------------
  readonly buscandoPartidas = signal(false);
  readonly partidasDisponiveis = signal<PartidaEmAndamento[] | null>(null);
  readonly avisosSincronizacao = signal<string[]>([]);
  readonly erroSincronizacao = signal<string | null>(null);
  readonly avisoFimDePartida = signal<string | null>(null);
  readonly sincronizada = computed(() => this.partida().sincronizada ?? null);
  private temporizador: ReturnType<typeof setInterval> | null = null;
  private pausadoAte = 0;
  private atualizando = false;

  readonly partida = signal<PartidaEspelho>(novaPartida('BRANCAS', 'LICHESS', ''));
  readonly consultas = signal<ConsultaExibida[]>([]);
  readonly limitePorPartida = signal(3);

  readonly lanceDigitado = signal('');
  readonly erroLance = signal<string | null>(null);

  readonly situacao = signal('');
  readonly candidatos = signal('');
  readonly trava = signal('');
  readonly mostrarPensamento = signal(false);

  readonly consultando = signal(false);
  readonly erroConsulta = signal<string | null>(null);

  /** D-68: dúvidas de partidas anteriores, com o que aconteceu depois. */
  readonly recentes = signal<ConsultaAoVivo[]>([]);
  readonly duvidasAnteriores = computed(() =>
    this.recentes().filter((consulta) => consulta.partida_espelho_id !== this.partida().id)
  );

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
    const [, recentes] = await Promise.all([
      salva ? this.carregarConsultas(salva.id) : Promise.resolve(),
      this.service.listarRecentes()
    ]);
    if (recentes.success && recentes.dados) {
      this.recentes.set(recentes.dados);
    }
    if (salva?.sincronizada) {
      this.iniciarAtualizacao();
    }
  }

  ngOnDestroy(): void {
    this.pararTemporizador();
  }

  // --- D-69: sincronização --------------------------------------------------

  /** Lista as suas partidas em andamento nas duas plataformas. */
  async buscarPartidas(): Promise<void> {
    this.buscandoPartidas.set(true);
    this.erroSincronizacao.set(null);
    const resposta = await this.service.listarPartidasEmAndamento();
    this.buscandoPartidas.set(false);
    if (!resposta.success || !resposta.dados) {
      this.erroSincronizacao.set(resposta.error ?? 'Não foi possível listar suas partidas.');
      return;
    }
    this.partidasDisponiveis.set(resposta.dados.partidas);
    this.avisosSincronizacao.set(resposta.dados.avisos);
  }

  /** Passa a acompanhar uma partida da plataforma no lugar do espelho à mão. */
  async sincronizar(escolhida: PartidaEmAndamento): Promise<void> {
    this.pararTemporizador();
    this.avisoFimDePartida.set(null);
    this.erroSincronizacao.set(null);
    this.partidasDisponiveis.set(null);
    this.partida.set({
      id: escolhida.partida_espelho_id,
      fenInicial: escolhida.fen,
      lances: [],
      cor: escolhida.cor,
      plataforma: escolhida.plataforma,
      adversario: escolhida.adversario,
      sincronizada: {
        plataforma: escolhida.plataforma,
        gameId: escolhida.game_id,
        url: escolhida.url,
        ranqueada: escolhida.ranqueada,
        ritmo: escolhida.ritmo,
        historicoCompleto: false
      }
    });
    this.consultas.set([]);
    // O id da partida espelhada vem da partida real: consultas feitas antes de
    // uma recarga, ou em outro aparelho, voltam junto.
    await Promise.all([this.carregarConsultas(escolhida.partida_espelho_id), this.atualizarPartida()]);
    // A primeira leitura pode ter descoberto que a partida já terminou.
    if (this.partida().sincronizada) {
      this.iniciarAtualizacao();
    }
  }

  /** Volta ao espelho à mão, a partir da posição em que a sincronização parou. */
  pararSincronizacao(): void {
    this.pararTemporizador();
    this.partida.update((p) => ({ ...p, sincronizada: null }));
  }

  /** Busca a posição atual. Chamado pelo temporizador e depois de consultar. */
  async atualizarPartida(): Promise<void> {
    const sinc = this.partida().sincronizada;
    if (!sinc || this.atualizando || Date.now() < this.pausadoAte) {
      return;
    }
    this.atualizando = true;
    const resposta = await this.service.estadoPartida(sinc.plataforma, sinc.gameId);
    this.atualizando = false;
    // A sincronização pode ter sido parada enquanto a resposta vinha.
    if (this.partida().sincronizada?.gameId !== sinc.gameId) {
      return;
    }

    if (resposta.success && resposta.dados) {
      this.erroSincronizacao.set(null);
      this.aplicarEstado(resposta.dados);
      return;
    }
    if (resposta.terminou) {
      this.pararTemporizador();
      this.partida.update((p) => ({ ...p, sincronizada: null }));
      this.avisoFimDePartida.set(
        'A partida terminou. O que aconteceu com as suas dúvidas aparece depois da coleta desta noite.'
      );
      return;
    }
    // Plataforma recusou ou caiu: espera um minuto antes de insistir.
    this.pausadoAte = Date.now() + ESPERA_APOS_RECUSA_MS;
    this.erroSincronizacao.set(resposta.error ?? 'A plataforma não respondeu.');
  }

  private aplicarEstado(estado: EstadoPartidaSincronizada): void {
    this.partida.update((p) => ({
      ...p,
      // Sem histórico completo, a posição exata vale mais que uma lista de
      // lances que não chega nela.
      fenInicial: estado.historico_completo ? estado.fen_inicial : estado.fen,
      lances: estado.historico_completo ? estado.lances : [],
      cor: estado.cor,
      adversario: estado.adversario,
      sincronizada: p.sincronizada
        ? { ...p.sincronizada, historicoCompleto: estado.historico_completo }
        : p.sincronizada
    }));
  }

  private iniciarAtualizacao(): void {
    this.pararTemporizador();
    this.temporizador = setInterval(() => {
      if (typeof document === 'undefined' || document.visibilityState === 'visible') {
        void this.atualizarPartida();
      }
    }, INTERVALO_SINCRONIZACAO_MS);
  }

  private pararTemporizador(): void {
    if (this.temporizador !== null) {
      clearInterval(this.temporizador);
      this.temporizador = null;
    }
  }

  rotuloPartida(p: PartidaEmAndamento): string {
    const plataforma = p.plataforma === 'LICHESS' ? 'Lichess' : 'Chess.com';
    const tipo = p.ranqueada ? 'ranqueada' : 'casual';
    return `${plataforma} · ${this.rotuloCor(p.cor)} contra ${p.adversario} · ${p.ritmo} · ${tipo}`;
  }

  /** Uma frase sobre o que aconteceu com a dúvida depois (D-68). */
  descreverDesfecho(consulta: ConsultaAoVivo): string {
    const desfecho = consulta.desfecho;
    if (desfecho.status === 'pendente') {
      return 'Ainda sem desfecho: a partida é procurada na coleta de toda noite.';
    }
    if (desfecho.status === 'sem_partida') {
      return 'A partida não apareceu na coleta — o desfecho desta dúvida ficou desconhecido.';
    }
    if (!desfecho.lance_jogado) {
      return 'A partida terminou nesta posição.';
    }
    // Depois da partida, comparar com o motor já não tira decisão de ninguém.
    const relacao = desfecho.era_o_melhor
      ? 'era o lance do motor'
      : desfecho.era_candidato
        ? 'estava entre os lances que o motor considerava'
        : 'não estava entre os lances que o motor considerava';
    const queda = desfecho.queda_win_percent;
    const custo =
      queda === null
        ? ''
        : queda > 0
          ? ` e custou ${queda.toFixed(1)}%`
          : ` e melhorou a posição em ${Math.abs(queda).toFixed(1)}%`;
    return `Você jogou ${desfecho.lance_jogado}: ${relacao}${custo}.`;
  }

  /** Cor do desfecho: verde se não perdeu nada relevante, vermelho se a dúvida virou erro. */
  classeDesfecho(consulta: ConsultaAoVivo): string {
    const queda = consulta.desfecho.queda_win_percent;
    if (consulta.desfecho.status !== 'casada' || queda === null) {
      return 'text-bruma-400';
    }
    return queda >= 10 ? 'text-perigo' : queda <= 3 ? 'text-sucesso' : 'text-latao-500';
  }

  private async carregarConsultas(partidaId: string): Promise<void> {
    const resposta = await this.service.listarDaPartida(partidaId);
    if (resposta.success && resposta.dados) {
      const exibidas = resposta.dados
        .map((dados, indice) => ({ chave: dados.id ?? `carregada-${indice}`, dados }))
        .reverse();
      this.consultas.set(exibidas);
    }
  }

  jogarDoTabuleiro(lance: LanceTabuleiro): void {
    if (this.sincronizada()) {
      return;
    }
    const copia = new Chess(this.fen());
    try {
      const feito = copia.move({ from: lance.from, to: lance.to, promotion: lance.promotion });
      this.acrescentarLance(feito.san);
    } catch {
      this.erroLance.set('Lance ilegal nessa posição.');
    }
  }

  jogarDoTexto(): void {
    if (this.sincronizada()) {
      return;
    }
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
    if (this.sincronizada()) {
      return;
    }
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
    this.pararTemporizador();
    this.avisoFimDePartida.set(null);
    this.partida.set(novaPartida(atual.cor, atual.plataforma, atual.adversario));
    this.consultas.set([]);
    this.limparPensamento();
    this.erroConsulta.set(null);
    this.erroLance.set(null);
  }

  /** Substitui os lances pelos de um PGN colado (a partida continua a mesma). */
  aplicarPgn(): void {
    if (this.sincronizada()) {
      return;
    }
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
      pensamento: temPensamento ? pensamento : null,
      sincronizada: partida.sincronizada
        ? { plataforma: partida.sincronizada.plataforma, game_id: partida.sincronizada.gameId }
        : null
    });
    this.consultando.set(false);

    if (!resposta.success || !resposta.dados) {
      this.erroConsulta.set(resposta.error ?? 'Não foi possível consultar a posição.');
      return;
    }

    const chave = resposta.dados.id ?? `local-${Date.now()}`;
    this.consultas.update((lista) => [{ chave, dados: resposta.dados! }, ...lista]);
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

  rotuloCor(cor: CorJogador): string {
    return cor === 'BRANCAS' ? 'Brancas' : 'Pretas';
  }
}
