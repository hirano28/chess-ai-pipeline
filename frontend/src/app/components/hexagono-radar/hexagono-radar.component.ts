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
import {
  ComposicaoCadencia,
  ROTULOS_CADENCIA,
  RevisaoAvulsaService
} from '../../services/revisao-avulsa.service';
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
  /** Retorno do último "Focar": antes o resultado era descartado e o usuário
   * caía numa /treino inalterada sem entender por quê (D-52). */
  readonly avisoFoco = signal<{ texto: string; tipo: 'erro' | 'info' } | null>(null);
  /** Contagem de exercícios de catálogo por categoria (D-53). `null` enquanto
   * não carregou ou se a consulta falhou — nesse caso nenhum botão é bloqueado,
   * porque supor "não tem material" sem saber seria pior que deixar tentar. */
  readonly catalogoPorCategoria = signal<Record<string, number> | null>(null);
  /** Composição do corpus por cadência (D-57). É uma ressalva, não uma
   * métrica: se quase tudo é blitz, o gargalo abaixo carrega junto o efeito do
   * relógio, e esconder isso seria vender um diagnóstico mais firme do que ele
   * é. `null` enquanto não carregou ou se a consulta falhou. */
  readonly composicaoCadencia = signal<ComposicaoCadencia | null>(null);
  readonly rotulosCadencia = ROTULOS_CADENCIA;
  /** Recorte do Hexágono por cadência (D-63). `null` = todas as partidas. É a
   * resposta à ressalva acima: em vez de só avisar que 72% é blitz, deixa o
   * usuário ver o hexágono só das blitz, ou só das rápidas. */
  readonly cadenciaSelecionada = signal<string | null>(null);

  private readonly supabaseService = inject(SupabaseService);
  private readonly treinoService = inject(TreinoService);
  private readonly revisaoAvulsaService = inject(RevisaoAvulsaService);
  private readonly router = inject(Router);
  private chart?: Chart<'radar'>;

  constructor() {
    // Cria/atualiza o gráfico apenas quando dados e canvas existem no DOM.
    effect(() => {
      // `metricasExibidas()` lê `dados` e `cadenciaSelecionada`, então trocar o
      // recorte redesenha o radar pelo mesmo caminho que trocar o modo.
      const analise = this.metricasExibidas();
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
    void this.carregarDisponibilidadeFoco();
    void this.carregarComposicaoCadencia();
  }

  /** Só alerta quando uma cadência domina de fato o corpus: abaixo disso a
   * ressalva viraria ruído em toda visita. */
  cadenciaDominaOCorpus(): boolean {
    const composicao = this.composicaoCadencia();
    return !!composicao && composicao.total > 0 && composicao.percentual_dominante >= 50;
  }

  /** "59,2" — separador decimal em português, não o ponto do JSON. */
  percentualDominanteFormatado(): string {
    const percentual = this.composicaoCadencia()?.percentual_dominante ?? 0;
    return percentual.toLocaleString('pt-BR', { maximumFractionDigits: 1 });
  }

  rotuloCadencia(cadencia: string | null): string {
    return (cadencia && this.rotulosCadencia[cadencia]) || 'cadência desconhecida';
  }

  /** Cadências presentes, da mais frequente para a menos. */
  cadenciasOrdenadas(): { cadencia: string; total: number }[] {
    const porCadencia = this.composicaoCadencia()?.por_cadencia ?? {};
    return Object.entries(porCadencia)
      .map(([cadencia, total]) => ({ cadencia, total }))
      .sort((a, b) => b.total - a.total);
  }

  private async carregarComposicaoCadencia(): Promise<void> {
    const resultado = await this.revisaoAvulsaService.obterComposicaoCadencia();
    // Degrada em silêncio, igual à disponibilidade de catálogo: sem a
    // composição a tela só deixa de mostrar a ressalva.
    if (resultado.success && resultado.composicao) {
      this.composicaoCadencia.set(resultado.composicao);
    }
  }

  /** As métricas que o radar e o rodapé mostram: o recorte escolhido, ou o
   * total. Análises gravadas antes do D-63 não têm `por_cadencia`, e aí só o
   * total existe — o seletor nem aparece. */
  metricasExibidas(): AnaliseHexagonoMetricas | null {
    const analise = this.dados();
    const cadencia = this.cadenciaSelecionada();
    if (!analise) {
      return null;
    }
    const bloco = cadencia ? analise.por_cadencia?.[cadencia] : undefined;
    return bloco ?? analise;
  }

  /** Cadências com recorte próprio, da que tem mais diagnósticos para a que
   * tem menos — mesma ordem da ressalva, para as duas listas não brigarem. */
  cadenciasDisponiveis(): { cadencia: string; partidas: number; diagnosticos: number }[] {
    const blocos = this.dados()?.por_cadencia ?? {};
    return Object.entries(blocos)
      .map(([cadencia, bloco]) => ({
        cadencia,
        partidas: bloco.partidas_distintas ?? 0,
        diagnosticos: bloco.total_diagnosticos ?? 0
      }))
      .sort((a, b) => b.diagnosticos - a.diagnosticos);
  }

  selecionarCadencia(cadencia: string | null): void {
    // Cadência sem bloco não vira seleção: mostraria o total com o chip errado
    // aceso, e o usuário leria o hexágono de tudo achando que é o de blitz.
    if (cadencia && !this.dados()?.por_cadencia?.[cadencia]) {
      return;
    }
    this.cadenciaSelecionada.set(cadencia);
  }

  gargaloExibido(): string | null {
    return this.metricasExibidas()?.gargalo_sistemico_atual ?? null;
  }

  rotuloGargalo(gargalo: string | null): string {
    return (gargalo && this.rotulosCategoria[gargalo]) || 'dados insuficientes';
  }

  /** true quando o gargalo do recorte é OUTRO que o do conjunto. É o achado
   * que este recorte existe para expor — e o que a prescrição do Agente 3,
   * que segue o gargalo do conjunto, ainda não leva em conta. */
  gargaloDivergeDoGeral(): boolean {
    if (!this.cadenciaSelecionada()) {
      return false;
    }
    const geral = this.dados()?.gargalo_sistemico_atual ?? null;
    const recorte = this.gargaloExibido();
    return !!geral && !!recorte && geral !== recorte;
  }

  /** A ressalva vira ação: se a cadência que domina o corpus tem recorte,
   * oferece ver o hexágono só dela em vez de apenas avisar. */
  podeRecortarDominante(): boolean {
    const dominante = this.composicaoCadencia()?.dominante;
    return !!dominante && !!this.dados()?.por_cadencia?.[dominante];
  }

  /** true quando já sabemos que a categoria não tem exercício de catálogo. */
  semCatalogo(categoria: Categoria): boolean {
    const catalogo = this.catalogoPorCategoria();
    return catalogo !== null && (catalogo[categoria] ?? 0) === 0;
  }

  /** Quantas categorias estão sem material, para a nota de rodapé do cartão. */
  categoriasSemCatalogo(): Categoria[] {
    return CATEGORIAS.filter((categoria) => this.semCatalogo(categoria));
  }

  private async carregarDisponibilidadeFoco(): Promise<void> {
    const resultado = await this.treinoService.disponibilidadeFoco();
    // Falha silenciosa de propósito: sem a contagem, os botões continuam
    // clicáveis e o usuário cai no aviso do D-52. Degrada, não quebra.
    if (resultado.success && resultado.porCategoria) {
      this.catalogoPorCategoria.set(resultado.porCategoria);
    }
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
    this.avisoFoco.set(null);

    try {
      const resultado = await this.treinoService.focarCategoria(categoria);

      if (!resultado.success) {
        this.avisoFoco.set({
          texto: resultado.error ?? 'Não foi possível montar o treino focado agora.',
          tipo: 'erro'
        });
        return;
      }

      // Navegar com 0 exercícios adicionados jogaria o usuário numa fila que
      // não mudou, sem explicação nenhuma — pior que não navegar.
      if (!resultado.adicionados) {
        this.avisoFoco.set({
          texto: this.mensagemDeFocoVazio(categoria, resultado.motivo ?? null),
          tipo: 'info'
        });
        return;
      }

      const rotulo = this.rotulosCategoria[categoria] ?? categoria;
      const plural = resultado.adicionados === 1 ? 'exercício' : 'exercícios';
      this.avisoFoco.set({
        texto: `${resultado.adicionados} ${plural} de ${rotulo} na fila de hoje.`,
        tipo: 'info'
      });
      await this.router.navigateByUrl('/treino');
    } finally {
      this.focandoCategoria.set(null);
    }
  }

  /** Os dois zeros possíveis dizem coisas opostas ao usuário: um é "não temos
   * material", o outro é "você já pegou tudo". Tratar como a mesma coisa
   * mentiria em um dos dois casos. */
  private mensagemDeFocoVazio(
    categoria: Categoria,
    motivo: 'sem_catalogo' | 'ja_na_fila' | null
  ): string {
    const rotulo = this.rotulosCategoria[categoria] ?? categoria;
    if (motivo === 'ja_na_fila') {
      return `Você já tem todos os exercícios de ${rotulo} na sua fila — nada novo a adicionar.`;
    }
    return (
      `Ainda não há exercícios de catálogo para ${rotulo}. ` +
      'Essa categoria só é treinada pelos seus próprios lances críticos, no Treino Diário.'
    );
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
        // Rótulos amigáveis, os mesmos dos botões "Focar" logo abaixo — o
        // gráfico escrevia ESTRUTURA_DE_PEOES / GESTAO_DE_TEMPO cru.
        labels: CATEGORIAS.map((categoria) => this.rotulosCategoria[categoria] ?? categoria),
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
