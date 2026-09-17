import { TestBed } from '@angular/core/testing';
import { HttpClient, HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConsultaAoVivoService } from './consulta-ao-vivo.service';
import { AuthService } from './auth.service';

describe('ConsultaAoVivoService (D-67)', () => {
  let service: ConsultaAoVivoService;
  let http: HttpClient;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        { provide: AuthService, useValue: { obterAccessToken: async () => 'token' } }
      ]
    });
    service = TestBed.inject(ConsultaAoVivoService);
    http = TestBed.inject(HttpClient);
  });

  it('acesso traduz a resposta do servidor', async () => {
    vi.spyOn(http, 'get').mockReturnValue(of({ habilitado: true, limite_por_partida: 3 }));
    expect(await service.acesso()).toEqual({ habilitado: true, limitePorPartida: 3 });
  });

  it('qualquer falha no acesso conta como não liberado', async () => {
    vi.spyOn(http, 'get').mockReturnValue(throwError(() => new HttpErrorResponse({ status: 500 })));
    expect(await service.acesso()).toEqual({ habilitado: false, limitePorPartida: 0 });
  });

  it('429 marca limite atingido e usa a mensagem do servidor', async () => {
    vi.spyOn(http, 'post').mockReturnValue(
      throwError(
        () => new HttpErrorResponse({ status: 429, error: { detail: 'Acabaram as consultas.' } })
      )
    );
    const resultado = await service.consultar({
      partida_espelho_id: 'p',
      lances: [],
      fen_inicial: null,
      cor_jogador: 'BRANCAS',
      plataforma: 'LICHESS',
      adversario: null,
      pensamento: null
    });
    expect(resultado).toEqual({
      success: false,
      error: 'Acabaram as consultas.',
      limiteAtingido: true
    });
  });

  it('401 vira sessão expirada', async () => {
    vi.spyOn(http, 'get').mockReturnValue(throwError(() => new HttpErrorResponse({ status: 401 })));
    const resultado = await service.listarDaPartida('p');
    expect(resultado.sessaoExpirada).toBe(true);
  });

  it('manda o token de sessão', async () => {
    const get = vi.spyOn(http, 'get').mockReturnValue(of([]));
    await service.listarDaPartida('abc');
    const opcoes = get.mock.calls[0][1] as { headers: { get(nome: string): string | null } };
    expect(opcoes.headers.get('Authorization')).toBe('Bearer token');
    expect(get.mock.calls[0][0]).toContain('/consulta-ao-vivo/partida/abc');
  });
});
