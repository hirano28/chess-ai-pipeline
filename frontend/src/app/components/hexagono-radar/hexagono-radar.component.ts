import {
  Component,
  ElementRef,
  OnDestroy,
  OnInit,
  effect,
  inject,
  signal,
  viewChild
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
  Chart,
  Filler,
  Legend,
  LineElement,
  PointElement,
  RadarController,
  RadialLinearScale,
  Tooltip
} from 'chart.js';
import {
  AnaliseHexagonoMetricas,
  SupabaseService
} from '../../services/supabase.service';
import { ROTULOS_CATEGORIA_HEXAGONO, TreinoService } from '../../services/treino.service';
import { SessoesTreinoComponent } from '../sessoes-treino/sessoes-treino.component';
import { NarrativaAnaliseComponent } from '../narrativa-analise/narrativa-analise.component';
import { PerguntasPendentesComponent } from '../perguntas-pendentes/perguntas-pendentes.component';
import { RepertorioInsightsComponent } from '../repertorio-insights/repertorio-insights.component';
import { PuzzlesInsightsComponent } from '../puzzles-insights/puzzles-insights.component';

Chart.register(
  RadarController,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend
);

/** Mesma pilha de --font-sans em src/styles.css: o gráfico não pode destoar da UI. */
const FAMILIA_UI = "Inter, ui-sans-serif, system-ui, -apple-system, sans-serif";

const CATEGORIAS = [
  'TATICA',
  'ESTRATEGIA',
  'FINAIS',
  'ESTRUTURA_DE_PEOES',
  'GESTAO_DE_TEMPO',
  'CALCULO'
] as const;

type Categoria = (typeof CATEGORIAS)[number];

@Component({
  selector: 'app-hexagono-radar',
  standalone: true,
  imports: [
    RouterLink,
    SessoesTreinoComponent,
    NarrativaAnaliseComponent,
    PerguntasPendentesComponent,
    RepertorioInsightsComponent,
    PuzzlesInsightsComponent
  ],
  templateUrl: './hexagono-radar.component.html'
})
export class HexagonoRadarComponent implements OnInit, OnDestroy {
  private readonly radarCanvas =
    viewChild<ElementRef<HTMLCanvasElement>>('radarCanvas');

  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  /** Auditoria de UX pós-D-49: "ainda não há análise" é um estado vazio
   * (usuário novo), não um erro — tinha ficado renderizado como .aviso-erro. */
  readonly semAnalise = signal(false);
  readonly dados = signal<AnaliseHexagonoMetricas | null>(null);
  readonly modoVisualizacao = signal<'erros' | 'forcas'>('erros');
  readonly categorias = CATEGORIAS;
  readonly rotulosCategoria = ROTULOS_CATEGORIA_HEXAGONO;
  readonly focandoCategoria = signal<string | null>(null);

  private readonly supabaseService = inject(SupabaseService);
  private readonly treinoService = inject(TreinoService);
  private readonly router = inject(Router);
  private chart?: Chart<'radar'>;

  constructor() {
    // Cria/atualiza o gráfico apenas quando dados e canvas existem no DOM.
    effect(() => {
      const analise = this.dados();
      const canvas = this.radarCanvas();
      const modo = this.modoVisualizacao();
      if (!analise?.frequencia_por_categoria || !canvas) {
        return;
      }
      this.renderizarGrafico(canvas.nativeElement, analise, modo);
    });
  }

  ngOnInit(): void {
    void this.carregarAnalise();
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }

  selecionarModo(modo: 'erros' | 'forcas'): void {
    this.modoVisualizacao.set(modo);
  }

  /** D-49: injeta exercícios do catálogo tático na fila de hoje, focados
   * nesta categoria, e leva o usuário direto pra tela de treino. */
  async focar(categoria: Categoria): Promise<void> {
    if (this.focandoCategoria()) {
      return;
    }
    this.focandoCategoria.set(categoria);
    await this.treinoService.focarCategoria(categoria);
    this.focandoCategoria.set(null);
    await this.router.navigateByUrl('/treino');
  }

  private async carregarAnalise(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    this.semAnalise.set(false);

    try {
      const analise = await this.supabaseService.getUltimaAnaliseHexagono();
      if (!analise?.frequencia_por_categoria) {
        this.semAnalise.set(true);
        return;
      }

      this.dados.set(analise);
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.error.set(`Não foi possível carregar o hexágono agora. ${message}`);
    } finally {
      this.loading.set(false);
    }
  }

