import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  PerguntaPendente,
  SupabaseService
} from '../../services/supabase.service';
import { TabuleiroPreviewComponent } from '../tabuleiro-preview/tabuleiro-preview.component';

@Component({
  selector: 'app-perguntas-pendentes',
  standalone: true,
  imports: [RouterLink, TabuleiroPreviewComponent],
  templateUrl: './perguntas-pendentes.component.html'
})
export class PerguntasPendentesComponent implements OnInit {
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly perguntas = signal<PerguntaPendente[]>([]);
  readonly enviando = signal<ReadonlySet<string>>(new Set());
  /** Quais perguntas estão com o campo de resposta aberto. Só a primeira abre
   * sozinha: seis textareas empilhadas no topo do dashboard empurravam o radar
   * para baixo e liam como uma lista de tarefas. */
  readonly respondendoIds = signal<ReadonlySet<string>>(new Set());
  /** D-64: por padrão só a primeira pergunta aparece. Seis cartões com
   * miniatura de tabuleiro ocupavam quase metade da altura da página ACIMA do
   * radar — o diagnóstico, que é o produto, começava abaixo de uma lista de
   * tarefas que nunca foi respondida (0 de 6 em toda a vida do recurso).
   * Uma pergunta por vez lê como um convite; seis leem como cobrança. */
  readonly mostrarTodas = signal(false);

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

  respondendo(perguntaId: string): boolean {
    return this.respondendoIds().has(perguntaId);
  }

  /** As perguntas de fato renderizadas: a primeira, ou todas se o usuário
   * pediu para ver o resto. */
  perguntasVisiveis(): PerguntaPendente[] {
    return this.mostrarTodas() ? this.perguntas() : this.perguntas().slice(0, 1);
  }

  quantidadeOculta(): number {
    return Math.max(0, this.perguntas().length - this.perguntasVisiveis().length);
  }

  alternarMostrarTodas(): void {
    this.mostrarTodas.update((atual) => !atual);
  }

  abrirResposta(perguntaId: string): void {
    this.respondendoIds.update((ids) => new Set(ids).add(perguntaId));
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
      const perguntas = await this.supabaseService.getPerguntasPendentes();
      this.perguntas.set(perguntas);
      if (perguntas.length > 0) {
        this.respondendoIds.set(new Set([perguntas[0].id]));
      }
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.error.set(`Não foi possível carregar as perguntas pendentes. ${message}`);
    } finally {
      this.loading.set(false);
    }
  }
}
