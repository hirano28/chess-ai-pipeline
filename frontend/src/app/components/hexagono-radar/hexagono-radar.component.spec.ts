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
    expect(texto).toContain('Ainda não há uma análise das suas partidas');
    // D-65: importar virou o caminho principal e colar PGN a alternativa —
    // antes o estado vazio só oferecia o PGN, ou esperar dois crons.
    expect(texto).toContain('Importar minhas partidas');
    expect(texto).toContain('Colar um PGN');
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

describe('HexagonoRadarComponent — recorte por cadência (D-63)', () => {
  let component: HexagonoRadarComponent;
  let fixture: ComponentFixture<HexagonoRadarComponent>;
  let supabaseService: SupabaseService;
  let revisaoService: RevisaoAvulsaService;

  const semRecorte: AnaliseHexagonoMetricas = {
    total_diagnosticos: 60,
    gargalo_sistemico_atual: 'TATICA',
    frequencia_por_categoria: { TATICA: 40, CALCULO: 20 }
  };

  /** Mesmo cenário do teste do Agente 2: o gargalo muda entre as cadências. */
  const comRecorte: AnaliseHexagonoMetricas = {
    total_diagnosticos: 13,
    partidas_distintas: 7,
    gargalo_sistemico_atual: 'TATICA',
    frequencia_por_categoria: { TATICA: 7, FINAIS: 6 },
    por_cadencia: {
      BLITZ: {
        total_diagnosticos: 6,
        partidas_distintas: 3,
        gargalo_sistemico_atual: 'TATICA',
        frequencia_por_categoria: { TATICA: 6 }
      },
      RAPIDA: {
        total_diagnosticos: 6,
        partidas_distintas: 3,
        gargalo_sistemico_atual: 'FINAIS',
        frequencia_por_categoria: { FINAIS: 6 }
      }
    }
  };

  const composicaoBlitz: ComposicaoCadencia = {
    por_cadencia: { BLITZ: 180, RAPIDA: 68 },
    total: 248,
    dominante: 'BLITZ',
    percentual_dominante: 72.6
  };

  async function criar(
    analise: AnaliseHexagonoMetricas | null,
    composicao: ComposicaoCadencia = composicaoBlitz
  ): Promise<void> {
    vi.spyOn(supabaseService, 'getUltimaAnaliseHexagono').mockResolvedValue(analise);
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

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [HexagonoRadarComponent],
      providers: [provideHttpClient(), provideRouter([]), SupabaseService, TreinoService]
    }).compileComponents();

    supabaseService = TestBed.inject(SupabaseService);
    revisaoService = TestBed.inject(RevisaoAvulsaService);
    vi.spyOn(TestBed.inject(TreinoService), 'disponibilidadeFoco').mockResolvedValue({
      success: true,
      porCategoria: {}
    });
    /** jsdom não tem canvas: o Chart.js nasce degradado ("can't acquire
     * context") e explode no SEGUNDO render (`chart.update()` →
     * `ownerDocument` de null). Os testes anteriores nunca redesenhavam; os
     * deste bloco trocam o recorte e redesenham. O que se afirma aqui é a
     * lógica do componente e o DOM — não o desenho —, então o desenho sai. */
    vi.spyOn(
      HexagonoRadarComponent.prototype as unknown as { renderizarGrafico: () => void },
      'renderizarGrafico'
    ).mockImplementation(() => undefined);
  });

  it('análise antiga, sem por_cadencia, não ganha seletor nem atalho', async () => {
    /** As 5 análises gravadas antes do D-63 não têm o recorte. Um seletor com
     * um único "Todas" seria um botão que não faz nada. */
    await criar(semRecorte);

    expect(component.cadenciasDisponiveis()).toEqual([]);
    expect(component.podeRecortarDominante()).toBe(false);
    const seletor = (fixture.nativeElement as HTMLElement).querySelector(
      '[aria-label="Recorte por cadência"]'
    );
    expect(seletor).toBeNull();
    expect(texto()).not.toContain('Ver o Hexágono só de');
  });

  it('com recorte, lista as cadências da mais diagnosticada para a menos', async () => {
    await criar(comRecorte);

    expect(component.cadenciasDisponiveis().map((item) => item.cadencia)).toEqual([
      'BLITZ',
      'RAPIDA'
    ]);
    expect(texto()).toContain('Todas');
    expect(texto()).toContain('Rápida');
  });

  it('escolher uma cadência troca as métricas exibidas e a escala do rodapé', async () => {
    await criar(comRecorte);

    component.selecionarCadencia('RAPIDA');
    fixture.detectChanges();

    expect(component.metricasExibidas()?.gargalo_sistemico_atual).toBe('FINAIS');
    expect(component.gargaloExibido()).toBe('FINAIS');
    expect(texto()).toContain('6 diagnósticos');
    expect(texto()).toContain('em 3 partidas');
    expect(texto()).toContain('de Rápida');
  });

  it('"Todas" volta para o total', async () => {
    await criar(comRecorte);
    component.selecionarCadencia('RAPIDA');

    component.selecionarCadencia(null);
    fixture.detectChanges();

    expect(component.metricasExibidas()).toBe(comRecorte);
    expect(texto()).toContain('13 diagnósticos');
  });

  it('avisa quando o gargalo do recorte é outro que o do conjunto', async () => {
    /** É o achado que o recorte existe para expor — e o que a prescrição do
     * Agente 3, que segue o gargalo do conjunto, ainda não leva em conta. */
    await criar(comRecorte);

    component.selecionarCadencia('RAPIDA');
    fixture.detectChanges();

    expect(component.gargaloDivergeDoGeral()).toBe(true);
    const aviso = (fixture.nativeElement as HTMLElement).querySelector(
      '[data-testid="gargalo-diverge"]'
    );
    expect(aviso?.textContent).toContain('Em Rápida o gargalo é');
    expect(aviso?.textContent).toContain('Finais');
    expect(aviso?.textContent).toContain('Tática');
  });

  it('não avisa divergência quando o gargalo coincide, nem no total', async () => {
    await criar(comRecorte);

    expect(component.gargaloDivergeDoGeral()).toBe(false);

    component.selecionarCadencia('BLITZ');
    fixture.detectChanges();

    expect(component.gargaloDivergeDoGeral()).toBe(false);
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[data-testid="gargalo-diverge"]')
    ).toBeNull();
  });

  it('cadência sem bloco não vira seleção', async () => {
    /** Aceitar acenderia o chip errado sobre o hexágono do total. */
    await criar(comRecorte);

    component.selecionarCadencia('CLASSICA');

    expect(component.cadenciaSelecionada()).toBeNull();
    expect(component.metricasExibidas()).toBe(comRecorte);
  });

  it('a ressalva oferece ver só a cadência dominante, e o clique aplica o recorte', async () => {
    await criar(comRecorte);

    expect(component.podeRecortarDominante()).toBe(true);
    const botao = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button')
    ).find((b) => b.textContent?.includes('Ver o Hexágono só de Blitz'));
    expect(botao).toBeDefined();

    botao!.click();
    fixture.detectChanges();

    expect(component.cadenciaSelecionada()).toBe('BLITZ');
    // Já recortado na dominante, o atalho some — repetir seria ruído.
    expect(texto()).not.toContain('Ver o Hexágono só de Blitz');
  });

  it('sem análise nenhuma, o seletor e o rodapé de escala não aparecem', async () => {
    await criar(null);

    expect(component.cadenciasDisponiveis()).toEqual([]);
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[data-testid="escala-do-recorte"]')
    ).toBeNull();
  });
});

