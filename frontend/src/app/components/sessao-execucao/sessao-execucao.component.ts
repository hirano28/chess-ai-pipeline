import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import {
  BlocoSessao,
  ExecucaoSessao,
  SessaoService
} from '../../services/sessao.service';
import { ROTULOS_CATEGORIA_HEXAGONO } from '../../services/treino.service';

/**
 * Tela de execução de uma sessão de treino focado (D-54).
 *
 * A sessão já existia como texto prescrito pelo Agente 3 desde o D-19, mas
 * não havia o que fazer dentro dela: em 16/09/2026 eram 5 prescritas, 0
 * concluídas e 0 com eficácia medida. Esta tela é o "dentro": blocos em
 * ordem, prática com exercícios reais e conclusão automática no último bloco.
 */
@Component({
  selector: 'app-sessao-execucao',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './sessao-execucao.component.html'
})
export class SessaoExecucaoComponent implements OnInit {
  readonly execucao = signal<ExecucaoSessao | null>(null);
  readonly carregando = signal(true);
  readonly ocupado = signal(false);
  readonly erro = signal<string | null>(null);

  readonly iniciada = computed(() => !!this.execucao()?.data_iniciada);
  readonly blocos = computed<BlocoSessao[]>(() => this.execucao()?.blocos ?? []);
  readonly totalBlocos = computed(() => this.blocos().length);
  readonly blocosConcluidos = computed(
    () => this.blocos().filter((bloco) => bloco.concluido).length
  );
  readonly percentual = computed(() => {
    const total = this.totalBlocos();
    return total === 0 ? 0 : Math.round((this.blocosConcluidos() / total) * 100);
  });

  /** Frase-resumo do plano. Montada aqui, e não no template, porque um `@if`
   * quebrado em linhas no HTML injetava espaço antes da vírgula. */
  readonly resumoDoPlano = computed(() => {
    const minutos = this.execucao()?.duracao_total_min ?? 0;
    const blocos = `São ${this.totalBlocos()} blocos`;
    const leitura = minutos > 0 ? `, cerca de ${minutos} minutos de leitura` : '';
    return `${blocos}${leitura}, mais os exercícios de prática.`;
  });

  /** Primeiro bloco em aberto — o que a tela destaca como "agora". */
  readonly blocoAtual = computed<BlocoSessao | null>(
    () => this.blocos().find((bloco) => !bloco.concluido) ?? null
  );

  private readonly sessaoService = inject(SessaoService);
  private readonly route = inject(ActivatedRoute);
  private readonly formatadorData = new Intl.DateTimeFormat('pt-BR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  });

  private sessaoId = '';

  ngOnInit(): void {
    this.sessaoId = this.route.snapshot.paramMap.get('id') ?? '';
    void this.carregar();
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

  rotuloCategoria(categoria: string | null): string {
    return (categoria && ROTULOS_CATEGORIA_HEXAGONO[categoria]) || 'categoria não identificada';
  }

  async carregar(): Promise<void> {
    if (!this.sessaoId) {
      this.erro.set('Sessão não informada.');
      this.carregando.set(false);
      return;
    }
    this.carregando.set(true);
    this.erro.set(null);
    this.aplicar(await this.sessaoService.obterExecucao(this.sessaoId));
    this.carregando.set(false);
  }

  async iniciar(): Promise<void> {
    if (this.ocupado()) {
      return;
    }
    this.ocupado.set(true);
    this.erro.set(null);
    this.aplicar(await this.sessaoService.iniciar(this.sessaoId));
    this.ocupado.set(false);
  }

  async concluirBloco(bloco: BlocoSessao): Promise<void> {
    if (this.ocupado() || bloco.tipo !== 'estudo' || bloco.concluido) {
      return;
    }
    this.ocupado.set(true);
    this.erro.set(null);
    this.aplicar(await this.sessaoService.concluirBloco(this.sessaoId, bloco.indice));
    this.ocupado.set(false);
  }

  private aplicar(resultado: {
    success: boolean;
    execucao?: ExecucaoSessao;
    error?: string;
  }): void {
    if (!resultado.success || !resultado.execucao) {
      this.erro.set(resultado.error ?? 'Não foi possível carregar a sessão.');
      return;
    }
    this.execucao.set(resultado.execucao);
  }
}
