import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  InsightsRepertorio,
  MetricasAberturaCorItem,
  RepertorioService
} from '../../services/repertorio.service';

export type FiltroCor = 'TODAS' | 'BRANCAS' | 'PRETAS';

@Component({
  selector: 'app-repertorio-insights',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './repertorio-insights.component.html'
})
export class RepertorioInsightsComponent implements OnInit {
  private readonly repertorioService = inject(RepertorioService);

  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly insights = signal<InsightsRepertorio | null>(null);
  readonly filtroCor = signal<FiltroCor>('TODAS');

  readonly aberturasFiltradas = computed<MetricasAberturaCorItem[]>(() => {
    const dados = this.insights();
    if (!dados?.por_abertura_e_cor) return [];
    const filtro = this.filtroCor();
    if (filtro === 'TODAS') return dados.por_abertura_e_cor;
    return dados.por_abertura_e_cor.filter(
      (item) => item.cor_jogada.toUpperCase() === filtro
    );
  });

  readonly taxaBrancas = computed(() => {
    return this.insights()?.taxa_vitoria_por_cor?.BRANCAS;
  });

  readonly taxaPretas = computed(() => {
    return this.insights()?.taxa_vitoria_por_cor?.PRETAS;
  });

  ngOnInit(): void {
    void this.carregarInsights();
  }

  async carregarInsights(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const res = await this.repertorioService.getInsightsRepertorio();
      if (res.success && res.dados) {
        this.insights.set(res.dados);
      } else {
        this.error.set(res.error || 'Falha ao carregar insights de repertório.');
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Erro inesperado';
      this.error.set(`Não foi possível carregar o repertório: ${msg}`);
    } finally {
      this.loading.set(false);
    }
  }

  selecionarFiltro(filtro: FiltroCor): void {
    this.filtroCor.set(filtro);
  }

  obterMomentoCritico(abertura: string): string | null {
    const picos = this.insights()?.lance_pico_por_abertura;
    if (!picos) return null;
    const match = picos.find(
      (item) => item.abertura_normalizada.toLowerCase() === abertura.toLowerCase()
    );
    if (!match) return null;
    return `Lance médio: ${match.lance_medio}`;
  }

  obterTopCategorias(
    abertura: string
  ): { categoria: string; contagem: number }[] {
    const categoriasMap = this.insights()?.categorias_por_abertura;
    if (!categoriasMap) return [];
    const cat = categoriasMap[abertura];
    if (!cat) return [];
    return Object.entries(cat)
      .map(([categoria, contagem]) => ({ categoria, contagem }))
      .filter((item) => item.contagem > 0)
      .sort((a, b) => b.contagem - a.contagem)
      .slice(0, 3);
  }

  corBarraProgresso(taxa: number): string {
    if (taxa >= 50) return 'bg-sucesso';
    if (taxa >= 40) return 'bg-latao-500';
    return 'bg-perigo';
  }

  /** Variante de `.selo` (ver src/styles.css). */
  corBadgeTaxa(taxa: number): string {
    if (taxa >= 50) return 'selo-sucesso';
    if (taxa >= 40) return 'selo-latao';
    return 'selo-perigo';
  }
}

