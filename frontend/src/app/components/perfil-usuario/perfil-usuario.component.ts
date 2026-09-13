import { Component, OnInit, inject, signal } from '@angular/core';
import { AuthService } from '../../services/auth.service';
import { SupabaseService } from '../../services/supabase.service';

/**
 * Cadastro da(s) conta(s) de Lichess/Chess.com de quem está logado (D-28).
 *
 * É a partir daqui que a coleta em backend/ingestao/ sabe de quem baixar
 * partidas e a quem atribuir o `user_id` gravado - sem um perfil aqui, a
 * pessoa pode logar e ver as telas, mas nunca vai ter partida nenhuma
 * analisada nem hexágono montado.
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

  private readonly authService = inject(AuthService);
  private readonly supabaseService = inject(SupabaseService);

  get formularioValido(): boolean {
    return this.lichessUsername().trim().length > 0 || this.chesscomUsername().trim().length > 0;
  }

  async ngOnInit(): Promise<void> {
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
