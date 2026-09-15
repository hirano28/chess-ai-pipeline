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
    if (taxa >= 70) return 'bg-sucesso';
    if (taxa >= 55) return 'bg-latao-500';
    return 'bg-perigo';
  }

  /** Variante de `.selo` (ver src/styles.css). */
  corBadgeTaxa(taxa: number): string {
    if (taxa >= 70) return 'selo-sucesso';
    if (taxa >= 55) return 'selo-latao';
    return 'selo-perigo';
  }

  /** Só a cor do texto: usada no número grande da métrica, onde selo não cabe. */
  corTextoTaxa(taxa: number): string {
    if (taxa >= 70) return 'text-sucesso';
    if (taxa >= 55) return 'text-latao-500';
    return 'text-perigo';
  }

  /** Variante de `.selo` (ver src/styles.css), uma cor por família tática. */
  badgeCategoria(categoria: string): string {
    switch (categoria) {
      case 'defesa':
        return 'selo-perigo';
      case 'ataque':
        return 'selo-latao';
      case 'tatica':
        return 'selo-info';
      case 'final':
        return 'selo-roxo';
      case 'mate':
        return 'selo-sucesso';
      default:
        return 'selo-neutro';
    }
  }
}

