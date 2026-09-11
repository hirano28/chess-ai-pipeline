import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  ExplicacaoPosicaoRecenteItem,
  ResultadoExplicadorPosicao,
  RevisaoAvulsaService
} from '../../services/revisao-avulsa.service';
import { AuthLocalService } from '../../services/auth-local.service';
import {
  HistoricoAnaliseComponent,
  HistoricoAnaliseItem
} from '../historico-analise/historico-analise.component';

/** Chave de localStorage que sobrevive a um F5, mesmo padrão do Analisador de Partida. */
export const STORAGE_KEY_EXPLICADOR_ATIVO = 'chess_explicador_ativo';

/** Tamanho máximo do veredito exibido como título de cada item do histórico. */
const TITULO_HISTORICO_MAX_CHARS = 90;

@Component({
  selector: 'app-explicador-posicao',
  standalone: true,
  imports: [CommonModule, HistoricoAnaliseComponent],
  templateUrl: './explicador-posicao.component.html'
})
export class ExplicadorPosicaoComponent implements OnInit {
  readonly posicao = signal('');
  readonly lado = signal<'TODOS' | 'BRANCAS' | 'PRETAS'>('TODOS');

  readonly carregando = signal(false);
  readonly erro = signal<string | null>(null);
  readonly resultado = signal<ResultadoExplicadorPosicao | null>(null);

  // Histórico de explicações já persistidas (explicacoes_posicao, ver P-10).
  readonly historico = signal<ExplicacaoPosicaoRecenteItem[]>([]);
  readonly carregandoHistorico = signal(false);

  /** Mapeia ExplicacaoPosicaoRecenteItem -> HistoricoAnaliseItem para o componente genérico. */
  readonly itensHistoricoComponent = computed<HistoricoAnaliseItem[]>(() =>
    this.historico().map((item) => {
      const veredito = item.resultado.explicacao?.veredito ?? item.fen;
      const titulo =
        veredito.length > TITULO_HISTORICO_MAX_CHARS
          ? `${veredito.slice(0, TITULO_HISTORICO_MAX_CHARS)}…`
          : veredito;
      const ladoAnalisado = item.lado_analisado ?? item.resultado.lado_analisado;
      const detalhes: string[] = [];
      if (ladoAnalisado) {
        detalhes.push(`Analisado: ${ladoAnalisado === 'BRANCAS' ? 'Brancas ♔' : 'Pretas ♚'}`);
      }
      detalhes.push(`Win%: ${item.resultado.avaliacao.win_percent}%`);
      return {
        id: item.id,
        titulo,
        detalhes,
        dataIso: item.created_at
        // Sem 'status': cada item já é um resultado salvo e pronto, não há
        // pipeline assíncrono aqui (diferente do Analisador de Partida).
      };
    })
  );

  private readonly revisaoAvulsaService = inject(RevisaoAvulsaService);
  private readonly authLocalService = inject(AuthLocalService);

  readonly chaveConfigurada = signal(this.authLocalService.isConfigured());
  readonly chaveInput = signal('');
  readonly erroChave = signal<string | null>(null);

  get chaveFormularioValido(): boolean {
    return this.chaveInput().trim().length > 0;
  }

  get formularioValido(): boolean {
    return this.posicao().trim().length > 0;
  }

  async ngOnInit(): Promise<void> {
    if (this.chaveConfigurada()) {
      await this.carregarHistorico();
      this.restaurarAtivoSalvo();
    }
  }

  async carregarHistorico(): Promise<void> {
    this.carregandoHistorico.set(true);
    try {
      const res = await this.revisaoAvulsaService.listarExplicacoesRecentes(20);
      if (res.chaveInvalida) {
        this.tratarChaveInvalida();
        return;
      }
      if (res.success && res.itens) {
        this.historico.set(res.itens);
      }
    } finally {
      this.carregandoHistorico.set(false);
    }
  }

  /** O item embute o resultado inteiro - restaurar é local, sem chamada de rede. */
  selecionarHistorico(id: string): void {
    const item = this.historico().find((i) => i.id === id);
    if (!item) {
      return;
    }
    this.resultado.set(item.resultado);
    this.erro.set(null);
    this.salvarAtivo(id);
  }

  private restaurarAtivoSalvo(): void {
    try {
      const salvo = localStorage.getItem(STORAGE_KEY_EXPLICADOR_ATIVO);
      if (salvo) {
        this.selecionarHistorico(salvo);
      }
    } catch {
      // Ignora erro de acesso a localStorage em ambientes restritos
    }
  }

  private salvarAtivo(id: string | null): void {
    try {
      if (id) {
        localStorage.setItem(STORAGE_KEY_EXPLICADOR_ATIVO, id);
      } else {
        localStorage.removeItem(STORAGE_KEY_EXPLICADOR_ATIVO);
      }
    } catch {
      // Ignora erro de acesso a localStorage
    }
  }

  salvarChave(): void {
    if (!this.chaveFormularioValido) {
      return;
    }
    this.authLocalService.setKey(this.chaveInput().trim());
    this.chaveInput.set('');
    this.erroChave.set(null);
    this.chaveConfigurada.set(true);
    void this.carregarHistorico();
    this.restaurarAtivoSalvo();
  }

  private tratarChaveInvalida(): void {
    this.chaveConfigurada.set(false);
    this.erroChave.set('Chave inválida, tente novamente.');
  }

  carregarExemplo(): void {
    // Exemplo tático clássico (Ataque grego / sacrifício em h7)
    this.posicao.set('r1bq1rk1/ppp2ppp/2np4/2b1p1N1/2B1P3/3P4/PPP2PPP/R1BQK2R w KQ - 0 8');
    this.lado.set('BRANCAS');
    this.erro.set(null);
    this.resultado.set(null);
    this.salvarAtivo(null);
  }

  async analisar(): Promise<void> {
    if (!this.formularioValido || this.carregando()) {
      return;
    }

    this.carregando.set(true);
    this.erro.set(null);
    this.resultado.set(null);

    try {
      const ladoParam = this.lado() === 'TODOS' ? null : this.lado();
      const resposta = await this.revisaoAvulsaService.explicarPosicao(
        this.posicao().trim(),
        ladoParam
      );
      if (resposta.chaveInvalida) {
        this.tratarChaveInvalida();
        return;
      }
      if (!resposta.success || !resposta.resultado) {
        throw new Error(resposta.error ?? 'O servidor não retornou um resultado.');
      }
      this.resultado.set(resposta.resultado);
      // O backend já persistiu ao gerar (ver P-10); marcamos como "ativo" só
      // quando ele confirma um id - se a persistência falhou lá, não há o
      // que restaurar num F5, então não sobrescrevemos o que já era ativo.
      if (resposta.resultado.id) {
        this.salvarAtivo(resposta.resultado.id);
      }
      void this.carregarHistorico();
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.erro.set(message);
    } finally {
      this.carregando.set(false);
    }
  }

  novaAnalise(): void {
    this.posicao.set('');
    this.lado.set('TODOS');
    this.resultado.set(null);
    this.erro.set(null);
    this.salvarAtivo(null);
  }

  corBadgeVencedor(lado: string): string {
    switch (lado) {
      case 'BRANCAS':
        return 'border-[#3f6b4c] bg-[#173322] text-[#8fd6a6]';
      case 'PRETAS':
        return 'border-[#7a3a34] bg-[#331a17] text-[#e79a90]';
      default:
        return 'border-[#7a6a2a] bg-[#332c14] text-[#e8cf7a]';
    }
  }
}

