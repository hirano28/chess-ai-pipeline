import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

/**
 * Bloqueia as telas do dashboard sem sessão ativa (Fase B.1 — ver D-15).
 *
 * Espera `aguardarSessaoPronta()` antes de decidir: sem isso, todo F5 com uma
 * sessão salva no localStorage passaria por um instante em que `usuario()`
 * ainda é null (getSession ainda não respondeu) e redirecionaria pro /login
 * por engano.
 */
export const authGuard: CanActivateFn = async (_route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  await authService.aguardarSessaoPronta();

  if (authService.autenticado()) {
    return true;
  }

  return router.parseUrl(`/login?returnUrl=${encodeURIComponent(state.url)}`);
};
