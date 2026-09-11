import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { vi } from 'vitest';
import { AnalisadorPartidaComponent } from './analisador-partida.component';
import {
  ResumoPartidaData,
  RevisaoAvulsaService
} from '../../services/revisao-avulsa.service';
import { AuthLocalService } from '../../services/auth-local.service';

describe('AnalisadorPartidaComponent', () => {
  let component: AnalisadorPartidaComponent;
  let fixture: ComponentFixture<AnalisadorPartidaComponent>;
  let revisaoService: RevisaoAvulsaService;
  let authService: AuthLocalService;

  const resumoMock: ResumoPartidaData = {
    narrativa: 'A partida iniciou com a Defesa Siciliana variante Najdorf. No lance 15, as brancas sacrificaram em f7 criando vantagem decisiva.',
    pontos_criticos: [
      {
        numero_lance: 15,
        tipo_evento: 'PICO',
        tags_falha: ['calculo_tatico_deficiente', 'perda_de_material']
      },
      {
        numero_lance: 28,
        tipo_evento: 'EROSAO',
        tags_falha: ['passividade_excessiva']
      }
    ],
    momento_chave_estrategico: 'O sacrifício tático no lance 15 desestruturou a defesa das pretas.'
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AnalisadorPartidaComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()]
    }).compileComponents();

    fixture = TestBed.createComponent(AnalisadorPartidaComponent);
    component = fixture.componentInstance;
    revisaoService = TestBed.inject(RevisaoAvulsaService);
    authService = TestBed.inject(AuthLocalService);
    authService.setKey('chave-teste');
    component.chaveConfigurada.set(true);
    fixture.detectChanges();
  });

  afterEach(() => {
    component.ngOnDestroy();
  });

  it('deve ser criado com estado inicial', () => {
    expect(component).toBeTruthy();
    expect(component.estado()).toBe('INICIAL');
    expect(component.pgn()).toBe('');
    expect(component.cor()).toBe('AUTO');
  });

  it('deve carregar exemplo de partida', () => {
    component.carregarExemplo();
    expect(component.pgn().length).toBeGreaterThan(50);
    expect(component.cor()).toBe('BRANCAS');
    expect(component.formularioValido).toBe(true);
  });

  it('não deve analisar se o formulário for inválido', async () => {
    const spySubmeter = vi.spyOn(revisaoService, 'submeterPartidaPgn');
    component.pgn.set('   ');
    await component.analisar();
    expect(spySubmeter).not.toHaveBeenCalled();
    expect(component.estado()).toBe('INICIAL');
  });

  it('deve submeter PGN com sucesso e transicionar para PROCESSANDO', async () => {
    vi.spyOn(revisaoService, 'submeterPartidaPgn').mockResolvedValue({
      success: true,
      partidaId: 'partida-123',
      externalId: 'manual_abc123'
    });

    component.pgn.set('1. e4 e5 2. Nf3 Nc6');
    component.cor.set('BRANCAS');

    await component.analisar();

    expect(component.estado()).toBe('PROCESSANDO');
    expect(component.partidaId()).toBe('partida-123');
    expect(component.externalId()).toBe('manual_abc123');
  });

  it('deve tratar erro na submissão e permanecer em INICIAL com mensagem de erro', async () => {
    vi.spyOn(revisaoService, 'submeterPartidaPgn').mockResolvedValue({
      success: false,
      error: 'Não foi possível inferir a cor do jogador.'
    });

    component.pgn.set('1. e4 e5 2. Nf3 Nc6');
    await component.analisar();

    expect(component.estado()).toBe('INICIAL');
    expect(component.erro()).toBe('Não foi possível inferir a cor do jogador.');
  });

  it('deve tratar chave inválida na submissão', async () => {
    vi.spyOn(revisaoService, 'submeterPartidaPgn').mockResolvedValue({
      success: false,
      chaveInvalida: true
    });

    component.pgn.set('1. e4 e5 2. Nf3 Nc6');
    await component.analisar();

    expect(component.chaveConfigurada()).toBe(false);
    expect(component.erroChave()).toContain('Chave inválida');
    expect(component.estado()).toBe('INICIAL');
  });

  it('deve salvar nova chave de API', () => {
    component.chaveInput.set('nova-chave-secreta');
    component.salvarChave();

    expect(authService.getKey()).toBe('nova-chave-secreta');
    expect(component.chaveConfigurada()).toBe(true);
    expect(component.chaveInput()).toBe('');
  });

  it('deve resetar o estado ao chamar novaAnalise', () => {
    component.pgn.set('1. e4');
    component.cor.set('PRETAS');
    component.partidaId.set('p1');
    component.resumo.set(resumoMock);
    component.estado.set('CONCLUIDO');

    component.novaAnalise();

    expect(component.pgn()).toBe('');
    expect(component.cor()).toBe('AUTO');
    expect(component.partidaId()).toBeNull();
    expect(component.resumo()).toBeNull();
    expect(component.estado()).toBe('INICIAL');
  });

  it('deve formatar o tempo em mm:ss', () => {
    expect(component.formatarTempo(0)).toBe('0:00');
    expect(component.formatarTempo(65)).toBe('1:05');
    expect(component.formatarTempo(120)).toBe('2:00');
  });

  it('deve formatar a tag com espaços e maiúsculas', () => {
    expect(component.formatarTag('perda_de_material')).toBe('PERDA DE MATERIAL');
  });

  it('deve carregar histórico de partidas recentes', async () => {
    vi.spyOn(revisaoService, 'listarPartidasRecentes').mockResolvedValue({
      success: true,
      partidas: [
        {
          partida_id: 'p-1',
          external_id: 'ext-1',
          status: 'concluido',
          cor_jogada: 'BRANCAS',
          jogadores: 'hirano28 vs adversario'
        }
      ]
    });

    await component.carregarHistorico();

    expect(component.historico().length).toBe(1);
    expect(component.historico()[0].partida_id).toBe('p-1');
    expect(component.historico()[0].jogadores).toBe('hirano28 vs adversario');
  });

  it('deve selecionar partida concluída do histórico e exibir resumo', async () => {
    vi.spyOn(revisaoService, 'consultarStatusPartida').mockResolvedValue({
      success: true,
      dados: {
        partida_id: 'p-pronta',
        status: 'concluido',
        resumo: resumoMock
      }
    });

    await component.selecionarPartidaDoHistorico('p-pronta');

    expect(component.partidaId()).toBe('p-pronta');
    expect(component.estado()).toBe('CONCLUIDO');
    expect(component.resumo()).toEqual(resumoMock);
    expect(localStorage.getItem('chess_analisador_partida_ativa')).toBe('p-pronta');
  });

  it('deve selecionar partida em processamento e iniciar polling', async () => {
    vi.spyOn(revisaoService, 'consultarStatusPartida').mockResolvedValue({
      success: true,
      dados: {
        partida_id: 'p-rodando',
        status: 'processando',
        resumo: null
      }
    });

    await component.selecionarPartidaDoHistorico('p-rodando');

    expect(component.partidaId()).toBe('p-rodando');
    expect(component.estado()).toBe('PROCESSANDO');
    expect(component.resumo()).toBeNull();
  });

  it('deve reprocessar partida atual com sucesso', async () => {
    component.partidaId.set('p-travada');
    vi.spyOn(revisaoService, 'reprocessarPartida').mockResolvedValue({
      success: true,
      partidaId: 'p-travada'
    });
    vi.spyOn(revisaoService, 'consultarStatusPartida').mockResolvedValue({
      success: true,
      dados: {
        partida_id: 'p-travada',
        status: 'processando',
        resumo: null
      }
    });

    await component.reprocessarPartidaAtual();

    expect(component.estado()).toBe('PROCESSANDO');
  });

  it('deve mapear o histórico para o formato genérico do componente compartilhado', async () => {
    vi.spyOn(revisaoService, 'listarPartidasRecentes').mockResolvedValue({
      success: true,
      partidas: [
        {
          partida_id: 'p-2',
          status: 'falhou',
          cor_jogada: 'PRETAS',
          eco_abertura: 'B90',
          resultado: 'DERROTA',
          jogadores: 'hirano28 vs adversario',
          created_at: '2026-09-10T01:58:29Z'
        }
      ]
    });

    await component.carregarHistorico();
    const itens = component.itensHistoricoComponent();

    expect(itens.length).toBe(1);
    expect(itens[0].id).toBe('p-2');
    expect(itens[0].titulo).toBe('hirano28 vs adversario');
    expect(itens[0].status).toBe('falhou');
    expect(itens[0].detalhes).toContain('Cor: Pretas ♚');
    expect(itens[0].detalhes).toContain('ECO: B90');
    expect(itens[0].detalhes).toContain('DERROTA');
  });
});