  private renderizarGrafico(
    canvas: HTMLCanvasElement,
    analise: AnaliseHexagonoMetricas,
    modo: 'erros' | 'forcas'
  ): void {
    const frequencias = analise.frequencia_por_categoria ?? {};
    const valores = CATEGORIAS.map((categoria) => this.numeroDaCategoria(frequencias, categoria));
    const maiorValor = Math.max(...valores, 0);
    const dadosNormalizados = maiorValor > 0
      ? valores.map((valor) => Math.round((valor / maiorValor) * 100))
      : valores;
    const dadosExibidos = modo === 'forcas'
      ? dadosNormalizados.map((valor) => 100 - valor)
      : dadosNormalizados;
    const label = modo === 'forcas'
      ? 'Pontos fortes (aprox.) (%)'
      : 'Frequência dos erros (%)';

    if (this.chart) {
      this.chart.data.datasets[0].data = dadosExibidos;
      this.chart.data.datasets[0].label = label;
      this.chart.update();
      return;
    }

    const corLatao500 = this.corToken('--color-latao-500', '#dea34c');
    const corLatao300 = this.corToken('--color-latao-300', '#f4c878');
    const corArdosia850 = this.corToken('--color-ardosia-850', '#101b20');
    const corArdosia800 = this.corToken('--color-ardosia-800', '#142228');
    const corLinhaForte = this.corToken('--color-linha-forte', '#2b3f47');
    const corBruma200 = this.corToken('--color-bruma-200', '#d5e0e1');
    const corBruma300 = this.corToken('--color-bruma-300', '#b9c7c8');
    const corBruma500 = this.corToken('--color-bruma-500', '#74898c');
    const corMarfim = this.corToken('--color-marfim', '#f4f0e6');

    this.chart = new Chart(canvas, {
      type: 'radar',
      data: {
        labels: [...CATEGORIAS],
        datasets: [
          {
            label,
            data: dadosExibidos,
            backgroundColor: 'rgba(222, 163, 76, 0.18)',
            borderColor: corLatao500,
            pointBackgroundColor: corLatao300,
            pointBorderColor: corArdosia800,
            pointHoverBackgroundColor: '#fff8e8',
            pointHoverBorderColor: corLatao500,
            borderWidth: 2,
            pointRadius: 3.5,
            pointHoverRadius: 6,
            pointBorderWidth: 2
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        // As cores são lidas dos tokens de src/styles.css em tempo real (via
        // corToken()), não copiadas à mão - evita o gráfico ficar com uma
        // paleta desatualizada se os tokens forem retocados.
        scales: {
          r: {
            beginAtZero: true,
            min: 0,
            max: 100,
            ticks: {
              stepSize: 25,
              backdropColor: 'transparent',
              color: corBruma500,
              font: { size: 10, family: FAMILIA_UI }
            },
            grid: { color: 'rgba(147, 169, 171, 0.14)' },
            angleLines: { color: 'rgba(147, 169, 171, 0.14)' },
            pointLabels: {
              color: corBruma200,
              font: { size: 11, weight: 600, family: FAMILIA_UI }
            }
          }
        },
        plugins: {
          // O título do cartão e o controle segmentado já dizem o que está no
          // gráfico; a legenda só repetiria isso ocupando espaço vertical.
          legend: { display: false },
          tooltip: {
            backgroundColor: corArdosia850,
            borderColor: corLinhaForte,
            borderWidth: 1,
            titleColor: corMarfim,
            bodyColor: corBruma300,
            titleFont: { family: FAMILIA_UI, weight: 600 },
            bodyFont: { family: FAMILIA_UI },
            padding: 10,
            displayColors: false
          }
        }
      }
    });
  }

  /** Lê um token de cor de src/styles.css em tempo real (fallback se o
   * token não existir ou `document` não estiver disponível, ex. SSR/testes). */
  private corToken(nomeVariavel: string, fallback: string): string {
    if (typeof document === 'undefined') {
      return fallback;
    }
    const valor = getComputedStyle(document.documentElement).getPropertyValue(nomeVariavel).trim();
    return valor || fallback;
  }

  private numeroDaCategoria(
    frequencias: Record<string, number>,
    categoria: Categoria
  ): number {
    const valor = frequencias[categoria];
    return typeof valor === 'number' && Number.isFinite(valor) ? Math.max(0, valor) : 0;
  }
}
