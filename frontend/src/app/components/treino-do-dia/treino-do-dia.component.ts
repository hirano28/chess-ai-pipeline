import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import {
  ItemFilaTreino,
  ROTULOS_CATEGORIA_HEXAGONO,
  ResultadoTreino,
  ResultadoTrecho,
  TreinoService
} from '../../services/treino.service';
import { TabuleiroPreviewComponent } from '../tabuleiro-preview/tabuleiro-preview.component';

@Component({
  selector: 'app-treino-do-dia',
  standalone: true,
  imports: [RouterLink, TabuleiroPreviewComponent],
  templateUrl: './treino-do-dia.component.html'
})
export class TreinoDoDiaComponent implements OnInit, OnDestroy {
  readonly fila = signal<ItemFilaTreino[]>([]);
  readonly feitasHoje = signal(0);
  readonly totalHoje = signal(0);
  readonly vencidosTotal = signal(0);
  /** Quando preenchido, a fila está filtrada pelo bloco de prática de uma
   * sessão de treino focado (D-56) e a tela diz isso em vez de parecer o
   * Treino Diário normal com menos cards. */
  readonly sessaoId = signal<string | null>(null);
  /** Quantos cards venceram além dos que cabem na tela. */
  readonly ocultosPeloTeto = computed(() =>
    Math.max(0, this.vencidosTotal() - this.fila().length)
  );

  readonly carregando = signal(true);
  readonly enviando = signal(false);
  readonly erro = signal<string | null>(null);

  readonly lance = signal('');
  readonly resultado = signal<ResultadoTreino | null>(null);

  /** Segundos que ainda restam no card cronometrado (D-55), ou null quando o
   * card não é de Gestão de Tempo. */
  readonly segundosRestantes = signal<number | null>(null);
  readonly tempoEsgotado = computed(() => this.segundosRestantes() === 0);

  readonly itemAtual = computed<ItemFilaTreino | null>(() => this.fila()[0] ?? null);
  readonly formularioValido = computed(
    () => this.lance().trim().length > 0 && !this.enviando()
  );

  /**
   * D-66: card de EROSAO, jogado lance a lance contra o motor.
   *
   * `trechoAtual` é o estado que veio da fila (ou o último devolvido pelo
   * servidor); `ultimoPasso` guarda a resposta do lance anterior, que é onde
   * mora a jogada do adversário. O veredito só existe em `resultadoTrecho`, e
   * só depois que a janela fecha.
   */
  readonly passoTrecho = signal<ResultadoTrecho | null>(null);
  readonly ehTrecho = computed(() => this.itemAtual()?.tipo_evento === 'EROSAO');
  readonly resultadoTrecho = computed<ResultadoTrecho | null>(() => {
    const passo = this.passoTrecho();
    return passo?.concluido ? passo : null;
  });
  /** A posição a jogar agora: a do último lance, ou a que veio na fila. */
  readonly fenDoTrecho = computed(
    () => this.passoTrecho()?.fen ?? this.itemAtual()?.fen ?? ''
  );
  readonly lancesFeitos = computed(
    () => this.passoTrecho()?.lances_feitos ?? this.itemAtual()?.trecho?.lances_feitos ?? 0
  );
  readonly totalDoTrecho = computed(
    () => this.passoTrecho()?.total_lances ?? this.itemAtual()?.trecho?.total_lances ?? 0
  );
  readonly historicoDoTrecho = computed(
    () => this.passoTrecho()?.historico ?? this.itemAtual()?.trecho?.historico ?? []
  );
  /** Resposta do adversário ao lance anterior, para a tela poder dizer o que
   * aconteceu entre a posição de antes e a de agora. */
  readonly respostaDoAdversario = computed(() => {
    const passo = this.passoTrecho();
    return passo && !passo.concluido ? passo.lance_oponente : null;
  });

  private readonly treinoService = inject(TreinoService);
  private readonly route = inject(ActivatedRoute);
  private cronometro: ReturnType<typeof setInterval> | null = null;
  private iniciadoEm = 0;

  ngOnInit(): void {
    this.sessaoId.set(this.route.snapshot.queryParamMap.get('sessao'));
    this.carregarFila();
  }

  ngOnDestroy(): void {
    this.pararCronometro();
  }

  /** "1:05" — o formato do relógio de xadrez, não "65 s". */
  formatarRelogio(segundos: number): string {
    const minutos = Math.floor(segundos / 60);
    return `${minutos}:${String(segundos % 60).padStart(2, '0')}`;
  }

  private pararCronometro(): void {
    if (this.cronometro !== null) {
      clearInterval(this.cronometro);
      this.cronometro = null;
    }
  }

  /** Começa a contar quando o card cronometrado entra em cena. O tempo corre
   * de verdade: estourá-lo rebaixa o agendamento do card no backend, senão o
   * cronômetro seria enfeite numa categoria cuja falha medida É o tempo. */
  private iniciarCronometro(item: ItemFilaTreino | null): void {
    this.pararCronometro();
    const limite = item?.segundos_sugeridos ?? null;
    if (limite === null) {
      this.segundosRestantes.set(null);
      return;
    }

    this.iniciadoEm = Date.now();
    this.segundosRestantes.set(limite);
    this.cronometro = setInterval(() => {
      const decorrido = Math.floor((Date.now() - this.iniciadoEm) / 1000);
      const restante = Math.max(0, limite - decorrido);
      this.segundosRestantes.set(restante);
      if (restante === 0) {
        this.pararCronometro();
      }
    }, 1000);
  }

  private segundosGastos(item: ItemFilaTreino): number | null {
    return item.segundos_sugeridos === null
      ? null
      : Math.round((Date.now() - this.iniciadoEm) / 1000);
  }

