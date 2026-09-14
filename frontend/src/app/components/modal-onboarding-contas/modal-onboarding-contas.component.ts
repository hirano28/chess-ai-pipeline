import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../../services/auth.service';
import { SupabaseService } from '../../services/supabase.service';
import { LichessOauthService } from '../../services/lichess-oauth.service';

export const CHAVE_ONBOARDING_DISPENSADO = 'onboarding_contas_dispensado';

@Component({
  selector: 'app-modal-onboarding-contas',
  standalone: true,
  templateUrl: './modal-onboarding-contas.component.html'
})
export class ModalOnboardingContasComponent implements OnInit {
  readonly visivel = signal(false);
  readonly lichessUsername = signal('');
  readonly chesscomUsername = signal('');
  readonly salvando = signal(false);
  readonly iniciandoOauth = signal(false);
  readonly erro = signal<string | null>(null);
  readonly sucesso = signal(false);

  private readonly authService = inject(AuthService);
  private readonly supabaseService = inject(SupabaseService);
  private readonly lichessOauthService = inject(LichessOauthService);
  private readonly router = inject(Router);

  get formularioValido(): boolean {
    return this.lichessUsername().trim().length > 0 || this.chesscomUsername().trim().length > 0;
  }

  async ngOnInit(): Promise<void> {
    await this.verificarNecessidadeOnboarding();
  }

  async verificarNecessidadeOnboarding(): Promise<void> {
    const usuario = this.authService.usuario();
    if (!usuario) {
      this.visivel.set(false);
      return;
    }

    // Não exibe se o usuário já dispensou nesta sessão
    if (typeof sessionStorage !== 'undefined' && sessionStorage.getItem(CHAVE_ONBOARDING_DISPENSADO) === 'true') {
      return;
    }

    // Não sobrepõe a tela de login ou a tela de perfil
    const urlAtual = this.router.url;
    if (urlAtual.includes('/login') || urlAtual.includes('/perfil')) {
      return;
    }

    try {
      const perfil = await this.supabaseService.getPerfilUsuario();
      // Se não tem perfil ou ambas as contas estão vazias, abre o onboarding
      const semContas = !perfil || (!perfil.lichessUsername && !perfil.chesscomUsername);
      if (semContas) {
        this.visivel.set(true);
      }
    } catch {
      // Em caso de erro de rede, não bloqueia o usuário com modal forçado
      this.visivel.set(false);
    }
  }

  fechar(): void {
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.setItem(CHAVE_ONBOARDING_DISPENSADO, 'true');
    }
    this.visivel.set(false);
  }

  async salvar(): Promise<void> {
    if (!this.formularioValido || this.salvando()) {
      return;
    }

    const userId = this.authService.usuario()?.id;
    if (!userId) {
      this.erro.set('Sessão expirada. Entre novamente para continuar.');
      return;
    }

    this.salvando.set(true);
    this.erro.set(null);

    try {
      const resultado = await this.supabaseService.salvarPerfilUsuario(
        userId,
        this.lichessUsername(),
        this.chesscomUsername()
      );

      if (!resultado.success) {
        throw new Error(resultado.error ?? 'Falha ao salvar contas.');
      }

      this.sucesso.set(true);
      setTimeout(() => {
        this.fechar();
      }, 1000);
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido.';
      this.erro.set(`Não foi possível salvar: ${message}`);
    } finally {
      this.salvando.set(false);
    }
  }

  async conectarLichessOauth(): Promise<void> {
    if (this.iniciandoOauth()) {
      return;
    }

    this.iniciandoOauth.set(true);
    this.erro.set(null);

    try {
      const url = await this.lichessOauthService.iniciarConexao();
      window.location.href = url;
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro ao iniciar conexão.';
      this.erro.set(message);
      this.iniciandoOauth.set(false);
    }
  }
}

