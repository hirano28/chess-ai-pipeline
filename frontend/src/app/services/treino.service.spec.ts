import { TestBed } from '@angular/core/testing';
import { HttpClient, HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { FilaTreino, ResultadoTreino, TreinoService } from './treino.service';
import { AuthService } from './auth.service';

describe('TreinoService', () => {
  let service: TreinoService;
  let http: HttpClient;
  let authService: AuthService;

  const mockFila: FilaTreino = {
    itens: [
      {
        fila_id: 7,
        fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        origem: 'lance_critico',
        numero_lance: 14,
        cor_jogada: 'BRANCAS',
        data_partida: '2026-09-10',
        plataforma: 'LICHESS',
        categoria: null,
        segundos_sugeridos: null,
        repeticoes: 0,
        total_revisoes: 0
      }
    ],
    feitas_hoje: 2,
    total_hoje: 3,
    vencidos_total: 1,
    sessao_id: null
  };

  const mockResultado: ResultadoTreino = {
    qualidade_lance: 'BOM',
    lance_interpretado: 'e4',
    melhor_lance: 'e4',
    queda_win_percent: 0.5,
    raiz_conceitual_violada: 'Não avaliou o centro.',
    tags_falha: ['calculo_tatico_deficiente'],
    livro_citado: 'Meu Sistema',
    capitulo_citado: '4',
    pagina_citada: 88,
    partida_referencia: null,
    partida_url: null,
    fora_do_tempo: false,
    proxima_revisao_data: '2026-09-17',
    repeticoes: 1
  };

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient()] });
    service = TestBed.inject(TreinoService);
    http = TestBed.inject(HttpClient);
    authService = TestBed.inject(AuthService);
    vi.spyOn(authService, 'obterAccessToken').mockResolvedValue('jwt-token-teste');
  });

  it('getFila() envia header Authorization e retorna a fila com sucesso', async () => {
    const getSpy = vi.spyOn(http, 'get').mockReturnValue(of(mockFila));

    const resultado = await service.getFila();

    expect(resultado.success).toBe(true);
    expect(resultado.fila).toEqual(mockFila);
    const callArgs = getSpy.mock.calls[0];
    expect(callArgs[0]).toContain('/treino/fila');
    const headers = (callArgs[1] as { headers: any })?.headers;
    expect(headers?.get('Authorization')).toBe('Bearer jwt-token-teste');
  });

  it('getFila(sessaoId) filtra a fila pelo bloco de prática da sessão', async () => {
    /** D-56: sem o filtro, os 12 cards da sessão ficavam atrás de dezenas de
     * outros vencidos e a sessão não tinha caminho reto do começo ao fim. */
    const getSpy = vi.spyOn(http, 'get').mockReturnValue(of(mockFila));

    await service.getFila('sessao-abc');

    expect(getSpy.mock.calls[0][0]).toContain('/treino/fila?sessao_id=sessao-abc');
  });

  it('getFila() sem sessão não manda parâmetro nenhum', async () => {
    const getSpy = vi.spyOn(http, 'get').mockReturnValue(of(mockFila));

    await service.getFila(null);

    expect(getSpy.mock.calls[0][0]).not.toContain('sessao_id');
  });

  it('getFila() retorna sessaoExpirada=true quando backend devolve 401', async () => {
    vi.spyOn(http, 'get').mockReturnValue(
      throwError(() => new HttpErrorResponse({ status: 401 }))
    );

    const resultado = await service.getFila();

    expect(resultado.success).toBe(false);
    expect(resultado.sessaoExpirada).toBe(true);
  });

  it('responder() envia o lance no corpo e retorna o resultado revelado', async () => {
    const postSpy = vi.spyOn(http, 'post').mockReturnValue(of(mockResultado));

    const resultado = await service.responder(7, 'e4');

    expect(resultado.success).toBe(true);
    expect(resultado.resultado).toEqual(mockResultado);
    const callArgs = postSpy.mock.calls[0];
    expect(callArgs[0]).toContain('/treino/7/responder');
    expect(callArgs[1]).toEqual({ lance: 'e4', segundos_gastos: null });
  });

  it('responder() retorna a mensagem de detail do backend em erro 400', async () => {
    vi.spyOn(http, 'post').mockReturnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 400,
            error: { detail: 'Lance inválido: Txz9.' }
          })
      )
    );

    const resultado = await service.responder(7, 'Txz9');

    expect(resultado.success).toBe(false);
    expect(resultado.error).toBe('Lance inválido: Txz9.');
  });

  it('responder() retorna sessaoExpirada=true quando backend devolve 403', async () => {
    vi.spyOn(http, 'post').mockReturnValue(
      throwError(() => new HttpErrorResponse({ status: 403 }))
    );

    const resultado = await service.responder(7, 'e4');

    expect(resultado.success).toBe(false);
    expect(resultado.sessaoExpirada).toBe(true);
  });

  it('focarCategoria() chama POST /treino/foco/{categoria} e retorna adicionados', async () => {
    const postSpy = vi.spyOn(http, 'post').mockReturnValue(of({ adicionados: 5 }));

    const resultado = await service.focarCategoria('TATICA');

    expect(resultado.success).toBe(true);
    expect(resultado.adicionados).toBe(5);
    const callArgs = postSpy.mock.calls[0];
    expect(callArgs[0]).toContain('/treino/foco/TATICA');
  });

  it('focarCategoria() retorna sessaoExpirada=true quando backend devolve 401', async () => {
    vi.spyOn(http, 'post').mockReturnValue(
      throwError(() => new HttpErrorResponse({ status: 401 }))
    );

    const resultado = await service.focarCategoria('TATICA');

    expect(resultado.success).toBe(false);
    expect(resultado.sessaoExpirada).toBe(true);
  });
});
