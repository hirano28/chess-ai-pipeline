import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { vi } from 'vitest';
import {
  contarPecasFen,
  ExplicadorPosicaoComponent,
  STORAGE_KEY_EXPLICADOR_ATIVO
} from './explicador-posicao.component';
import {
  ExplicacaoPosicaoRecenteItem,
  ResultadoExplicadorPosicao,
  RevisaoAvulsaService
} from '../../services/revisao-avulsa.service';
import { TeoriaFinaisService } from '../../services/teoria-finais.service';

describe('ExplicadorPosicaoComponent', () => {
  let component: ExplicadorPosicaoComponent;
  let fixture: ComponentFixture<ExplicadorPosicaoComponent>;
  let revisaoService: RevisaoAvulsaService;
  let teoriaFinaisService: TeoriaFinaisService;

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
    teoriaFinaisService = TestBed.inject(TeoriaFinaisService);
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
    expect(element.textContent).toContain('Veredito claro');
    expect(element.textContent).toContain('Brancas têm ataque decisivo na ala do rei.');
    expect(element.textContent).toContain('Ameaça concreta');
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

  it('deve avisar quando a sessão expirar', async () => {
    vi.spyOn(revisaoService, 'explicarPosicao').mockResolvedValue({
      success: false,
      sessaoExpirada: true,
      error: 'Sua sessão expirou. Entre de novo para continuar.'
    });

    component.posicao.set('r1bq1rk1/ppp2ppp/2np4/2b1p1N1/2B1P3/3P4/PPP2PPP/R1BQK2R w KQ - 0 8');
    await component.analisar();
    fixture.detectChanges();

    expect(component.erro()).toContain('sessão expirou');
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
    expect(component.corBadgeVencedor('BRANCAS')).toBe('selo-brancas');
    expect(component.corBadgeVencedor('PRETAS')).toBe('selo-pretas');
    expect(component.corBadgeVencedor('EQUILIBRADO')).toBe('selo-latao');
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
      // Miniatura da posição explicada, na perspectiva do lado analisado.
      expect(itens[0].fen).toBe(itemHistorico.fen);
      expect(itens[0].orientacao).toBe('BRANCAS');
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

  describe('Syzygy Endgame Tablebase', () => {
    const fenFinal3Pecas = '8/8/8/8/4k3/8/4K3/4Q3 w - - 0 1'; // 3 peças (K+Q vs K)

    it('contarPecasFen deve calcular a quantidade correta de peças', () => {
      expect(contarPecasFen(fenFinal3Pecas)).toBe(3);
      expect(contarPecasFen('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')).toBe(32);
    });

    it('não deve consultar Syzygy quando a posição tiver mais de 7 peças', async () => {
      const spySyzygy = vi.spyOn(teoriaFinaisService, 'getAnaliseSyzygy');
      vi.spyOn(revisaoService, 'explicarPosicao').mockResolvedValue({
        success: true,
        resultado: resultadoMock // 30 peças
      });

      component.posicao.set(resultadoMock.fen);
      await component.analisar();

      expect(spySyzygy).not.toHaveBeenCalled();
      expect(component.syzygy()).toBeNull();
    });

    it('deve consultar Syzygy quando a posição tiver <= 7 peças e renderizar o banner', async () => {
      const mockResultadoFinal: ResultadoExplicadorPosicao = {
        ...resultadoMock,
        fen: fenFinal3Pecas
      };

      vi.spyOn(revisaoService, 'explicarPosicao').mockResolvedValue({
        success: true,
        resultado: mockResultadoFinal
      });

      vi.spyOn(teoriaFinaisService, 'getAnaliseSyzygy').mockResolvedValue({
        success: true,
        dados: {
          elegivel_syzygy: true,
          num_pecas: 3,
          categoria_antes: 'win',
          veredito_pt: 'Vitória matemática (brancas)',
          dtm: 10,
          dtz: 10,
          eh_blunder_teorico: false,
          melhores_lances: [
            { uci: 'e1d2', san: 'Qd2', categoria: 'win', dtz: 9 }
          ]
        }
      });

      component.posicao.set(fenFinal3Pecas);
      await component.analisar();
      fixture.detectChanges();

      expect(component.syzygy()?.elegivel_syzygy).toBe(true);
      expect(component.syzygy()?.num_pecas).toBe(3);
      expect(component.syzygy()?.veredito_pt).toBe('Vitória matemática (brancas)');

      const element = fixture.nativeElement as HTMLElement;
      expect(element.textContent).toContain('Syzygy Tablebase');
      expect(element.textContent).toContain('Vitória matemática (brancas)');
      expect(element.textContent).toContain('Final com 3 peças');
    });
  });
});

