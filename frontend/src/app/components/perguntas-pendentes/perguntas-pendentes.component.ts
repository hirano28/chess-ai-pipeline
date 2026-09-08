import { Component, OnInit, inject, signal } from '@angular/core';
import {
  PerguntaPendente,
  SupabaseService
} from '../../services/supabase.service';

@Component({
  selector: 'app-perguntas-pendentes',
  standalone: true,
  templateUrl: './perguntas-pendentes.component.html'
})
export class PerguntasPendentesComponent implements OnInit {
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly perguntas = signal<PerguntaPendente[]>([]);
  readonly enviando = signal<ReadonlySet<string>>(new Set());

  private readonly supabaseService = inject(SupabaseService);
  private readonly formatadorData = new Intl.DateTimeFormat('pt-BR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  });

  ngOnInit(): void {
    void this.carregarPerguntas();
  }

  formatarData(data: string | null): string {
    if (!data) {
      return 'data indisponível';
    }
    const valor = new Date(data);
    return Number.isNaN(valor.getTime())
      ? 'data indisponível'
      : this.formatadorData.format(valor);
  }

  async responder(pergunta: PerguntaPendente, texto: string): Promise<void> {
    const textoLimpo = texto.trim();
    if (!textoLimpo || this.enviando().has(pergunta.id)) {
      return;
    }

    this.error.set(null);
    this.enviando.update((ids) => new Set(ids).add(pergunta.id));

    try {
      const result = await this.supabaseService.responderPergunta(pergunta.id, textoLimpo);
      if (!result.success) {
        throw new Error(result.error ?? 'O servidor não confirmou a resposta.');
      }

      this.perguntas.update((lista) => lista.filter((item) => item.id !== pergunta.id));
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.error.set(`Não foi possível enviar a resposta. ${message}`);
    } finally {
      this.enviando.update((ids) => {
        const atualizados = new Set(ids);
        atualizados.delete(pergunta.id);
        return atualizados;
      });
    }
  }

  private async carregarPerguntas(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);

    try {
      this.perguntas.set(await this.supabaseService.getPerguntasPendentes());
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.error.set(`Não foi possível carregar as perguntas pendentes. ${message}`);
    } finally {
      this.loading.set(false);
    }
  }
}
