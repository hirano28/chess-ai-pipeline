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
});

