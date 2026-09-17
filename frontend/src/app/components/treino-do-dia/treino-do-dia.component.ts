import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import {
  ItemFilaTreino,
  ROTULOS_CATEGORIA_HEXAGONO,
  ResultadoTreino,
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

  async responder(): Promise<void> {
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
    this.erro.set(null);
    this.iniciarCronometro(this.itemAtual());
  }

  /** Rótulo amigável da categoria de um exercício de catálogo (D-49/D-55). */
  rotuloCategoria(categoria: string | null): string {
    return (categoria && ROTULOS_CATEGORIA_HEXAGONO[categoria]) || 'Exercício de catálogo';
  }

  /** O que este card é, para o selo de origem. */
  rotuloOrigem(item: ItemFilaTreino): string {
    if (item.origem === 'lance_critico') {
      return 'Da sua partida';
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
