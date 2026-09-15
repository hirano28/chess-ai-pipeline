import { TestBed } from '@angular/core/testing';
import { HttpClient, HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { TeoriaFinaisService, TeoriaAbertura, SyzygyAvaliacao } from './teoria-finais.service';
import { AuthService } from './auth.service';

describe('TeoriaFinaisService', () => {
  let service: TeoriaFinaisService;
  let http: HttpClient;
  let authService: AuthService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient()] });
    service = TestBed.inject(TeoriaFinaisService);
    http = TestBed.inject(HttpClient);
    authService = TestBed.inject(AuthService);
    vi.spyOn(authService, 'obterAccessToken').mockResolvedValue('jwt-token-teste');
  });

  describe('getTeoriaAbertura', () => {
    it('consulta endpoint com partidaId e header de autenticação', async () => {
      const mockTeoria: TeoriaAbertura = {
        sucesso: true,
        disponivel: true,
        ply_saida: 12,
        numero_lance_saida: 6,
        cor_saida: 'PRETAS',
        quem_saiu: 'JOGADOR',
        lance_san: 'c5',
        nome_abertura: 'French Defense',
        eco: 'C00'
      };

      const getSpy = vi.spyOn(http, 'get').mockReturnValue(of(mockTeoria));

      const res = await service.getTeoriaAbertura('partida-123');

      expect(res.success).toBe(true);
      expect(res.dados).toEqual(mockTeoria);
      expect(getSpy).toHaveBeenCalledTimes(1);
      const url = getSpy.mock.calls[0][0];
      expect(url).toContain('/partidas/partida-123/teoria-abertura');
    });

    it('retorna erro se a requisição falhar', async () => {
      vi.spyOn(http, 'get').mockReturnValue(
        throwError(() => new HttpErrorResponse({ status: 404, error: { detail: 'Partida não encontrada.' } }))
      );

      const res = await service.getTeoriaAbertura('partida-999');

      expect(res.success).toBe(false);
      expect(res.error).toBe('Partida não encontrada.');
    });
  });

  describe('getAnaliseSyzygy', () => {
    it('consulta endpoint com FEN e lance', async () => {
      const mockSyzygy: SyzygyAvaliacao = {
        elegivel_syzygy: true,
        categoria_antes: 'win',
        categoria_lance_jogado: 'draw',
        eh_blunder_teorico: true,
        tipo_erro_final: 'erro_conversao'
      };

      const getSpy = vi.spyOn(http, 'get').mockReturnValue(of(mockSyzygy));

      const res = await service.getAnaliseSyzygy('8/8/8/4k3/8/8/4Q3/4K3 w - - 0 1', 'Kd2');

      expect(res.success).toBe(true);
      expect(res.dados?.eh_blunder_teorico).toBe(true);
      expect(getSpy).toHaveBeenCalledTimes(1);
      const options = getSpy.mock.calls[0][1] as { params: any };
      expect(options.params.get('fen')).toBe('8/8/8/4k3/8/8/4Q3/4K3 w - - 0 1');
      expect(options.params.get('lance')).toBe('Kd2');
    });
  });
});

