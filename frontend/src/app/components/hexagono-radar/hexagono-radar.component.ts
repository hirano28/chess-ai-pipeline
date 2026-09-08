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
import { SessoesTreinoComponent } from '../sessoes-treino/sessoes-treino.component';
import { NarrativaAnaliseComponent } from '../narrativa-analise/narrativa-analise.component';
import { PerguntasPendentesComponent } from '../perguntas-pendentes/perguntas-pendentes.component';

Chart.register(
  RadarController,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend
);

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
  imports: [SessoesTreinoComponent, NarrativaAnaliseComponent, PerguntasPendentesComponent],
  templateUrl: './hexagono-radar.component.html'
})
export class HexagonoRadarComponent implements OnInit, OnDestroy {
  private readonly radarCanvas =
    viewChild<ElementRef<HTMLCanvasElement>>('radarCanvas');

  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly dados = signal<AnaliseHexagonoMetricas | null>(null);
  readonly modoVisualizacao = signal<'erros' | 'forcas'>('erros');

  private readonly supabaseService = inject(SupabaseService);
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

  private async carregarAnalise(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);

    try {
      const analise = await this.supabaseService.getUltimaAnaliseHexagono();
      if (!analise?.frequencia_por_categoria) {
        this.error.set('Ainda não há uma análise de partidas disponível.');
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

    this.chart = new Chart(canvas, {
      type: 'radar',
      data: {
        labels: [...CATEGORIAS],
        datasets: [
          {
            label,
            data: dadosExibidos,
            backgroundColor: 'rgba(222, 163, 76, 0.2)',
            borderColor: '#dea34c',
            pointBackgroundColor: '#f4c878',
            pointBorderColor: '#162126',
            pointHoverBackgroundColor: '#fff8e8',
            pointHoverBorderColor: '#dea34c',
            borderWidth: 2,
            pointRadius: 4
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          r: {
            beginAtZero: true,
            min: 0,
            max: 100,
            ticks: {
              stepSize: 25,
              backdropColor: 'transparent',
              color: '#b9c7c8'
            },
            grid: { color: 'rgba(185, 199, 200, 0.24)' },
            angleLines: { color: 'rgba(185, 199, 200, 0.24)' },
            pointLabels: {
              color: '#f4f0e6',
              font: { size: 11, weight: 600 }
            }
          }
        },
        plugins: {
          legend: {
            labels: { color: '#f4f0e6' }
          }
        }
      }
    });
  }

  private numeroDaCategoria(
    frequencias: Record<string, number>,
    categoria: Categoria
  ): number {
    const valor = frequencias[categoria];
    return typeof valor === 'number' && Number.isFinite(valor) ? Math.max(0, valor) : 0;
  }
}
