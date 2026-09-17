import { TestBed } from '@angular/core/testing';
import { HttpClient, HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { ExecucaoSessao, SessaoService } from './sessao.service';
import { AuthService } from './auth.service';

describe('SessaoService', () => {
  let service: SessaoService;
  let http: HttpClient;
  let authService: AuthService;

  const mockExecucao: ExecucaoSessao = {
    sessao_id: 'sessao-abc',
    titulo: 'Sprint de Tática',
    categoria_foco: 'TATICA',
    data_prescrita: '2026-09-15',
    data_iniciada: null,
    data_concluida: null,
    duracao_total_min: 90,
    concluida: false,
    blocos: [
      {
        indice: 0,
        tipo: 'estudo',
        nome: 'Ler o capítulo sobre cravadas',
        conteudo: 'Meu Sistema, cap. 4',
        duracao_min: 30,
        livro: 'Meu Sistema',
        capitulo: '4',
        pagina_aprox: 88,
        concluido: false,
        categoria: null,
        exercicios_feitos: null,
        exercicios_total: null
      },
      {
        indice: 1,
        tipo: 'pratica',
        nome: 'Praticar 12 exercícios de Tática',
        conteudo: null,
        duracao_min: 60,
        livro: null,
        capitulo: null,
        pagina_aprox: null,
        concluido: false,
        categoria: 'TATICA',
        exercicios_feitos: 3,
        exercicios_total: 12
      }
    ]
  };

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient()] });
    service = TestBed.inject(SessaoService);
    http = TestBed.inject(HttpClient);
    authService = TestBed.inject(AuthService);
    vi.spyOn(authService, 'obterAccessToken').mockResolvedValue('jwt-token-teste');
  });

  it('obterExecucao() busca a sessão certa com o header de sessão', async () => {
    const getSpy = vi.spyOn(http, 'get').mockReturnValue(of(mockExecucao));

    const resultado = await service.obterExecucao('sessao-abc');

    expect(resultado.success).toBe(true);
    expect(resultado.execucao).toEqual(mockExecucao);
    const callArgs = getSpy.mock.calls[0];
    expect(callArgs[0]).toContain('/sessoes/sessao-abc/execucao');
    const headers = (callArgs[1] as { headers: any })?.headers;
    expect(headers?.get('Authorization')).toBe('Bearer jwt-token-teste');
  });

  it('iniciar() faz POST no endpoint de início da sessão', async () => {
    const postSpy = vi.spyOn(http, 'post').mockReturnValue(of(mockExecucao));

    const resultado = await service.iniciar('sessao-abc');

    expect(resultado.success).toBe(true);
    expect(postSpy.mock.calls[0][0]).toContain('/sessoes/sessao-abc/iniciar');
    // Corpo vazio de propósito: quem monta o bloco de prática é o backend, a
    // partir da categoria do gargalo. A tela não escolhe exercício.
    expect(postSpy.mock.calls[0][1]).toEqual({});
  });

  it('concluirBloco() endereça o bloco pelo índice', async () => {
    const postSpy = vi.spyOn(http, 'post').mockReturnValue(of(mockExecucao));

    await service.concluirBloco('sessao-abc', 1);

    expect(postSpy.mock.calls[0][0]).toContain('/sessoes/sessao-abc/blocos/1/concluir');
  });

  it('marcar o bloco de índice 0 não cai em caminho falsy', async () => {
    /** `0` é índice válido e valor falsy: um `if (indice)` no caminho da URL
     * mandaria o primeiro bloco de estudo para a rota errada, e ele é
     * justamente o mais provável de ser marcado primeiro. */
    const postSpy = vi.spyOn(http, 'post').mockReturnValue(of(mockExecucao));

    await service.concluirBloco('sessao-abc', 0);

    expect(postSpy.mock.calls[0][0]).toContain('/blocos/0/concluir');
  });

  it('devolve sessaoExpirada=true no 401', async () => {
    vi.spyOn(http, 'get').mockReturnValue(
      throwError(() => new HttpErrorResponse({ status: 401 }))
    );

    const resultado = await service.obterExecucao('sessao-abc');

    expect(resultado.success).toBe(false);
    expect(resultado.sessaoExpirada).toBe(true);
    expect(resultado.error).toContain('sessão expirou');
  });

  it('trata 403 como sessão expirada também', async () => {
    vi.spyOn(http, 'post').mockReturnValue(
      throwError(() => new HttpErrorResponse({ status: 403 }))
    );

    const resultado = await service.iniciar('sessao-abc');

    expect(resultado.sessaoExpirada).toBe(true);
  });

  it('sessão de outro dono responde 404 e NÃO vira "sessão expirada"', async () => {
    /** O backend responde 404, não 403, para sessão de outro usuário (mesmo
     * padrão do D-29). Confundir os dois mandaria o usuário fazer login de
     * novo para resolver um problema que não é de autenticação. */
    vi.spyOn(http, 'get').mockReturnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 404,
            error: { detail: 'Sessão de treino não encontrada.' }
          })
      )
    );

    const resultado = await service.obterExecucao('sessao-de-outro');

    expect(resultado.success).toBe(false);
    expect(resultado.sessaoExpirada).toBeUndefined();
    expect(resultado.error).toBe('Sessão de treino não encontrada.');
  });

  it('erro de rede (status 0) vira mensagem de conexão, não de servidor', async () => {
    vi.spyOn(http, 'get').mockReturnValue(
      throwError(() => new HttpErrorResponse({ status: 0 }))
    );

    const resultado = await service.obterExecucao('sessao-abc');

    expect(resultado.error).toContain('conectar ao servidor');
  });

  it('sem token, a chamada sai sem header em vez de explodir', async () => {
    /** Deixar a API responder 401 é melhor que a tela quebrar antes de pedir:
     * o fluxo de "sessão expirou" já existe e trata isso. */
    vi.spyOn(authService, 'obterAccessToken').mockResolvedValue(null);
    const getSpy = vi.spyOn(http, 'get').mockReturnValue(of(mockExecucao));

    const resultado = await service.obterExecucao('sessao-abc');

    expect(resultado.success).toBe(true);
    const headers = (getSpy.mock.calls[0][1] as { headers: any })?.headers;
    expect(headers?.has('Authorization')).toBe(false);
  });
});
