import { TestBed } from '@angular/core/testing';
import { HttpClient, HttpErrorResponse, HttpHeaders, provideHttpClient } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { RepertorioService, InsightsRepertorio } from './repertorio.service';
import { AuthService } from './auth.service';

describe('RepertorioService', () => {
  let service: RepertorioService;
  let http: HttpClient;
  let authService: AuthService;

  const mockPayload: InsightsRepertorio = {
    taxa_vitoria_por_cor: {
      BRANCAS: { total: 10, vitorias: 6, taxa_vitoria_pct: 60.0 },
      PRETAS: { total: 10, vitorias: 4, taxa_vitoria_pct: 40.0 }
    },
    por_abertura_e_cor: [
      {
        abertura_normalizada: 'Francesa',
        cor_jogada: 'PRETAS',
        total: 8,
        vitorias: 5,
        taxa_vitoria_pct: 62.5
      }
    ],
    lance_pico_por_abertura: [
      {
        abertura_normalizada: 'Francesa',
        total_eventos: 8,
        lance_medio: 14.2,
        lance_mediano: 14
      }
    ],
    categorias_por_abertura: {
      Francesa: { TATICA: 5, ESTRATEGIA: 3 }
    }
  };

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient()] });
    service = TestBed.inject(RepertorioService);
    http = TestBed.inject(HttpClient);
    authService = TestBed.inject(AuthService);
    vi.spyOn(authService, 'obterAccessToken').mockResolvedValue('jwt-token-teste');
  });

  it('getInsightsRepertorio() envia header Authorization e retorna dados com sucesso', async () => {
    const getSpy = vi.spyOn(http, 'get').mockReturnValue(of(mockPayload));

    const res = await service.getInsightsRepertorio();

    expect(res.success).toBe(true);
    expect(res.dados).toEqual(mockPayload);
    const headers = (getSpy.mock.calls[0][1] as { headers: HttpHeaders }).headers;
    expect(headers.get('Authorization')).toBe('Bearer jwt-token-teste');
  });

  it('getInsightsRepertorio() trata erro 401 como sessaoExpirada', async () => {
    vi.spyOn(http, 'get').mockReturnValue(
      throwError(() => new HttpErrorResponse({ status: 401, statusText: 'Unauthorized' }))
    );

    const res = await service.getInsightsRepertorio();

    expect(res.success).toBe(false);
    expect(res.sessaoExpirada).toBe(true);
    expect(res.error).toContain('sessão expirou');
  });

  it('getInsightsRepertorio() trata erro genérico com mensagem de falha', async () => {
    vi.spyOn(http, 'get').mockReturnValue(
      throwError(() => new Error('Falha de rede'))
    );

    const res = await service.getInsightsRepertorio();

    expect(res.success).toBe(false);
    expect(res.sessaoExpirada).toBeUndefined();
    expect(res.error).toBe('Falha de rede');
  });
});

