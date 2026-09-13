import { TestBed } from '@angular/core/testing';
import { HttpClient, HttpHeaders, provideHttpClient } from '@angular/common/http';
import { of } from 'rxjs';
import { vi } from 'vitest';
import {
  AvaliacaoSequenciaItem,
  RevisaoAvulsaService
} from './revisao-avulsa.service';
import { AuthService } from './auth.service';

/**
 * D-25 unificou a autenticação: a sessão do Supabase Auth é o ÚNICO mecanismo
 * de acesso à API. Toda chamada leva `Authorization: Bearer`, e nenhuma leva
 * `X-API-Key` — que deixou de ser porta de entrada (antes, em D-17, as duas
 * conviviam: a chave dava acesso e o Bearer só refinava o dono da escrita).
 */
describe('RevisaoAvulsaService - autenticação só por sessão (D-25)', () => {
  let service: RevisaoAvulsaService;
  let http: HttpClient;
  let authService: AuthService;

  const avaliacaoMock: AvaliacaoSequenciaItem = {
    indice_na_sequencia: 1,
    lance_jogado: 'e4',
    lance_interpretado: 'e4',
    melhor_lance: 'e4',
    queda_win_percent: 0,
    qualidade_lance: 'BOM',
    qualidade_raciocinio: 'SOLIDO',
    feedback_texto: 'ok',
    analise_mestre: 'ok',
    top_candidatos: [],
    checklist_rotina: {}
  };

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient()] });
    service = TestBed.inject(RevisaoAvulsaService);
    http = TestBed.inject(HttpClient);
    authService = TestBed.inject(AuthService);
    vi.spyOn(authService, 'obterAccessToken').mockResolvedValue('jwt-da-sessao');
  });

  function headersDoPost(spy: ReturnType<typeof vi.spyOn>): HttpHeaders {
    return (spy.mock.calls[0][2] as { headers: HttpHeaders }).headers;
  }

  function headersDoGet(spy: ReturnType<typeof vi.spyOn>): HttpHeaders {
    return (spy.mock.calls[0][1] as { headers: HttpHeaders }).headers;
  }

  describe('escritas', () => {
    it('salvar() envia Authorization e nenhuma X-API-Key', async () => {
      const postSpy = vi.spyOn(http, 'post').mockReturnValue(of({ status: 'salvo', id: 'x' }));

      await service.salvar(avaliacaoMock, 'fen-teste', 'pensamento');

      const headers = headersDoPost(postSpy);
      expect(headers.get('Authorization')).toBe('Bearer jwt-da-sessao');
      expect(headers.has('X-API-Key')).toBe(false);
    });

    it('submeterPartidaPgn() envia Authorization', async () => {
      const postSpy = vi.spyOn(http, 'post').mockReturnValue(
        of({ partida_id: 'p1', external_id: 'ext1' })
      );

      await service.submeterPartidaPgn('1. e4 e5');

      expect(headersDoPost(postSpy).get('Authorization')).toBe('Bearer jwt-da-sessao');
    });
  });

  describe('leituras e análises (antes iam só com X-API-Key)', () => {
    it('revisar() agora também envia Authorization', async () => {
      const postSpy = vi.spyOn(http, 'post').mockReturnValue(
        of({ fen: 'f', lances: [], lance_interpretado: '', avaliacoes: [], resumo_geral: null })
      );

      await service.revisar('fen', ['e4'], 'pensamento');

      const headers = headersDoPost(postSpy);
      expect(headers.get('Authorization')).toBe('Bearer jwt-da-sessao');
      expect(headers.has('X-API-Key')).toBe(false);
    });

    it('listarPartidasRecentes() envia Authorization', async () => {
      const getSpy = vi.spyOn(http, 'get').mockReturnValue(of([]));

      await service.listarPartidasRecentes(20);

      expect(headersDoGet(getSpy).get('Authorization')).toBe('Bearer jwt-da-sessao');
    });

    it('resolverFen() envia Authorization', async () => {
      const getSpy = vi.spyOn(http, 'get').mockReturnValue(of({ fen: 'f' }));

      await service.resolverFen('1. e4');

      expect(headersDoGet(getSpy).get('Authorization')).toBe('Bearer jwt-da-sessao');
    });
  });

  describe('sessão ausente', () => {
    it('sem token, não inventa header nenhum — o backend responde 401', async () => {
      vi.spyOn(authService, 'obterAccessToken').mockResolvedValue(null);
      const postSpy = vi.spyOn(http, 'post').mockReturnValue(of({ status: 'salvo', id: 'x' }));

      await service.salvar(avaliacaoMock, 'fen-teste', 'pensamento');

      const headers = headersDoPost(postSpy);
      expect(headers.has('Authorization')).toBe(false);
      expect(headers.has('X-API-Key')).toBe(false);
    });
  });
});