  async carregarFila(): Promise<void> {
    this.carregando.set(true);
    this.erro.set(null);

    const resposta = await this.treinoService.getFila(this.sessaoId());
    if (resposta.sessaoExpirada) {
      this.erro.set(resposta.error ?? 'Sessão expirada.');
      this.carregando.set(false);
      return;
    }
    if (!resposta.success || !resposta.fila) {
      this.erro.set(resposta.error ?? 'Não foi possível carregar a fila de treino.');
      this.carregando.set(false);
      return;
    }

    this.fila.set(resposta.fila.itens);
    this.feitasHoje.set(resposta.fila.feitas_hoje);
    this.totalHoje.set(resposta.fila.total_hoje);
    this.vencidosTotal.set(resposta.fila.vencidos_total ?? resposta.fila.itens.length);
    this.carregando.set(false);
    this.iniciarCronometro(this.itemAtual());
  }

  /**
   * Joga um lance do trecho (D-66). O servidor responde com a jogada do motor
   * e a posição nova — e nada sobre quanto o lance custou, até a janela fechar.
   */
  async jogarLanceDoTrecho(): Promise<void> {
    const item = this.itemAtual();
    if (!item || !this.formularioValido() || this.enviando()) {
      return;
    }

    this.enviando.set(true);
    this.erro.set(null);

    const resposta = await this.treinoService.jogarTrecho(item.fila_id, this.lance().trim());

    if (resposta.sessaoExpirada) {
      this.erro.set(resposta.error ?? 'Sessão expirada.');
      this.enviando.set(false);
      return;
    }
    if (resposta.trechoReiniciado) {
      // O servidor zerou o progresso: recarregar é o único jeito de voltar a
      // uma posição que os dois lados concordam qual é. O aviso é posto DEPOIS
      // da recarga porque `carregarFila` limpa `erro` — senão o trecho voltaria
      // ao começo sem nada na tela explicando por quê.
      this.passoTrecho.set(null);
      this.lance.set('');
      this.enviando.set(false);
      await this.carregarFila();
      this.erro.set(resposta.error ?? 'O trecho foi reiniciado.');
      return;
    }
    if (!resposta.success || !resposta.resultado) {
      this.erro.set(resposta.error ?? 'Não foi possível avaliar o lance.');
      this.enviando.set(false);
      return;
    }

    this.passoTrecho.set(resposta.resultado);
    this.lance.set('');
    this.enviando.set(false);
  }

  async responder(): Promise<void> {
    if (this.ehTrecho()) {
      await this.jogarLanceDoTrecho();
      return;
    }

    const item = this.itemAtual();
    if (!item || !this.formularioValido() || this.enviando()) {
      return;
    }

    this.enviando.set(true);
    this.erro.set(null);
    // Congela o relógio no instante da resposta: o que vai para o backend é o
    // tempo até decidir, não o tempo até a avaliação do Stockfish voltar.
    const segundosGastos = this.segundosGastos(item);
    this.pararCronometro();

    const resposta = await this.treinoService.responder(
      item.fila_id,
      this.lance().trim(),
      segundosGastos
    );

    if (resposta.sessaoExpirada) {
      this.erro.set(resposta.error ?? 'Sessão expirada.');
      this.enviando.set(false);
      return;
    }
    if (!resposta.success || !resposta.resultado) {
      this.erro.set(resposta.error ?? 'Não foi possível avaliar o lance.');
      this.enviando.set(false);
      return;
    }

    this.resultado.set(resposta.resultado);
    this.enviando.set(false);
  }

  /** Avança para o próximo card da fila, descartando o feedback do anterior. */
  proxima(): void {
    this.fila.update((itens) => itens.slice(1));
    this.feitasHoje.update((n) => n + 1);
    this.lance.set('');
    this.resultado.set(null);
    this.passoTrecho.set(null);
    this.erro.set(null);
    this.iniciarCronometro(this.itemAtual());
  }

  /** Rótulo amigável da categoria de um exercício de catálogo (D-49/D-55). */
  rotuloCategoria(categoria: string | null): string {
    return (categoria && ROTULOS_CATEGORIA_HEXAGONO[categoria]) || 'Exercício de catálogo';
  }

  /** "−4.2%" ou "+1.3%": queda positiva é perda, negativa é melhora. */
  formatarQueda(queda: number): string {
    const sinal = queda > 0 ? '−' : '+';
    return `${sinal}${Math.abs(queda).toFixed(1)}%`;
  }

  /** "Lances 12 a 19" — a janela que escorregou, no selo do card de trecho. */
  rotuloJanela(item: ItemFilaTreino): string {
    if (item.numero_lance_fim && item.numero_lance) {
      return `Lances ${item.numero_lance} a ${item.numero_lance_fim}`;
    }
    return 'Trecho da sua partida';
  }

  /** O que este card é, para o selo de origem. */
  rotuloOrigem(item: ItemFilaTreino): string {
    if (item.origem === 'lance_critico') {
      return item.tipo_evento === 'EROSAO' ? 'Trecho da sua partida' : 'Da sua partida';
    }
    if (item.origem === 'exercicio_posicional') {
      return `Partida real · ${this.rotuloCategoria(item.categoria)}`;
    }
    return `Exercício · ${this.rotuloCategoria(item.categoria)}`;
  }

  /** Variante de `.selo` (ver src/styles.css) — mesmo mapeamento do Laboratório. */
  corBadgeQualidadeLance(qualidade: string): string {
    switch (qualidade) {
      case 'BOM':
        return 'selo-sucesso';
      case 'SUBOTIMO':
        return 'selo-latao';
      default:
        return 'selo-perigo';
    }
  }
}
