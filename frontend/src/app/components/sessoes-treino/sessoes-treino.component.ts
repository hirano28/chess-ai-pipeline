import { Component, OnInit, inject, signal } from '@angular/core';
import {
  ModuloTreino,
  SessaoTreino,
  SupabaseService
} from '../../services/supabase.service';

@Component({
  selector: 'app-sessoes-treino',
  standalone: true,
  templateUrl: './sessoes-treino.component.html'
})
export class SessoesTreinoComponent implements OnInit {
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly sessoes = signal<SessaoTreino[]>([]);
  readonly sessoesAtualizando = signal<ReadonlySet<string>>(new Set());

  private readonly supabaseService = inject(SupabaseService);
  private readonly formatadorData = new Intl.DateTimeFormat('pt-BR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  });

  ngOnInit(): void {
    void this.carregarSessoes();
  }

  modulosDaSessao(sessao: SessaoTreino): ModuloTreino[] {
    return Array.isArray(sessao.modulos)
      ? sessao.modulos
      : sessao.modulos.modulos ?? [];
  }

  formatarData(data: string): string {
    const valor = new Date(data);
    return Number.isNaN(valor.getTime())
      ? 'data indisponível'
      : this.formatadorData.format(valor);
  }

  async marcarComoConcluida(sessao: SessaoTreino): Promise<void> {
    if (this.sessoesAtualizando().has(sessao.id)) {
      return;
    }

    this.error.set(null);
    this.sessoesAtualizando.update((ids) => new Set(ids).add(sessao.id));

    try {
      const result = await this.supabaseService.marcarSessaoConcluida(sessao.id);
      if (!result.success || !result.dataConcluida) {
        throw new Error(result.error ?? 'O servidor não confirmou a atualização.');
      }

      this.sessoes.update((sessoes) =>
        sessoes.map((item) =>
          item.id === sessao.id
            ? { ...item, data_concluida: result.dataConcluida ?? null }
            : item
        )
      );
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.error.set(`Não foi possível concluir a sessão. ${message}`);
    } finally {
      this.sessoesAtualizando.update((ids) => {
        const atualizados = new Set(ids);
        atualizados.delete(sessao.id);
        return atualizados;
      });
    }
  }

  private async carregarSessoes(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);

    try {
      this.sessoes.set(await this.supabaseService.getSessoesTreino());
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.error.set(`Não foi possível carregar as sessões de treino. ${message}`);
    } finally {
      this.loading.set(false);
    }
  }
}
