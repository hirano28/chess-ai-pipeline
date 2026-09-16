import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter, Router } from '@angular/router';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { HexagonoRadarComponent } from './hexagono-radar.component';
import { AnaliseHexagonoMetricas, SupabaseService } from '../../services/supabase.service';
import { TreinoService } from '../../services/treino.service';

describe('HexagonoRadarComponent', () => {
  let component: HexagonoRadarComponent;
  let fixture: ComponentFixture<HexagonoRadarComponent>;
  let supabaseService: SupabaseService;
  let treinoService: TreinoService;
  let router: Router;

  const mockAnalise: AnaliseHexagonoMetricas = {
    frequencia_por_categoria: {
      TATICA: 40,
      ESTRATEGIA: 10,
      FINAIS: 5,
      ESTRUTURA_DE_PEOES: 0,
      GESTAO_DE_TEMPO: 0,
      CALCULO: 20
    }
  } as AnaliseHexagonoMetricas;

  async function criarComponente(): Promise<void> {
    fixture = TestBed.createComponent(HexagonoRadarComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HexagonoRadarComponent],
      providers: [provideHttpClient(), provideRouter([]), SupabaseService, TreinoService]
    }).compileComponents();

    supabaseService = TestBed.inject(SupabaseService);
    treinoService = TestBed.inject(TreinoService);
    router = TestBed.inject(Router);
    vi.spyOn(treinoService, 'focarCategoria').mockResolvedValue({ success: true, adicionados: 0 });
    vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
  });

  it('deve exibir o estado vazio (não um erro) quando ainda não há análise', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockResolvedValue(null);
    await criarComponente();

    expect(component.semAnalise()).toBe(true);
    expect(component.error()).toBeNull();
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Ainda não há uma análise de partidas disponível');
    expect(texto).toContain('Analisar minha primeira partida');
  });

  it('deve exibir uma mensagem de erro quando a busca falha de verdade', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockRejectedValue(new Error('fora do ar'));
    await criarComponente();

    expect(component.error()).toContain('fora do ar');
    expect(component.semAnalise()).toBe(false);
  });

  it('deve carregar a análise com sucesso', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockResolvedValue(mockAnalise);
    await criarComponente();

    expect(component.loading()).toBe(false);
    expect(component.dados()).toEqual(mockAnalise);
    expect(component.semAnalise()).toBe(false);
  });

  it('selecionarModo troca entre "erros" e "forcas"', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockResolvedValue(null);
    await criarComponente();

    expect(component.modoVisualizacao()).toBe('erros');
    component.selecionarModo('forcas');
    expect(component.modoVisualizacao()).toBe('forcas');
  });

  it('focar() chama focarCategoria() e navega para /treino', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockResolvedValue(null);
    await criarComponente();

    await component.focar('TATICA');

    expect(treinoService.focarCategoria).toHaveBeenCalledWith('TATICA');
    expect(router.navigateByUrl).toHaveBeenCalledWith('/treino');
    expect(component.focandoCategoria()).toBeNull();
  });

  it('focar() ignora cliques repetidos enquanto uma chamada está em andamento', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockResolvedValue(null);
    await criarComponente();

    const primeira = component.focar('TATICA');
    const segunda = component.focar('CALCULO');
    await Promise.all([primeira, segunda]);

    expect(treinoService.focarCategoria).toHaveBeenCalledTimes(1);
    expect(treinoService.focarCategoria).toHaveBeenCalledWith('TATICA');
  });
});
