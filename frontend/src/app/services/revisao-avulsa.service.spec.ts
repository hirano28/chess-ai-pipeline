import { TestBed } from '@angular/core/testing';
import { HttpClient, HttpHeaders, provideHttpClient } from '@angular/common/http';
import { of } from 'rxjs';
import { vi } from 'vitest';
import {
  AvaliacaoSequenciaItem,
  RevisaoAvulsaService
} from './revisao-avulsa.service';
import { AuthLocalService } from './auth-local.service';
import { AuthService } from './auth.service';

/**
 * Só os 3 métodos que escrevem nas tabelas raiz (D-14) ganham Authorization:
 * Bearer quando há sessão ativa - salvar() (revisao_exercicio_avulso),
 * explicarPosicao() (explicacoes_posicao) e submeterPartidaPgn() (partidas).
 * Fase B.2 (D-17): X-API-Key continua indo em toda chamada, controlando o
 * acesso ao endpoint; Authorization só refina o dono da escrita.
 */
describe('RevisaoAvulsaService - Authorization por sessão (Fase B.2, D-17)', () => {
  let service: RevisaoAvulsaService;
  let http: HttpClient;
  let authService: AuthService;
  let authLocalService: AuthLocalService;

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
    authLocalService = TestBed.inject(AuthLocalService);
    authLocalService.setKey('chave-de-teste');
  });

  function headersDaChamada(postSpy: ReturnType<typeof vi.spyOn>): HttpHeaders {
    return (postSpy.mock.calls[0][2] as { headers: HttpHeaders }).headers;
  }

  describe('salvar (POST /revisar-avulso/salvar)', () => {
    it('envia só X-API-Key sem sessão Supabase Auth ativa', async () => {
      vi.spyOn(authService, 'autenticado').mockReturnValue(false);
      const postSpy = vi.spyOn(http, 'post').mockReturnValue(of({ status: 'salvo', id: 'x' }));

      await service.salvar(avaliacaoMock, 'fen-teste', 'pensamento');

      const headers = headersDaChamada(postSpy);
      expect(headers.get('X-API-Key')).toBe('chave-de-teste');
      expect(headers.has('Authorization')).toBe(false);
    });

    it('envia X-API-Key + Authorization: Bearer com sessão ativa', async () => {
      vi.spyOn(authService, 'autenticado').mockReturnValue(true);
      vi.spyOn(authService, 'obterAccessToken').mockResolvedValue('jwt-da-sessao');
      const postSpy = vi.spyOn(http, 'post').mockReturnValue(of({ status: 'salvo', id: 'x' }));

      await service.salvar(avaliacaoMock, 'fen-teste', 'pensamento');

      const headers = headersDaChamada(postSpy);
      expect(headers.get('X-API-Key')).toBe('chave-de-teste');
      expect(headers.get('Authorization')).toBe('Bearer jwt-da-sessao');
    });

    it('autenticado mas sem token (sessão expirou entre a checagem e getSession) não quebra', async () => {
      vi.spyOn(authService, 'autenticado').mockReturnValue(true);
      vi.spyOn(authService, 'obterAccessToken').mockResolvedValue(null);
      const postSpy = vi.spyOn(http, 'post').mockReturnValue(of({ status: 'salvo', id: 'x' }));

      await service.salvar(avaliacaoMock, 'fen-teste', 'pensamento');

      const headers = headersDaChamada(postSpy);
      expect(headers.get('X-API-Key')).toBe('chave-de-teste');
      expect(headers.has('Authorization')).toBe(false);
    });
  });

  describe('explicarPosicao (POST /explicar-posicao)', () => {
    it('envia Authorization: Bearer com sessão ativa', async () => {
      vi.spyOn(authService, 'autenticado').mockReturnValue(true);
      vi.spyOn(authService, 'obterAccessToken').mockResolvedValue('jwt-da-sessao');
      const postSpy = vi.spyOn(http, 'post').mockReturnValue(
        of({
          fen: 'fen-x',
          lado_a_jogar: 'BRANCAS',
          lado_analisado: 'BRANCAS',
          avaliacao: {
            score_cp: 0,
            mate: null,
            win_percent: 50,
            lado_vencedor: 'EQUILIBRADO',
            descricao: ''
          },
          linhas_taticas: [],
          elementos_posicionais: {},
          explicacao: {
            veredito: '',
            ameaca_concreta: '',
            o_que_parece_bom_mas_falha: '',
            plano_conversao: '',
            resumo_didatico: ''
          }
        })
      );

      await service.explicarPosicao('fen-x');

      expect(headersDaChamada(postSpy).get('Authorization')).toBe('Bearer jwt-da-sessao');
    });
  });

  describe('submeterPartidaPgn (POST /analisar-pgn)', () => {
    it('envia Authorization: Bearer com sessão ativa', async () => {
      vi.spyOn(authService, 'autenticado').mockReturnValue(true);
      vi.spyOn(authService, 'obterAccessToken').mockResolvedValue('jwt-da-sessao');
      const postSpy = vi.spyOn(http, 'post').mockReturnValue(
        of({ partida_id: 'p1', external_id: 'ext1' })
      );

      await service.submeterPartidaPgn('1. e4 e5');

      expect(headersDaChamada(postSpy).get('Authorization')).toBe('Bearer jwt-da-sessao');
    });
  });

  describe('métodos fora do escopo de B.2 (não persistem em tabela raiz)', () => {
    it('revisar() continua sem Authorization mesmo com sessão ativa', async () => {
      vi.spyOn(authService, 'autenticado').mockReturnValue(true);
      const obterTokenSpy = vi.spyOn(authService, 'obterAccessToken');
      const postSpy = vi.spyOn(http, 'post').mockReturnValue(
        of({ fen: 'f', lances: [], lance_interpretado: '', avaliacoes: [], resumo_geral: null })
      );

      await service.revisar('fen', ['e4'], 'pensamento');

      expect(obterTokenSpy).not.toHaveBeenCalled();
      expect(headersDaChamada(postSpy).has('Authorization')).toBe(false);
    });
  });
});
