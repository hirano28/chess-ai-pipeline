import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { PuzzlesInsightsComponent } from './puzzles-insights.component';
import {
  InsightsPuzzles,
  PuzzlesService
} from '../../services/puzzles.service';

describe('PuzzlesInsightsComponent', () => {
  let component: PuzzlesInsightsComponent;
  let fixture: ComponentFixture<PuzzlesInsightsComponent>;
  let puzzlesService: PuzzlesService;

  const mockInsights: InsightsPuzzles = {
    resumo: {
      total: 660,
      acertos: 464,
      erros: 196,
      taxa_acerto_pct: 70.3,
      rating_medio: 1853.7,
      rating_min: 424,
      rating_max: 2790
    },
    temas_vulneraveis: [
      {
        slug: 'defensiveMove',
        nome: 'Lance Defensivo',
        descricao: 'Defesa salvadora.',
        categoria: 'defesa',
        total: 31,
        acertos: 14,
        taxa_acerto_pct: 45.2,
        url_treino: 'https://lichess.org/training/defensiveMove'
      },
      {
        slug: 'deflection',
        nome: 'Desvio',
        descricao: 'Desviar peça chave.',
        categoria: 'tatica',
        total: 33,
        acertos: 16,
        taxa_acerto_pct: 48.5,
        url_treino: 'https://lichess.org/training/deflection'
      }
    ],
    temas_dominados: [
      {
        slug: 'mateIn1',
        nome: 'Mate em 1 lance',
        descricao: 'Rede de mate.',
        categoria: 'mate',
        total: 193,
        acertos: 181,
        taxa_acerto_pct: 93.8,
        url_treino: 'https://lichess.org/training/mateIn1'
      }
    ],
    todos_os_temas: [],
    diagnostico_gap: {
      titulo: 'Gap Tático: Visão Ofensiva vs Defesa Sob Pressão',
      resumo_executivo: 'Rating médio 1854 nos puzzles...',
      analise_comparativa: 'Ataque forte, defesa fraca...',
      sugestao_foco: 'Treinar defesa...'
    }
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PuzzlesInsightsComponent],
      providers: [provideHttpClient(), PuzzlesService]
    }).compileComponents();

    puzzlesService = TestBed.inject(PuzzlesService);
    vi.spyOn(puzzlesService, 'getInsightsPuzzles').mockResolvedValue({
      success: true,
      dados: mockInsights
    });

    fixture = TestBed.createComponent(PuzzlesInsightsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('deve ser criado com sucesso', () => {
    expect(component).toBeTruthy();
  });

  it('deve carregar e computar métricas na inicialização', () => {
    expect(component.loading()).toBe(false);
    expect(component.error()).toBeNull();
    expect(component.resumo()?.total).toBe(660);
    expect(component.resumo()?.rating_medio).toBe(1853.7);
    expect(component.temasVulneraveis().length).toBe(2);
    expect(component.temasDominados().length).toBe(1);
    expect(component.diagnosticoGap()?.titulo).toContain('Gap Tático');
  });

  it('deve renderizar links de treino do Lichess nos temas vulneráveis', () => {
    const el = fixture.nativeElement as HTMLElement;
    const links = el.querySelectorAll('a[href^="https://lichess.org/training/"]');
    expect(links.length).toBe(2);
    expect(links[0].getAttribute('href')).toBe('https://lichess.org/training/defensiveMove');
    expect(links[1].getAttribute('href')).toBe('https://lichess.org/training/deflection');
  });

  it('deve exibir mensagem de erro se o serviço falhar', async () => {
    vi.spyOn(puzzlesService, 'getInsightsPuzzles').mockResolvedValue({
      success: false,
      error: 'Falha na conexão'
    });

    await component.carregarInsights();

    expect(component.loading()).toBe(false);
    expect(component.error()).toBe('Falha na conexão');
  });

  it('corBarraProgresso e corBadgeTaxa retornam classes corretas conforme taxa', () => {
    expect(component.corBarraProgresso(80)).toBe('bg-sucesso');
    expect(component.corBarraProgresso(60)).toBe('bg-latao-500');
    expect(component.corBarraProgresso(40)).toBe('bg-perigo');

    expect(component.corBadgeTaxa(80)).toBe('selo-sucesso');
    expect(component.corBadgeTaxa(60)).toBe('selo-latao');
    expect(component.corBadgeTaxa(40)).toBe('selo-perigo');
  });

  it('badgeCategoria retorna classes adequadas por tipo', () => {
    expect(component.badgeCategoria('defesa')).toBe('selo-perigo');
    expect(component.badgeCategoria('ataque')).toBe('selo-latao');
    expect(component.badgeCategoria('tatica')).toBe('selo-info');
    expect(component.badgeCategoria('final')).toBe('selo-roxo');
    expect(component.badgeCategoria('mate')).toBe('selo-sucesso');
    expect(component.badgeCategoria('outro')).toBe('selo-neutro');
  });
});