describe('HexagonoRadarComponent — importação sob demanda (D-65)', () => {
  let component: HexagonoRadarComponent;
  let fixture: ComponentFixture<HexagonoRadarComponent>;
  let revisaoService: RevisaoAvulsaService;

  async function criar(): Promise<void> {
    fixture = TestBed.createComponent(HexagonoRadarComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [HexagonoRadarComponent],
      providers: [provideHttpClient(), provideRouter([]), SupabaseService, TreinoService]
    }).compileComponents();

    revisaoService = TestBed.inject(RevisaoAvulsaService);
    vi.spyOn(TestBed.inject(TreinoService), 'disponibilidadeFoco').mockResolvedValue({
      success: true,
      porCategoria: {}
    });
    // Estado de usuário novo: nenhuma análise ainda.
    vi.spyOn(TestBed.inject(SupabaseService), 'getUltimaAnaliseHexagono').mockResolvedValue(null);
    vi.spyOn(revisaoService, 'obterComposicaoCadencia').mockResolvedValue({
      success: false
    });
    vi.spyOn(
      HexagonoRadarComponent.prototype as unknown as { renderizarGrafico: () => void },
      'renderizarGrafico'
    ).mockImplementation(() => undefined);
  });

  it('o estado vazio oferece importar, e colar PGN vira a alternativa', async () => {
    /** Antes do D-65 o único caminho era "Analisar minha primeira partida":
     * um usuário recém-cadastrado colava um PGN ou esperava até 7 dias pelos
     * dois crons. */
    await criar();

    expect(texto()).toContain('Importar minhas partidas');
    expect(texto()).toContain('Colar um PGN');
  });

  it('importar() mostra o detalhe que o backend devolveu', async () => {
    vi.spyOn(revisaoService, 'importarPartidas').mockResolvedValue({
      success: true,
      importacao: { iniciada: true, fontes: ['chesscom'], detalhe: 'Importação iniciada.' }
    });
    vi.spyOn(revisaoService, 'obterStatusImportacao').mockResolvedValue({
      success: true,
      status: {
        partidas: 10, pendentes: 8, processando: 1, concluidas: 1,
        diagnosticos: 3, tem_hexagono: false, em_andamento: true, pronto: false
      }
    });
    await criar();

    await component.importarPartidas();
    fixture.detectChanges();

    expect(component.avisoImportacao()?.texto).toBe('Importação iniciada.');
    expect(component.progressoImportacao()).toContain('1 prontas, 9 na fila');
  });

  it('falha ao importar explica em vez de ficar girando', async () => {
    vi.spyOn(revisaoService, 'importarPartidas').mockResolvedValue({
      success: false,
      error: 'Cadastre seu usuário do Lichess ou do Chess.com no Perfil antes de importar.'
    });
    await criar();

    await component.importarPartidas();
    fixture.detectChanges();

    expect(component.importando()).toBe(false);
    expect(component.avisoImportacao()?.tipo).toBe('erro');
    expect(texto()).toContain('no Perfil antes de importar');
  });

  it('terminar de processar sem Hexágono ainda conta como em andamento', async () => {
    /** "Pronto" é ter o que o usuário veio ver. Parar o acompanhamento aqui o
     * deixaria olhando o estado vazio achando que acabou. */
    vi.spyOn(revisaoService, 'importarPartidas').mockResolvedValue({
      success: true,
      importacao: { iniciada: true, fontes: ['chesscom'], detalhe: 'ok' }
    });
    vi.spyOn(revisaoService, 'obterStatusImportacao').mockResolvedValue({
      success: true,
      status: {
        partidas: 10, pendentes: 0, processando: 0, concluidas: 10,
        diagnosticos: 30, tem_hexagono: false, em_andamento: false, pronto: false
      }
    });
    await criar();

    await component.importarPartidas();

    expect(component.progressoImportacao()).toContain('Preparando o seu diagnóstico');
    expect(component.importando()).toBe(true);
  });

  it('durante a coleta nao afirma que as partidas ja foram analisadas', async () => {
    /** O status sai do dado sendo produzido, nao de uma tabela de job: enquanto
     * a coleta roda ainda nao existe partida pendente, entao `em_andamento` e
     * falso embora nada tenha terminado. Para um usuario NOVO — o alvo deste
     * recurso — esse e justamente o primeiro minuto. */
    vi.spyOn(revisaoService, 'importarPartidas').mockResolvedValue({
      success: true,
      importacao: { iniciada: true, fontes: ['chesscom'], detalhe: 'ok' }
    });
    vi.spyOn(revisaoService, 'obterStatusImportacao').mockResolvedValue({
      success: true,
      status: {
        partidas: 0, pendentes: 0, processando: 0, concluidas: 0,
        diagnosticos: 0, tem_hexagono: false, em_andamento: false, pronto: false
      }
    });
    await criar();

    await component.importarPartidas();

    expect(component.progressoImportacao()).toContain('Buscando suas partidas');
    expect(component.importando()).toBe(true);
  });

  it('quando fica pronto, recarrega a análise e para de acompanhar', async () => {
    const supabase = TestBed.inject(SupabaseService);
    vi.spyOn(revisaoService, 'importarPartidas').mockResolvedValue({
      success: true,
      importacao: { iniciada: true, fontes: ['chesscom'], detalhe: 'ok' }
    });
    vi.spyOn(revisaoService, 'obterStatusImportacao').mockResolvedValue({
      success: true,
      status: {
        partidas: 10, pendentes: 0, processando: 0, concluidas: 10,
        diagnosticos: 30, tem_hexagono: true, em_andamento: false, pronto: true
      }
    });
    await criar();
    const recarga = vi.spyOn(supabase, 'getUltimaAnaliseHexagono');
    recarga.mockClear();

    await component.importarPartidas();

    expect(component.importando()).toBe(false);
    expect(component.progressoImportacao()).toBeNull();
    // Sem esta recarga o usuário esperaria minutos e teria que dar F5.
    expect(recarga).toHaveBeenCalled();
  });
});
