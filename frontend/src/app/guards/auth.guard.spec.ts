import { TestBed } from '@angular/core/testing';
import { Router, UrlTree, provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { authGuard } from './auth.guard';
import { AuthService } from '../services/auth.service';
import { routes } from '../app.routes';

// O guard é sempre uma função async (devolve Promise); o tipo de retorno do
// CanActivateFn é mais amplo (aceita síncrono/Observable também), então o
// cast só afirma o que a implementação real garante.
function executarGuard(url: string): Promise<boolean | UrlTree> {
  return TestBed.runInInjectionContext(() =>
    authGuard({} as any, { url } as any)
  ) as Promise<boolean | UrlTree>;
}

describe('authGuard', () => {
  let authService: AuthService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideRouter(routes)]
    });
    authService = TestBed.inject(AuthService);
  });

  it('libera a navegação quando há sessão ativa', async () => {
    vi.spyOn(authService, 'aguardarSessaoPronta').mockResolvedValue();
    vi.spyOn(authService, 'autenticado').mockReturnValue(true);

    const resultado = await executarGuard('/laboratorio');

    expect(resultado).toBe(true);
  });

  it('redireciona para /login com returnUrl quando não há sessão', async () => {
    vi.spyOn(authService, 'aguardarSessaoPronta').mockResolvedValue();
    vi.spyOn(authService, 'autenticado').mockReturnValue(false);
    const router = TestBed.inject(Router);

    const resultado = await executarGuard('/laboratorio');

    expect(resultado.toString()).toBe(
      router.parseUrl('/login?returnUrl=%2Flaboratorio').toString()
    );
  });

  it('espera a checagem inicial de sessão antes de decidir', async () => {
    let resolverSessao!: () => void;
    const promessaSessao = new Promise<void>((resolve) => {
      resolverSessao = resolve;
    });
    vi.spyOn(authService, 'aguardarSessaoPronta').mockReturnValue(promessaSessao);
    vi.spyOn(authService, 'autenticado').mockReturnValue(true);

    let concluiu = false;
    const execucao = executarGuard('/').then((resultado) => {
      concluiu = true;
      return resultado;
    });

    // Ainda não resolveu a promessa de sessão: o guard não pode ter decidido.
    await Promise.resolve();
    expect(concluiu).toBe(false);

    resolverSessao();
    const resultado = await execucao;
    expect(concluiu).toBe(true);
    expect(resultado).toBe(true);
  });
});
