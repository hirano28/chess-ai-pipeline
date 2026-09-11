import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { vi } from 'vitest';
import {
  ExplicadorPosicaoComponent,
  STORAGE_KEY_EXPLICADOR_ATIVO
} from './explicador-posicao.component';
import {
  ExplicacaoPosicaoRecenteItem,
  ResultadoExplicadorPosicao,
  RevisaoAvulsaService
} from '../../services/revisao-avulsa.service';
import { AuthLocalService } from '../../services/auth-local.service';

describe('ExplicadorPosicaoComponent', () => {
  let component: ExplicadorPosicaoComponent;
  let fixture: ComponentFixture<ExplicadorPosicaoComponent>;
  let revisaoService: RevisaoAvulsaService;
  let authService: AuthLocalService;

  const resultadoMock: ResultadoExplicadorPosicao = {
    fen: 'r1bq1rk1/ppp2ppp/2np4/2b1p1N1/2B1P3/3P4/PPP2PPP/R1BQK2R w KQ - 0 8',
    lado_a_jogar: 'BRANCAS',
    lado_analisado: 'BRANCAS',
    avaliacao: {
      score_cp: 350,
      mate: null,
      win_percent: 92.5,
      lado_vencedor: 'BRANCAS',
      descricao: '+3.50 centipawns (vantagem decisiva para Brancas)'
    },
    linhas_taticas: [
      {
        lance: 'Qh5',
        avaliacao: '+350',
        pv_san: ['Qh5', 'h6', 'Qxf7+']
      }
    ],
    refutacao_defesa: {
      defesa: 'h6',
      refutacao_linha: ['Qh5', 'h6', 'Qxf7+'],
      detalhes: 'Após Qh5, h6 falha após Qxf7+.'
    },
    elementos_posicionais: {
      material: {
        pontos_brancas: 39,
        pontos_pretas: 39,
        saldo_brancas: 0,
        descricao: 'Material rigorosamente igual',
        par_bispos_brancas: true,
        par_bispos_pretas: true
      },
      pecas_indefesas: { BRANCAS: [], PRETAS: [] },
      pecas_cravadas: { BRANCAS: [], PRETAS: [] },
      seguranca_rei: {
        BRANCAS: { casa: 'e1', em_xeque: false, casas_vizinhas_atacadas: 0, roque_disponivel: true, resumo: 'Normal' },
        PRETAS: { casa: 'g8', em_xeque: false, casas_vizinhas_atacadas: 2, roque_disponivel: false, resumo: 'Ameaçado' }
      },
      ameacas_imediatas: { cheques: [], capturas: [] }
    },
    explicacao: {
      veredito: 'Brancas têm ataque decisivo na ala do rei.',
      ameaca_concreta: 'Qh5 cria ameaça imparável de mate em f7 e h7.',
      o_que_parece_bom_mas_falha: 'h6 parece expulsar o cavalo mas perde imediatamente.',
      plano_conversao: 'Executar o arremate tático contra o rei desprotegido.',
      resumo_didatico: 'Ataque fulminante aproveitando a falta de peças defensivas ao redor do rei.'
    }
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ExplicadorPosicaoComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()]
    }).compileComponents();

    fixture = TestBed.createComponent(ExplicadorPosicaoComponent);
    component = fixture.componentInstance;
    revisaoService = TestBed.inject(RevisaoAvulsaService);
    authService = TestBed.inject(AuthLocalService);
    authService.setKey('chave-teste');
    component.chaveConfigurada.set(true);
    fixture.detectChanges();
  });

  it('deve criar o componente', () => {
    expect(component).toBeTruthy();
  });

  it('deve desabilitar botão quando posição estiver vazia', () => {
    component.posicao.set('');
    expect(component.formularioValido).toBe(false);
  });

  it('deve carregar exemplo clássico', () => {
    component.carregarExemplo();
    expect(component.posicao()).toContain('r1bq1rk1');
    expect(component.lado()).toBe('BRANCAS');
    expect(component.formularioValido).toBe(true);
  });

  it('deve exibir resultado após análise bem-sucedida', async () => {
    vi.spyOn(revisaoService, 'explicarPosicao').mockResolvedValue({
      success: true,
      resultado: resultadoMock
    });

    component.posicao.set('r1bq1rk1/ppp2ppp/2np4/2b1p1N1/2B1P3/3P4/PPP2PPP/R1BQK2R w KQ - 0 8');
    await component.analisar();
    fixture.detectChanges();

    expect(component.resultado()).toEqual(resultadoMock);
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Veredito Claro');
    expect(element.textContent).toContain('Brancas têm ataque decisivo na ala do rei.');
    expect(element.textContent).toContain('Ameaça Concreta');
  });

  it('deve tratar erro na análise', async () => {
    vi.spyOn(revisaoService, 'explicarPosicao').mockResolvedValue({
      success: false,
      error: 'Posição FEN inválida.'
    });

    component.posicao.set('posicao_invalida');
    await component.analisar();
    fixture.detectChanges();

    expect(component.erro()).toBe('Posição FEN inválida.');
    expect(component.resultado()).toBeNull();
  });

  it('deve limpar resultado anterior ao carregar exemplo', () => {
    component.resultado.set(resultadoMock);
    component.carregarExemplo();
    expect(component.resultado()).toBeNull();
    expect(component.posicao()).toContain('r1bq1rk1');
  });

  it('deve deslogar e pedir chave quando chave for inválida', async () => {
    vi.spyOn(revisaoService, 'explicarPosicao').mockResolvedValue({
      success: false,
      chaveInvalida: true,
      error: 'Chave inválida, tente novamente.'
    });

    component.posicao.set('r1bq1rk1/ppp2ppp/2np4/2b1p1N1/2B1P3/3P4/PPP2PPP/R1BQK2R w KQ - 0 8');
    await component.analisar();
    fixture.detectChanges();

    expect(component.chaveConfigurada()).toBe(false);
    expect(component.erroChave()).toContain('Chave inválida');
  });

  it('deve limpar estado ao chamar novaAnalise', () => {
    component.posicao.set('fen-teste');
    component.lado.set('BRANCAS');
    component.resultado.set(resultadoMock);
    component.erro.set('algum erro');

    component.novaAnalise();

    expect(component.posicao()).toBe('');
    expect(component.lado()).toBe('TODOS');
    expect(component.resultado()).toBeNull();
    expect(component.erro()).toBeNull();
  });

  it('deve retornar cores corretas para corBadgeVencedor', () => {
    expect(component.corBadgeVencedor('BRANCAS')).toContain('bg-[#173322]');
    expect(component.corBadgeVencedor('PRETAS')).toContain('bg-[#331a17]');
    expect(component.corBadgeVencedor('EQUILIBRADO')).toContain('bg-[#332c14]');
  });

  it('deve salvar nova chave de acesso', () => {
    component.chaveConfigurada.set(false);
    component.chaveInput.set('nova-chave-secreta');
    expect(component.chaveFormularioValido).toBe(true);

    component.salvarChave();

    expect(component.chaveConfigurada()).toBe(true);
    expect(component.chaveInput()).toBe('');
    expect(authService.getKey()).toBe('nova-chave-secreta');
  });

  describe('histórico de explicações (fecha P-10)', () => {
    const itemHistorico: ExplicacaoPosicaoRecenteItem = {
      id: 'exp-1',
      fen: resultadoMock.fen,
      lado_analisado: 'BRANCAS',
      created_at: '2026-09-11T10:00:00Z',
      resultado: resultadoMock
    };

    afterEach(() => {
      localStorage.removeItem(STORAGE_KEY_EXPLICADOR_ATIVO);
    });

    it('deve carregar o histórico e mapear para o formato genérico', async () => {
      vi.spyOn(revisaoService, 'listarExplicacoesRecentes').mockResolvedValue({
        success: true,
        itens: [itemHistorico]
      });

      await component.carregarHistorico();
      const itens = component.itensHistoricoComponent();

      expect(component.historico().length).toBe(1);
      expect(itens[0].id).toBe('exp-1');
      expect(itens[0].titulo).toContain('Brancas têm ataque decisivo');
      expect(itens[0].detalhes).toContain('Analisado: Brancas ♔');
      expect(itens[0].detalhes).toContain('Win%: 92.5%');
    });

    it('deve restaurar o resultado completo ao selecionar um item do histórico', () => {
      component.historico.set([itemHistorico]);

      component.selecionarHistorico('exp-1');

      expect(component.resultado()).toEqual(resultadoMock);
      expect(localStorage.getItem(STORAGE_KEY_EXPLICADOR_ATIVO)).toBe('exp-1');
    });

    it('não deve quebrar ao selecionar um id que não existe no histórico carregado', () => {
      component.historico.set([]);
      component.selecionarHistorico('id-inexistente');
      expect(component.resultado()).toBeNull();
    });

    it('deve marcar o resultado recém-gerado como ativo quando o backend devolve id', async () => {
      vi.spyOn(revisaoService, 'explicarPosicao').mockResolvedValue({
        success: true,
        resultado: { ...resultadoMock, id: 'exp-novo-99' }
      });
      vi.spyOn(revisaoService, 'listarExplicacoesRecentes').mockResolvedValue({
        success: true,
        itens: []
      });

      component.posicao.set(resultadoMock.fen);
      await component.analisar();

      expect(localStorage.getItem(STORAGE_KEY_EXPLICADOR_ATIVO)).toBe('exp-novo-99');
    });

    it('novaAnalise deve limpar o item ativo salvo', () => {
      localStorage.setItem(STORAGE_KEY_EXPLICADOR_ATIVO, 'exp-1');
      component.novaAnalise();
      expect(localStorage.getItem(STORAGE_KEY_EXPLICADOR_ATIVO)).toBeNull();
    });
  });
});

