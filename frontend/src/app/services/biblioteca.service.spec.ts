import { TestBed } from '@angular/core/testing';
import { HttpClient, HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import {
  BibliotecaService,
  RespostaBiblioteca,
  formatarFonte
} from './biblioteca.service';
import { AuthService } from './auth.service';

describe('formatarFonte', () => {
  it('monta livro, capítulo e página', () => {
    expect(
      formatarFonte({
        livro: 'Meu Sistema',
        capitulo: 'A Peça Cravada',
        pagina_aprox: 111
      })
    ).toBe('Meu Sistema — A Peça Cravada (pág. 111)');
  });

  it('omite o que não existe em vez de escrever "null"', () => {
    expect(formatarFonte({ livro: 'Meu Sistema' })).toBe('Meu Sistema');
    expect(formatarFonte({ livro: 'Meu Sistema', pagina_aprox: 12 })).toBe(
      'Meu Sistema (pág. 12)'
    );
  });
});

describe('BibliotecaService', () => {
  let service: BibliotecaService;
  let http: HttpClient;
  let authService: AuthService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient()] });
    service = TestBed.inject(BibliotecaService);
    http = TestBed.inject(HttpClient);
    authService = TestBed.inject(AuthService);
    vi.spyOn(authService, 'obterAccessToken').mockResolvedValue('jwt-token-teste');
  });

  it('envia a pergunta e devolve resposta com fontes', async () => {
    const mock: RespostaBiblioteca = {
      id: 'abc',
      pergunta: 'o que é cravada?',
      resposta: 'A cravada imobiliza a peça.',
      fontes: [{ livro: 'Meu Sistema', capitulo: 'A Peça Cravada', pagina_aprox: 111 }]
    };
    const postSpy = vi.spyOn(http, 'post').mockReturnValue(of(mock));

    const res = await service.consultar('o que é cravada?');

    expect(res.success).toBe(true);
    expect(res.dados).toEqual(mock);
    expect(postSpy.mock.calls[0][0]).toContain('/biblioteca/consultar');
    expect(postSpy.mock.calls[0][1]).toEqual({ pergunta: 'o que é cravada?' });
  });

  it('sinaliza sessão expirada num 401 para a tela pedir login de novo', async () => {
    vi.spyOn(http, 'post').mockReturnValue(
      throwError(() => new HttpErrorResponse({ status: 401 }))
    );

    const res = await service.consultar('qualquer coisa');

    expect(res.success).toBe(false);
    expect(res.sessaoExpirada).toBe(true);
  });

  it('propaga a mensagem do backend num erro de validação', async () => {
    vi.spyOn(http, 'post').mockReturnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 400,
            error: { detail: 'Escreva uma pergunta para consultar os livros.' }
          })
      )
    );

    const res = await service.consultar('   ');

    expect(res.success).toBe(false);
    expect(res.error).toBe('Escreva uma pergunta para consultar os livros.');
    expect(res.sessaoExpirada).toBeUndefined();
  });

  it('carrega o histórico', async () => {
    const getSpy = vi.spyOn(http, 'get').mockReturnValue(of([]));

    const res = await service.listarRecentes();

    expect(res.success).toBe(true);
    expect(getSpy.mock.calls[0][0]).toContain('/biblioteca/recentes');
  });
});
