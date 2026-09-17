import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { consultaAoVivoGuard } from './consulta-ao-vivo.guard';
import { ConsultaAoVivoService } from '../services/consulta-ao-vivo.service';

describe('consultaAoVivoGuard (D-67)', () => {
  let service: ConsultaAoVivoService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideRouter([])] });
    service = TestBed.inject(ConsultaAoVivoService);
  });

  function executar(): Promise<boolean | UrlTree> {
    return TestBed.runInInjectionContext(
      () =>
        consultaAoVivoGuard(
          {} as ActivatedRouteSnapshot,
          { url: '/consulta-ao-vivo' } as RouterStateSnapshot
        ) as Promise<boolean | UrlTree>
    );
  }

  it('deixa passar quem o servidor libera', async () => {
    vi.spyOn(service, 'acesso').mockResolvedValue({ habilitado: true, limitePorPartida: 3 });
    expect(await executar()).toBe(true);
  });

  it('manda para o Hexágono quem não está liberado', async () => {
    vi.spyOn(service, 'acesso').mockResolvedValue({ habilitado: false, limitePorPartida: 0 });
    const resultado = await executar();
    const router = TestBed.inject(Router);
    expect(router.serializeUrl(resultado as UrlTree)).toBe('/');
  });
});
