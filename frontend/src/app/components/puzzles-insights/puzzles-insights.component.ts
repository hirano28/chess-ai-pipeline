import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  InsightsPuzzles,
  PuzzlesService,
  TemaPuzzleStat
} from '../../services/puzzles.service';

@Component({
  selector: 'app-puzzles-insights',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './puzzles-insights.component.html'
})
export class PuzzlesInsightsComponent implements OnInit {
  private readonly puzzlesService = inject(PuzzlesService);

  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly insights = signal<InsightsPuzzles | null>(null);

  readonly resumo = computed(() => this.insights()?.resumo);
  readonly diagnosticoGap = computed(() => this.insights()?.diagnostico_gap);
  readonly temasVulneraveis = computed<TemaPuzzleStat[]>(
    () => this.insights()?.temas_vulneraveis ?? []
  );
  readonly temasDominados = computed<TemaPuzzleStat[]>(
    () => this.insights()?.temas_dominados ?? []
  );

  ngOnInit(): void {
    void this.carregarInsights();
  }

  async carregarInsights(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const res = await this.puzzlesService.getInsightsPuzzles();
      if (res.success && res.dados) {
        this.insights.set(res.dados);
      } else {
        this.error.set(res.error || 'Falha ao carregar insights de puzzles.');
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Erro inesperado';
      this.error.set(`Não foi possível carregar os insights de puzzles: ${msg}`);
    } finally {
      this.loading.set(false);
    }
  }

  corBarraProgresso(taxa: number): string {
    if (taxa >= 70) return 'bg-emerald-500';
    if (taxa >= 55) return 'bg-amber-500';
    return 'bg-rose-500';
  }

  corBadgeTaxa(taxa: number): string {
    if (taxa >= 70) return 'text-emerald-400 bg-emerald-950/60 border-emerald-800';
    if (taxa >= 55) return 'text-amber-400 bg-amber-950/60 border-amber-800';
    return 'text-rose-400 bg-rose-950/60 border-rose-800';
  }

  badgeCategoria(categoria: string): string {
    switch (categoria) {
      case 'defesa':
        return 'border-rose-800 bg-rose-950/40 text-rose-300';
      case 'ataque':
        return 'border-amber-800 bg-amber-950/40 text-amber-300';
      case 'tatica':
        return 'border-sky-800 bg-sky-950/40 text-sky-300';
      case 'final':
        return 'border-purple-800 bg-purple-950/40 text-purple-300';
      case 'mate':
        return 'border-emerald-800 bg-emerald-950/40 text-emerald-300';
      default:
        return 'border-zinc-700 bg-zinc-800 text-zinc-300';
    }
  }
}

