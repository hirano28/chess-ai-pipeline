import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../../services/auth.service';

type Modo = 'login' | 'cadastro';

@Component({
  selector: 'app-login',
  standalone: true,
  templateUrl: './login.component.html'
})
export class LoginComponent {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly modo = signal<Modo>('login');
  readonly email = signal('');
  readonly senha = signal('');
  readonly carregando = signal(false);
  readonly erro = signal<string | null>(null);
  readonly confirmacaoPendente = signal(false);

  get formularioValido(): boolean {
    return this.email().trim().length > 0 && this.senha().length >= 6;
  }

  alternarModo(modo: Modo): void {
    this.modo.set(modo);
    this.erro.set(null);
    this.confirmacaoPendente.set(false);
  }

  async entrar(): Promise<void> {
    if (!this.formularioValido || this.carregando()) {
      return;
    }
    this.carregando.set(true);
    this.erro.set(null);

    try {
      const resultado = await this.authService.login(this.email().trim(), this.senha());
      if (!resultado.success) {
        this.erro.set(resultado.error ?? 'Não foi possível entrar.');
        return;
      }
      const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') || '/';
      await this.router.navigateByUrl(returnUrl);
    } finally {
      this.carregando.set(false);
    }
  }

  async cadastrar(): Promise<void> {
    if (!this.formularioValido || this.carregando()) {
      return;
    }
    this.carregando.set(true);
    this.erro.set(null);
    this.confirmacaoPendente.set(false);

    try {
      const resultado = await this.authService.cadastrar(this.email().trim(), this.senha());
      if (!resultado.success) {
        this.erro.set(resultado.error ?? 'Não foi possível criar a conta.');
        return;
      }
      if (resultado.confirmacaoPendente) {
        this.confirmacaoPendente.set(true);
        return;
      }
      const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') || '/';
      await this.router.navigateByUrl(returnUrl);
    } finally {
      this.carregando.set(false);
    }
  }
}
