import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../../services/auth.service';
import { SupabaseService } from '../../services/supabase.service';
import {
  LichessOauthService,
  LichessOauthStatus
} from '../../services/lichess-oauth.service';

/**
 * Cadastro da(s) conta(s) de Lichess/Chess.com e conexão OAuth (D-28, D-35).
 *
 * É a partir daqui que a coleta em backend/ingestao/ sabe de quem baixar
 * partidas e a quem atribuir o `user_id` gravado - e onde o usuário autoriza
 * o acesso OAuth com escopo puzzle:read para sincronizar puzzles automaticamente.
 */
@Component({
  selector: 'app-perfil-usuario',
  standalone: true,
  templateUrl: './perfil-usuario.component.html'
})
export class PerfilUsuarioComponent implements OnInit {
  readonly lichessUsername = signal('');
  readonly chesscomUsername = signal('');

  readonly carregando = signal(true);
  readonly salvando = signal(false);
  readonly salvo = signal(false);
  readonly erro = signal<string | null>(null);

  // Estados do OAuth Lichess (D-35)
  readonly oauthStatus = signal<LichessOauthStatus | null>(null);
  readonly oauthCarregando = signal(true);
  readonly oauthIniciando = signal(false);
  readonly oauthDesconectando = signal(false);
  readonly confirmandoDesconexao = signal(false);
  readonly oauthMensagemSucesso = signal<string | null>(null);
  readonly oauthMensagemErro = signal<string | null>(null);

  private readonly authService = inject(AuthService);
  private readonly supabaseService = inject(SupabaseService);
  private readonly lichessOauthService = inject(LichessOauthService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  get formularioValido(): boolean {
    return this.lichessUsername().trim().length > 0 || this.chesscomUsername().trim().length > 0;
  }

  async ngOnInit(): Promise<void> {
    this.processarRetornoOauth();
    await Promise.all([this.carregarPerfil(), this.carregarOauthStatus()]);
  }

  private processarRetornoOauth(): void {
    const params = this.route.snapshot.queryParams;
    if (params['conectado'] === 'lichess') {
      this.oauthMensagemSucesso.set('Conta do Lichess vinculada com sucesso via OAuth!');
      this.limparQueryParams();
    } else if (params['erro']) {
      const codigoErro = params['erro'];
      const mapaErros: Record<string, string> = {
        lichess_negado: 'Você cancelou ou recusou a conexão no Lichess.',
        lichess_state_invalido: 'Tentativa de conexão expirada ou inválida. Tente novamente.',
        lichess_state_expirado: 'Tempo limite da tentativa esgotado. Tente novamente.',
        lichess_troca_falhou: 'Não foi possível confirmar a autorização com o Lichess.',
        lichess_gravacao_falhou: 'Erro ao registrar autorização no sistema.',
        lichess_indisponivel: 'Serviço de autenticação temporariamente indisponível.'
      };
      this.oauthMensagemErro.set(mapaErros[codigoErro] ?? 'Falha ao conectar com o Lichess.');
      this.limparQueryParams();
    }
  }

  private limparQueryParams(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {},
      replaceUrl: true
    });
  }

  async carregarPerfil(): Promise<void> {
    this.carregando.set(true);
    try {
      const perfil = await this.supabaseService.getPerfilUsuario();
      if (perfil) {
        this.lichessUsername.set(perfil.lichessUsername ?? '');
        this.chesscomUsername.set(perfil.chesscomUsername ?? '');
      }
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.erro.set(`Não foi possível carregar seu perfil. ${message}`);
    } finally {
      this.carregando.set(false);
    }
  }

  async carregarOauthStatus(): Promise<void> {
    this.oauthCarregando.set(true);
    try {
      const status = await this.lichessOauthService.obterStatus();
      this.oauthStatus.set(status);
    } catch {
      this.oauthStatus.set({ conectado: false });
    } finally {
      this.oauthCarregando.set(false);
    }
  }

  async conectarLichess(): Promise<void> {
    if (this.oauthIniciando()) {
      return;
    }

    this.oauthIniciando.set(true);
    this.oauthMensagemErro.set(null);
    this.oauthMensagemSucesso.set(null);

    try {
      const url = await this.lichessOauthService.iniciarConexao();
      window.location.href = url;
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro ao iniciar conexão com o Lichess.';
      this.oauthMensagemErro.set(message);
      this.oauthIniciando.set(false);
    }
  }

  /** Pede confirmação antes de revogar: um clique sem volta, num botão
   * vermelho encostado no "Reconectar", derrubava a sincronização de puzzles
   * sem perguntar nada. */
  pedirConfirmacaoDesconectar(): void {
    this.oauthMensagemErro.set(null);
    this.oauthMensagemSucesso.set(null);
    this.confirmandoDesconexao.set(true);
  }

  cancelarDesconexao(): void {
    this.confirmandoDesconexao.set(false);
  }

  async desconectarLichess(): Promise<void> {
    if (this.oauthDesconectando()) {
      return;
    }

    this.confirmandoDesconexao.set(false);
    this.oauthDesconectando.set(true);
    this.oauthMensagemErro.set(null);
    this.oauthMensagemSucesso.set(null);

    try {
      const ok = await this.lichessOauthService.desconectar();
      if (ok) {
        this.oauthStatus.set({ conectado: false });
        this.oauthMensagemSucesso.set('Conta do Lichess desvinculada com sucesso.');
      } else {
        this.oauthMensagemErro.set('Não foi possível desvincular sua conta.');
      }
    } catch {
      this.oauthMensagemErro.set('Erro ao desvincular conta do Lichess.');
    } finally {
      this.oauthDesconectando.set(false);
    }
  }

  async salvar(): Promise<void> {
    if (!this.formularioValido || this.salvando()) {
      return;
    }

    const userId = this.authService.usuario()?.id;
    if (!userId) {
      this.erro.set('Sua sessão expirou. Entre de novo para continuar.');
      return;
    }

    this.salvando.set(true);
    this.erro.set(null);
    this.salvo.set(false);

    try {
      const resultado = await this.supabaseService.salvarPerfilUsuario(
        userId,
        this.lichessUsername(),
        this.chesscomUsername()
      );
      if (!resultado.success) {
        throw new Error(resultado.error ?? 'O servidor não confirmou o salvamento.');
      }
      this.salvo.set(true);
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.erro.set(`Não foi possível salvar seu perfil. ${message}`);
    } finally {
      this.salvando.set(false);
    }
  }
}
