import { Component, effect, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from './services/auth.service';
import { ConsultaAoVivoService } from './services/consulta-ao-vivo.service';
import { ModalOnboardingContasComponent } from './components/modal-onboarding-contas/modal-onboarding-contas.component';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ModalOnboardingContasComponent],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  protected readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly consultaAoVivoService = inject(ConsultaAoVivoService);

  /** D-67: o link da consulta ao vivo só aparece para quem o servidor libera. */
  protected readonly consultaAoVivoHabilitada = signal(false);

  constructor() {
    effect(() => {
      const usuarioId = this.authService.usuario()?.id ?? null;
      if (!usuarioId) {
        this.consultaAoVivoHabilitada.set(false);
        return;
      }
      void this.consultaAoVivoService
        .acesso()
        .then((acesso) => this.consultaAoVivoHabilitada.set(acesso.habilitado));
    });
  }

  async sair(): Promise<void> {
    await this.authService.logout();
    await this.router.navigateByUrl('/login');
  }
}
