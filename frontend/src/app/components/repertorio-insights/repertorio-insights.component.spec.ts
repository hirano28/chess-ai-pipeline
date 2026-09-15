import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { RepertorioInsightsComponent } from './repertorio-insights.component';
import {
  InsightsRepertorio,
  RepertorioService
} from '../../services/repertorio.service';

describe('RepertorioInsightsComponent', () => {
  let component: RepertorioInsightsComponent;
  let fixture: ComponentFixture<RepertorioInsightsComponent>;
  let repertorioService: RepertorioService;

  const mockInsights: InsightsRepertorio = {
    taxa_vitoria_por_cor: {
      BRANCAS: { total: 20, vitorias: 12, taxa_vitoria_pct: 60.0 },
      PRETAS: { total: 20, vitorias: 8, taxa_vitoria_pct: 40.0 }
    },
    por_abertura_e_cor: [
      {
        abertura_normalizada: 'Francesa',
        cor_jogada: 'PRETAS',
        total: 15,
        vitorias: 9,
        taxa_vitoria_pct: 60.0
      },
      {
        abertura_normalizada: 'Sistema Londres',
        cor_jogada: 'BRANCAS',
        total: 10,
        vitorias: 7,
        taxa_vitoria_pct: 70.0
      }
    ],
    lance_pico_por_abertura: [
      {
        abertura_normalizada: 'Francesa',
        total_eventos: 15,
        lance_medio: 14.2,
        lance_mediano: 14
      }
    ],
    categorias_por_abertura: {
      Francesa: {
        TATICA: 10,
        ESTRATEGIA: 4,
        FINAIS: 1,
        CALCULO: 0
      }
    }
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RepertorioInsightsComponent],
      providers: [provideHttpClient(), RepertorioService]
    }).compileComponents();

    repertorioService = TestBed.inject(RepertorioService);
    vi.spyOn(repertorioService, 'getInsightsRepertorio').mockResolvedValue({
      success: true,
      dados: mockInsights
    });

    fixture = TestBed.createComponent(RepertorioInsightsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('deve ser criado com sucesso', () => {
    expect(component).toBeTruthy();
  });

  it('deve carregar e computar métricas na inicialização', () => {
    expect(component.loading()).toBe(false);
    expect(component.error()).toBeNull();
    expect(component.taxaBrancas()?.taxa_vitoria_pct).toBe(60.0);
    expect(component.taxaPretas()?.taxa_vitoria_pct).toBe(40.0);
    expect(component.aberturasFiltradas().length).toBe(2);
  });

  it('deve filtrar aberturas por cor', () => {
    component.selecionarFiltro('BRANCAS');
    expect(component.filtroCor()).toBe('BRANCAS');
    expect(component.aberturasFiltradas().length).toBe(1);
    expect(component.aberturasFiltradas()[0].abertura_normalizada).toBe(
      'Sistema Londres'
    );

    component.selecionarFiltro('PRETAS');
    expect(component.filtroCor()).toBe('PRETAS');
    expect(component.aberturasFiltradas().length).toBe(1);
    expect(component.aberturasFiltradas()[0].abertura_normalizada).toBe(
      'Francesa'
    );

    component.selecionarFiltro('TODAS');
    expect(component.aberturasFiltradas().length).toBe(2);
  });

  it('obterMomentoCritico retorna string formatada ou null', () => {
    expect(component.obterMomentoCritico('Francesa')).toBe('Lance médio: 14.2');
    expect(component.obterMomentoCritico('Inexistente')).toBeNull();
  });

  it('obterTopCategorias retorna categorias ordenadas e limitadas a 3', () => {
    const top = component.obterTopCategorias('Francesa');
    expect(top.length).toBe(3);
    expect(top[0]).toEqual({ categoria: 'TATICA', contagem: 10 });
    expect(top[1]).toEqual({ categoria: 'ESTRATEGIA', contagem: 4 });
    expect(top[2]).toEqual({ categoria: 'FINAIS', contagem: 1 });
  });

  it('deve exibir mensagem de erro se a busca falhar', async () => {
    vi.spyOn(repertorioService, 'getInsightsRepertorio').mockResolvedValue({
      success: false,
      error: 'Erro no servidor'
    });

    await component.carregarInsights();

    expect(component.loading()).toBe(false);
    expect(component.error()).toBe('Erro no servidor');
  });

  it('corBarraProgresso retorna classes corretas conforme taxa', () => {
    expect(component.corBarraProgresso(60)).toBe('bg-sucesso');
    expect(component.corBarraProgresso(45)).toBe('bg-latao-500');
    expect(component.corBarraProgresso(30)).toBe('bg-perigo');
  });

  it('corBadgeTaxa retorna a variante de selo conforme taxa', () => {
    expect(component.corBadgeTaxa(60)).toBe('selo-sucesso');
    expect(component.corBadgeTaxa(45)).toBe('selo-latao');
    expect(component.corBadgeTaxa(30)).toBe('selo-perigo');
  });
});

