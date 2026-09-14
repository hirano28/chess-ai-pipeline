import { TestBed } from '@angular/core/testing';
import { HttpClient, HttpHeaders, provideHttpClient } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { LichessOauthService } from './lichess-oauth.service';
import { AuthService } from './auth.service';

describe('LichessOauthService (D-35)', () => {
  let service: LichessOauthService;
  let http: HttpClient;
  let authService: AuthService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient()] });
    service = TestBed.inject(LichessOauthService);
    http = TestBed.inject(HttpClient);
    authService = TestBed.inject(AuthService);
    vi.spyOn(authService, 'obterAccessToken').mockResolvedValue('jwt-da-sessao');
  });

  function headersDoGet(spy: ReturnType<typeof vi.spyOn>): HttpHeaders {
    return (spy.mock.calls[0][1] as { headers: HttpHeaders }).headers;
  }

  function headersDoPost(spy: ReturnType<typeof vi.spyOn>): HttpHeaders {
    return (spy.mock.calls[0][2] as { headers: HttpHeaders }).headers;
  }

  it('obterStatus() envia header Authorization e retorna status conectado', async () => {
    const getSpy = vi.spyOn(http, 'get').mockReturnValue(
      of({ conectado: true, expires_at: '2027-01-01T00:00:00+00:00' })
    );

    const status = await service.obterStatus();

    expect(status.conectado).toBe(true);
    expect(status.expires_at).toBe('2027-01-01T00:00:00+00:00');
    const headers = headersDoGet(getSpy);
    expect(headers.get('Authorization')).toBe('Bearer jwt-da-sessao');
  });

  it('obterStatus() retorna conectado=false em caso de falha HTTP', async () => {
    vi.spyOn(http, 'get').mockReturnValue(throwError(() => new Error('Falha')));

    const status = await service.obterStatus();

    expect(status.conectado).toBe(false);
  });

  it('iniciarConexao() envia post e retorna url_autorizacao', async () => {
    const postSpy = vi.spyOn(http, 'post').mockReturnValue(
      of({ url_autorizacao: 'https://lichess.org/oauth?xyz', expira_em: '2026-09-14' })
    );

    const url = await service.iniciarConexao();

    expect(url).toBe('https://lichess.org/oauth?xyz');
    const headers = headersDoPost(postSpy);
    expect(headers.get('Authorization')).toBe('Bearer jwt-da-sessao');
  });

  it('desconectar() chama rota de desconexão com Authorization', async () => {
    const postSpy = vi.spyOn(http, 'post').mockReturnValue(of({ desconectado: true }));

    const sucesso = await service.desconectar();

    expect(sucesso).toBe(true);
    const headers = headersDoPost(postSpy);
    expect(headers.get('Authorization')).toBe('Bearer jwt-da-sessao');
  });

  it('desconectar() retorna false se requisição falhar', async () => {
    vi.spyOn(http, 'post').mockReturnValue(throwError(() => new Error('erro')));

    const sucesso = await service.desconectar();

    expect(sucesso).toBe(false);
  });
});

