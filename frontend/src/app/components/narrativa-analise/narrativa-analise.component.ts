import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  AnaliseHexagonoCompleta,
  CitacaoGargalo,
  SupabaseService
} from '../../services/supabase.service';
import { SegmentoTexto, segmentosDeNegrito } from '../../shared/texto';

@Component({
  selector: 'app-narrativa-analise',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './narrativa-analise.component.html'
})
export class NarrativaAnaliseComponent implements OnInit {
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly analise = signal<AnaliseHexagonoCompleta | null>(null);

  /**
   * D-81: capítulo real que trata do gargalo. Só aparece quando a análise foi
   * gerada depois do D-81 E a categoria tem conceito indexado — as duas
   * ausências são normais, não erro.
   */
  readonly citacao = computed<CitacaoGargalo | null>(() => {
    const citacao = this.analise()?.citacao_gargalo;
    return citacao?.livro ? citacao : null;
  });

  /** Pergunta que leva o capítulo indicado para a Biblioteca já pesquisado. */
  readonly perguntaSobreCitacao = computed(() => {
    const citacao = this.citacao();
    if (!citacao) {
      return '';
    }
    const assunto = citacao.conceito?.replace(/_/g, ' ') ?? citacao.capitulo ?? '';
    return `Explique ${assunto} e por que isso aparece tanto nos meus erros.`;
  });

  private readonly supabaseService = inject(SupabaseService);
  private readonly formatadorData = new Intl.DateTimeFormat('pt-BR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  });

  ngOnInit(): void {
    void this.carregarAnalise();
  }

  /** Wrapper fino sobre o helper compartilhado, só para o template chamá-lo.
   * O Gemini usa `**negrito**` na narrativa e os asteriscos apareciam crus. */
  segmentos(paragrafo: string): SegmentoTexto[] {
    return segmentosDeNegrito(paragrafo);
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
