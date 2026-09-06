import { Component, OnInit, inject, signal } from '@angular/core';
import {
  AnaliseHexagonoCompleta,
  SupabaseService
} from '../../services/supabase.service';

@Component({
  selector: 'app-narrativa-analise',
  standalone: true,
  templateUrl: './narrativa-analise.component.html'
})
export class NarrativaAnaliseComponent implements OnInit {
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly analise = signal<AnaliseHexagonoCompleta | null>(null);

  private readonly supabaseService = inject(SupabaseService);
  private readonly formatadorData = new Intl.DateTimeFormat('pt-BR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  });

  ngOnInit(): void {
    void this.carregarAnalise();
  }

  paragrafosDaNarrativa(narrativa: string): string[] {
    return narrativa
      .split(/\n+/)
      .map((paragrafo) => paragrafo.trim())
      .filter((paragrafo) => paragrafo.length > 0);
  }

  formatarData(data: string): string {
    const valor = new Date(data);
    return Number.isNaN(valor.getTime())
      ? 'data indisponível'
      : this.formatadorData.format(valor);
  }

  private async carregarAnalise(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);

    try {
      this.analise.set(await this.supabaseService.getUltimaAnaliseCompleta());
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.error.set(`Não foi possível carregar a análise. ${message}`);
    } finally {
      this.loading.set(false);
    }
  }
}
