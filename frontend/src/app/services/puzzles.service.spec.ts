import { TestBed } from '@angular/core/testing';
import { HttpClient, HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { PuzzlesService, InsightsPuzzles } from './puzzles.service';
import { AuthService } from './auth.service';

describe('PuzzlesService', () => {
  let service: PuzzlesService;
  let http: HttpClient;
  let authService: AuthService;

  const mockPayload: InsightsPuzzles = {
    resumo: {
      total: 660,
      acertos: 464,
      erros: 196,
      taxa_acerto_pct: 70.3,
      rating_medio: 1853.7,
      rating_min: 424,
      rating_max: 2790
    },
    temas_vulneraveis: [
      {
        slug: 'defensiveMove',
        nome: 'Lance Defensivo',
        descricao: 'Encontrar a única defesa.',
        categoria: 'defesa',
        total: 31,
        acertos: 14,
        taxa_acerto_pct: 45.2,
        url_treino: 'https://lichess.org/training/defensiveMove'
      }
    ],
    temas_dominados: [
      {
        slug: 'mateIn1',
        nome: 'Mate em 1 lance',
        descricao: 'Rede de mate imediata.',
        categoria: 'mate',
        total: 193,
        acertos: 181,
        taxa_acerto_pct: 93.8,
        url_treino: 'https://lichess.org/training/mateIn1'
      }
    ],
    todos_os_temas: [],
    diagnostico_gap: {
      titulo: 'Gap Tático: Visão Ofensiva vs Defesa Sob Pressão',
      resumo_executivo: 'Rating médio nos puzzles é 1854...',
      analise_comparativa: 'Você brilha em ataque...',
      sugestao_foco: 'Treine lances defensivos...'
    }
  };

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient()] });
    service = TestBed.inject(PuzzlesService);
    http = TestBed.inject(HttpClient);
    authService = TestBed.inject(AuthService);
    vi.spyOn(authService, 'obterAccessToken').mockResolvedValue('jwt-token-teste');
  });

  it('getInsightsPuzzles() envia header Authorization e retorna dados com sucesso', async () => {
    const getSpy = vi.spyOn(http, 'get').mockReturnValue(of(mockPayload));

    const resultado = await service.getInsightsPuzzles();

    expect(resultado.success).toBe(true);
    expect(resultado.dados).toEqual(mockPayload);
    expect(getSpy).toHaveBeenCalledTimes(1);

    const callArgs = getSpy.mock.calls[0];
    expect(callArgs[0]).toContain('/insights/puzzles');
    const headers = (callArgs[1] as { headers: any })?.headers;
    expect(headers?.get('Authorization')).toBe('Bearer jwt-token-teste');
  });

  it('retorna sessaoExpirada=true quando backend devolve 401', async () => {
    vi.spyOn(http, 'get').mockReturnValue(
      throwError(() => new HttpErrorResponse({ status: 401 }))
    );

    const resultado = await service.getInsightsPuzzles();

    expect(resultado.success).toBe(false);
    expect(resultado.sessaoExpirada).toBe(true);
    expect(resultado.error).toContain('sessão expirou');
  });

  it('retorna erro genérico quando requisição falha com 500', async () => {
    vi.spyOn(http, 'get').mockReturnValue(
      throwError(() => new HttpErrorResponse({ status: 500, statusText: 'Internal Server Error' }))
    );

    const resultado = await service.getInsightsPuzzles();

    expect(resultado.success).toBe(false);
    expect(resultado.error).toBeTruthy();
  });
});

