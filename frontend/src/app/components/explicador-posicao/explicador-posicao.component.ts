import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  ResultadoExplicadorPosicao,
  RevisaoAvulsaService
} from '../../services/revisao-avulsa.service';
import { AuthLocalService } from '../../services/auth-local.service';

@Component({
  selector: 'app-explicador-posicao',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './explicador-posicao.component.html'
})
export class ExplicadorPosicaoComponent {
  readonly posicao = signal('');
  readonly lado = signal<'TODOS' | 'BRANCAS' | 'PRETAS'>('TODOS');

  readonly carregando = signal(false);
  readonly erro = signal<string | null>(null);
  readonly resultado = signal<ResultadoExplicadorPosicao | null>(null);

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

  salvarChave(): void {
    if (!this.chaveFormularioValido) {
      return;
    }
    this.authLocalService.setKey(this.chaveInput().trim());
    this.chaveInput.set('');
    this.erroChave.set(null);
    this.chaveConfigurada.set(true);
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

