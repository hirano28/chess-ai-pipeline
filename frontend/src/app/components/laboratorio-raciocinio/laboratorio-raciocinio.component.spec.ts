import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { vi } from 'vitest';
import {
  LaboratorioRaciocinioComponent,
  STORAGE_KEY_LABORATORIO_ATIVO
} from './laboratorio-raciocinio.component';
import {
  AvaliacaoSequenciaItem,
  ResultadoRevisaoAvulsa,
  RevisaoAvulsaRecenteItem,
  RevisaoAvulsaService
} from '../../services/revisao-avulsa.service';
import { AuthLocalService } from '../../services/auth-local.service';

describe('LaboratorioRaciocinioComponent', () => {
  let component: LaboratorioRaciocinioComponent;
  let fixture: ComponentFixture<LaboratorioRaciocinioComponent>;
  let revisaoService: RevisaoAvulsaService;
  let authService: AuthLocalService;

  const avaliacaoMock: AvaliacaoSequenciaItem = {
    indice_na_sequencia: 1,
    lance_jogado: 'Nf3',
    lance_interpretado: 'Cf3',
    melhor_lance: 'e4',
    queda_win_percent: 1.5,
    qualidade_lance: 'BOM',
    qualidade_raciocinio: 'SOLIDO',
    feedback_texto: 'Bom desenvolvimento.',
    analise_mestre: 'Linha sólida.',
    top_candidatos: [],
    checklist_rotina: {}
  };

  const resultadoMock: ResultadoRevisaoAvulsa = {
    fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    lances: ['Nf3'],
    lance_interpretado: 'Cf3',
    avaliacoes: [avaliacaoMock],
    resumo_geral: null
  };

  const itemHistoricoMock: RevisaoAvulsaRecenteItem = {
    id: 'rev-1',
    fen: resultadoMock.fen,
    lance_jogado: 'Nf3',
    melhor_lance: 'e4',
    queda_win_percent: 1.5,
    texto_pensamento: 'Desenvolvo o cavalo.',
    qualidade_lance: 'BOM',
    qualidade_raciocinio: 'SOLIDO',
    feedback_texto: 'Bom desenvolvimento.',
    created_at: '2026-09-11T10:00:00Z'
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LaboratorioRaciocinioComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()]
    }).compileComponents();

    fixture = TestBed.createComponent(LaboratorioRaciocinioComponent);
    component = fixture.componentInstance;
    revisaoService = TestBed.inject(RevisaoAvulsaService);
    authService = TestBed.inject(AuthLocalService);
    authService.setKey('chave-teste');
    component.chaveConfigurada.set(true);
    vi.spyOn(revisaoService, 'guiaPassos').mockResolvedValue([]);
  });

  afterEach(() => {
    localStorage.removeItem(STORAGE_KEY_LABORATORIO_ATIVO);
  });

  it('deve criar o componente', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('deve mapear o histórico para o formato genérico do componente compartilhado', async () => {
    vi.spyOn(revisaoService, 'listarRevisoesAvulsasRecentes').mockResolvedValue({
      success: true,
      itens: [itemHistoricoMock]
    });

    await component.carregarHistorico();
    const itens = component.itensHistoricoComponent();

    expect(itens.length).toBe(1);
    expect(itens[0].id).toBe('rev-1');
    expect(itens[0].titulo).toBe('Lance Nf3');
    expect(itens[0].detalhes).toContain('Qualidade: BOM');
    expect(itens[0].detalhes).toContain('Raciocínio: SOLIDO');
  });

  it('deve exibir o card somente-leitura ao selecionar um item do histórico', () => {
    component.historico.set([itemHistoricoMock]);
    component.resultado.set(resultadoMock);

    component.selecionarHistorico('rev-1');

    expect(component.visualizandoHistorico()).toEqual(itemHistoricoMock);
    expect(component.resultado()).toBeNull();
    expect(localStorage.getItem(STORAGE_KEY_LABORATORIO_ATIVO)).toBe('rev-1');
  });

  it('não deve quebrar ao selecionar um id que não existe no histórico carregado', () => {
    component.historico.set([]);
    component.selecionarHistorico('id-inexistente');
    expect(component.visualizandoHistorico()).toBeNull();
  });

  it('novaAnalise deve fechar a visualização do histórico e limpar o item ativo', () => {
    component.historico.set([itemHistoricoMock]);
    component.selecionarHistorico('rev-1');
    expect(component.visualizandoHistorico()).not.toBeNull();

    component.novaAnalise();

    expect(component.visualizandoHistorico()).toBeNull();
    expect(localStorage.getItem(STORAGE_KEY_LABORATORIO_ATIVO)).toBeNull();
  });

  it('salvarExercicio deve marcar o item como ativo quando o backend devolve id', async () => {
    component.resultado.set(resultadoMock);
    vi.spyOn(revisaoService, 'salvar').mockResolvedValue({ success: true, id: 'rev-novo-42' });
    vi.spyOn(revisaoService, 'listarRevisoesAvulsasRecentes').mockResolvedValue({
      success: true,
      itens: []
    });

    await component.salvarExercicio();

    expect(component.salvo()).toBe(true);
    expect(localStorage.getItem(STORAGE_KEY_LABORATORIO_ATIVO)).toBe('rev-novo-42');
  });

  it('analisar deve abandonar a visualização do histórico ativa', async () => {
    component.historico.set([itemHistoricoMock]);
    component.selecionarHistorico('rev-1');

    component.posicao.set(resultadoMock.fen);
    component.lance.set('Nf3');
    component.pensamento.set('Desenvolvo.');
    vi.spyOn(revisaoService, 'revisar').mockResolvedValue({
      success: true,
      resultado: resultadoMock
    });

    await component.analisar();

    expect(component.visualizandoHistorico()).toBeNull();
    expect(localStorage.getItem(STORAGE_KEY_LABORATORIO_ATIVO)).toBeNull();
    expect(component.resultado()).toEqual(resultadoMock);
  });
});
