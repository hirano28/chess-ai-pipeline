import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter, Router } from '@angular/router';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { HexagonoRadarComponent } from './hexagono-radar.component';
import { AnaliseHexagonoMetricas, SupabaseService } from '../../services/supabase.service';
import { TreinoService } from '../../services/treino.service';
import {
  ComposicaoCadencia,
  RevisaoAvulsaService
} from '../../services/revisao-avulsa.service';

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
    vi.spyOn(treinoService, 'focarCategoria').mockResolvedValue({ success: true, adicionados: 8 });
    vi.spyOn(treinoService, 'disponibilidadeFoco').mockResolvedValue({
      success: true,
      porCategoria: {
        TATICA: 300,
        CALCULO: 300,
        FINAIS: 300,
        ESTRUTURA_DE_PEOES: 300,
        ESTRATEGIA: 0,
        GESTAO_DE_TEMPO: 0
      }
    });
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

  it('categoria sem catálogo não navega e explica que não há material', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockResolvedValue(null);
    vi.spyOn(treinoService, 'focarCategoria').mockResolvedValue({
      success: true,
      adicionados: 0,
      motivo: 'sem_catalogo'
    });
    await criarComponente();

    await component.focar('GESTAO_DE_TEMPO');

    // Navegar aqui jogaria o usuário numa fila que não mudou, sem explicação.
    expect(router.navigateByUrl).not.toHaveBeenCalled();
    expect(component.avisoFoco()?.texto).toContain('Ainda não há exercícios de catálogo');
    expect(component.avisoFoco()?.texto).toContain('Gestão de Tempo');
  });

  it('fila já completa diz que não há nada novo, em vez de "não temos material"', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockResolvedValue(null);
    vi.spyOn(treinoService, 'focarCategoria').mockResolvedValue({
      success: true,
      adicionados: 0,
      motivo: 'ja_na_fila'
    });
    await criarComponente();

    await component.focar('TATICA');

    expect(router.navigateByUrl).not.toHaveBeenCalled();
    expect(component.avisoFoco()?.texto).toContain('já tem todos os exercícios');
  });

  it('falha ao focar mostra o erro e não navega', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockResolvedValue(null);
    vi.spyOn(treinoService, 'focarCategoria').mockResolvedValue({
      success: false,
      error: 'Sua sessão expirou.'
    });
    await criarComponente();

    await component.focar('TATICA');

    expect(router.navigateByUrl).not.toHaveBeenCalled();
    expect(component.avisoFoco()).toEqual({ texto: 'Sua sessão expirou.', tipo: 'erro' });
    expect(component.focandoCategoria()).toBeNull();
  });

  it('não oferece "Focar" nas categorias sem catálogo, e explica a alternativa', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockResolvedValue(null);
    await criarComponente();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Focar em Tática');
    expect(texto).not.toContain('Focar em Estratégia');
    expect(texto).not.toContain('Focar em Gestão de Tempo');
    // A ausência precisa ser explicada, senão vira "sumiu sem motivo".
    expect(texto).toContain('Sem exercícios de catálogo para');
    expect(texto).toContain('Treino Diário');
    expect(component.categoriasSemCatalogo()).toEqual(['ESTRATEGIA', 'GESTAO_DE_TEMPO']);
  });

  it('se a consulta de disponibilidade falhar, nenhum botão é escondido', async () => {
    // Supor "não tem material" sem saber seria pior que deixar tentar.
    vi.spyOn(treinoService, 'disponibilidadeFoco').mockResolvedValue({
      success: false,
      error: 'fora do ar'
    });
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockResolvedValue(null);
    await criarComponente();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Focar em Estratégia');
    expect(component.semCatalogo('ESTRATEGIA')).toBe(false);
    expect(component.categoriasSemCatalogo()).toEqual([]);
  });

  it('sucesso informa quantos exercícios entraram na fila', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockResolvedValue(null);
    await criarComponente();

    await component.focar('TATICA');

    expect(component.avisoFoco()?.texto).toBe('8 exercícios de Tática na fila de hoje.');
    expect(router.navigateByUrl).toHaveBeenCalledWith('/treino');
  });
});

describe('HexagonoRadarComponent — ressalva de cadência (D-57)', () => {
  let component: HexagonoRadarComponent;
  let fixture: ComponentFixture<HexagonoRadarComponent>;
  let revisaoService: RevisaoAvulsaService;

  async function criar(composicao: ComposicaoCadencia): Promise<void> {
    vi.spyOn(revisaoService, 'obterComposicaoCadencia').mockResolvedValue({
      success: true,
      composicao
    });
    fixture = TestBed.createComponent(HexagonoRadarComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [HexagonoRadarComponent],
      providers: [provideHttpClient(), provideRouter([]), SupabaseService, TreinoService]
    }).compileComponents();

    revisaoService = TestBed.inject(RevisaoAvulsaService);
    const treinoService = TestBed.inject(TreinoService);
    vi.spyOn(treinoService, 'disponibilidadeFoco').mockResolvedValue({
      success: true,
      porCategoria: {}
    });
    vi.spyOn(TestBed.inject(SupabaseService), 'getUltimaAnaliseHexagono').mockResolvedValue(
      null
    );
  });

  it('avisa quando uma cadência domina o corpus', async () => {
    /** Sem esta ressalva o produto venderia um diagnóstico mais firme do que
     * ele é: erro sob pressão de relógio tem a mesma cara de erro de
     * entendimento no radar. */
    await criar({
      por_cadencia: { BLITZ: 142, RAPIDA: 30, DESCONHECIDA: 68 },
      total: 240,
      dominante: 'BLITZ',
      percentual_dominante: 59.2
    });

    expect(component.cadenciaDominaOCorpus()).toBe(true);
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('59,2% das 240 partidas analisadas são Blitz');
    expect(component.percentualDominanteFormatado()).toBe('59,2');
    expect(texto).toContain('efeito do relógio');
  });

  it('cala a boca quando o corpus é equilibrado', async () => {
    await criar({
      por_cadencia: { BLITZ: 30, RAPIDA: 40, CLASSICA: 30 },
      total: 100,
      dominante: 'RAPIDA',
      percentual_dominante: 40
    });

    expect(component.cadenciaDominaOCorpus()).toBe(false);
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).not.toContain('efeito do relógio');
  });

  it('ordena as cadências da mais frequente para a menos', async () => {
    await criar({
      por_cadencia: { BLITZ: 142, RAPIDA: 30, DESCONHECIDA: 68 },
      total: 240,
      dominante: 'BLITZ',
      percentual_dominante: 59.2
    });

    expect(component.cadenciasOrdenadas().map((item) => item.cadencia)).toEqual([
      'BLITZ',
      'DESCONHECIDA',
      'RAPIDA'
    ]);
  });

  it('sem partidas analisadas não mostra ressalva nenhuma', async () => {
    await criar({ por_cadencia: {}, total: 0, dominante: null, percentual_dominante: 0 });

    expect(component.cadenciaDominaOCorpus()).toBe(false);
  });
});
