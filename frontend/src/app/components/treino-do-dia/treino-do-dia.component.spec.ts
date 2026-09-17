import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { TreinoDoDiaComponent } from './treino-do-dia.component';
import { FilaTreino, ResultadoTrecho, ResultadoTreino, TreinoService } from '../../services/treino.service';

describe('TreinoDoDiaComponent', () => {
  let component: TreinoDoDiaComponent;
  let fixture: ComponentFixture<TreinoDoDiaComponent>;
  let treinoService: TreinoService;

  const item1 = {
    fila_id: 7,
    fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    origem: 'lance_critico' as const,
    tipo_evento: 'PICO' as const,
    numero_lance_fim: null,
    trecho: null,
    numero_lance: 14,
    cor_jogada: 'BRANCAS' as const,
    data_partida: '2026-09-10',
    plataforma: 'LICHESS',
    categoria: null,
    segundos_sugeridos: null,
    repeticoes: 0,
    total_revisoes: 0
  };

  const item2 = { ...item1, fila_id: 8, numero_lance: 20 };

  const mockFila: FilaTreino = { itens: [item1, item2], feitas_hoje: 1, total_hoje: 3, vencidos_total: 1, sessao_id: null };

  const mockResultado: ResultadoTreino = {
    qualidade_lance: 'BOM',
    lance_interpretado: 'e4',
    melhor_lance: 'e4',
    queda_win_percent: 0.5,
    raiz_conceitual_violada: 'Não avaliou o centro.',
    tags_falha: ['calculo_tatico_deficiente'],
    livro_citado: 'Meu Sistema',
    capitulo_citado: '4',
    pagina_citada: 88,
    partida_referencia: null,
    partida_url: null,
    fora_do_tempo: false,
    proxima_revisao_data: '2026-09-17',
    repeticoes: 1
  };

  async function criarComponente(): Promise<void> {
    fixture = TestBed.createComponent(TreinoDoDiaComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TreinoDoDiaComponent],
      providers: [provideHttpClient(), provideRouter([]), TreinoService]
    }).compileComponents();

    treinoService = TestBed.inject(TreinoService);
  });

  it('deve ser criado com sucesso', async () => {
    vi.spyOn(treinoService, 'getFila').mockResolvedValue({ success: true, fila: mockFila });
    await criarComponente();
    expect(component).toBeTruthy();
  });

  it('deve carregar a fila na inicialização', async () => {
    vi.spyOn(treinoService, 'getFila').mockResolvedValue({ success: true, fila: mockFila });
    await criarComponente();

    expect(component.carregando()).toBe(false);
    expect(component.fila().length).toBe(2);
    expect(component.feitasHoje()).toBe(1);
    expect(component.totalHoje()).toBe(3);
    expect(component.itemAtual()?.fila_id).toBe(7);
  });

  it('deve exibir o estado vazio quando não há nada pendente', async () => {
    vi.spyOn(treinoService, 'getFila').mockResolvedValue({
      success: true,
      fila: { itens: [], feitas_hoje: 3, total_hoje: 3, vencidos_total: 1, sessao_id: null }
    });
    await criarComponente();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Nenhuma revisão pendente hoje');
  });

  it('deve exibir erro quando o serviço falha ao carregar', async () => {
    vi.spyOn(treinoService, 'getFila').mockResolvedValue({
      success: false,
      error: 'Falha na conexão'
    });
    await criarComponente();

    expect(component.erro()).toBe('Falha na conexão');
  });

  it('não deve responder com o campo de lance vazio', async () => {
    vi.spyOn(treinoService, 'getFila').mockResolvedValue({ success: true, fila: mockFila });
    await criarComponente();
    const responderSpy = vi.spyOn(treinoService, 'responder');

    await component.responder();

    expect(responderSpy).not.toHaveBeenCalled();
  });

  it('deve responder e revelar o resultado sem avançar automaticamente', async () => {
    vi.spyOn(treinoService, 'getFila').mockResolvedValue({ success: true, fila: mockFila });
    await criarComponente();
    vi.spyOn(treinoService, 'responder').mockResolvedValue({
      success: true,
      resultado: mockResultado
    });

    component.lance.set('e4');
    await component.responder();

    expect(component.resultado()).toEqual(mockResultado);
    expect(component.enviando()).toBe(false);
    // Ainda é o mesmo item: só 'próxima' avança a fila.
    expect(component.itemAtual()?.fila_id).toBe(7);
  });

  it('deve exibir o erro do backend quando o lance é inválido', async () => {
    vi.spyOn(treinoService, 'getFila').mockResolvedValue({ success: true, fila: mockFila });
    await criarComponente();
    vi.spyOn(treinoService, 'responder').mockResolvedValue({
      success: false,
      error: 'Lance inválido: Txz9.'
    });

    component.lance.set('Txz9');
    await component.responder();

    expect(component.erro()).toBe('Lance inválido: Txz9.');
    expect(component.resultado()).toBeNull();
  });

  it('proxima() avança pro próximo card e soma feitasHoje', async () => {
    vi.spyOn(treinoService, 'getFila').mockResolvedValue({ success: true, fila: mockFila });
    await criarComponente();
    component.resultado.set(mockResultado);

    component.proxima();

    expect(component.itemAtual()?.fila_id).toBe(8);
    expect(component.feitasHoje()).toBe(2);
    expect(component.resultado()).toBeNull();
    expect(component.lance()).toBe('');
  });

  it('corBadgeQualidadeLance mapeia BOM/SUBOTIMO/RUIM para os selos', async () => {
    vi.spyOn(treinoService, 'getFila').mockResolvedValue({ success: true, fila: mockFila });
    await criarComponente();

    expect(component.corBadgeQualidadeLance('BOM')).toBe('selo-sucesso');
    expect(component.corBadgeQualidadeLance('SUBOTIMO')).toBe('selo-latao');
    expect(component.corBadgeQualidadeLance('RUIM')).toBe('selo-perigo');
  });

  it('exibe o selo de "Exercício" com a categoria para cards de catálogo (D-49)', async () => {
    const itemExercicio = {
      ...item1,
      fila_id: 9,
      origem: 'exercicio_tatico' as const,
      numero_lance: null,
      categoria: 'TATICA'
    };
    vi.spyOn(treinoService, 'getFila').mockResolvedValue({
      success: true,
      fila: { itens: [itemExercicio], feitas_hoje: 0, total_hoje: 1, vencidos_total: 1, sessao_id: null }
    });
    await criarComponente();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Exercício · Tática');
  });

  it('rotuloCategoria mapeia a categoria pro nome amigável, com fallback', async () => {
    vi.spyOn(treinoService, 'getFila').mockResolvedValue({ success: true, fila: mockFila });
    await criarComponente();

    expect(component.rotuloCategoria('CALCULO')).toBe('Cálculo');
    expect(component.rotuloCategoria(null)).toBe('Exercício de catálogo');
  });

  describe('fila com teto e filtro de sessão (D-56)', () => {
    it('diz quantos cards ficaram de fora do teto', async () => {
      /** O teto corta o que a tela mostra, nunca o que o SM-2 agendou —
       * omitir o tamanho do atraso seria mentir por omissão. */
      vi.spyOn(treinoService, 'getFila').mockResolvedValue({
        success: true,
        fila: {
          itens: [item1, item2],
          feitas_hoje: 0,
          total_hoje: 47,
          vencidos_total: 47,
          sessao_id: null
        }
      });
      await criarComponente();

      expect(component.ocultosPeloTeto()).toBe(45);
      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(texto).toContain('Mostrando 2 de 47');
    });

    it('não incomoda com o aviso de teto quando tudo cabe', async () => {
      vi.spyOn(treinoService, 'getFila').mockResolvedValue({
        success: true,
        fila: {
          itens: [item1, item2],
          feitas_hoje: 0,
          total_hoje: 2,
          vencidos_total: 2,
          sessao_id: null
        }
      });
      await criarComponente();

      expect(component.ocultosPeloTeto()).toBe(0);
      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(texto).not.toContain('Mostrando');
    });

    it('sem parâmetro de sessão, pede a fila inteira', async () => {
      const getFila = vi
        .spyOn(treinoService, 'getFila')
        .mockResolvedValue({ success: true, fila: mockFila });
      await criarComponente();

      expect(getFila).toHaveBeenCalledWith(null);
      expect(component.sessaoId()).toBeNull();
    });
  });

  describe('exercício posicional cronometrado (D-55)', () => {
    const itemCronometrado = {
      ...item1,
      fila_id: 42,
      origem: 'exercicio_posicional' as const,
      numero_lance: null,
      cor_jogada: null,
      categoria: 'GESTAO_DE_TEMPO',
      segundos_sugeridos: 65
    };

    async function comCardCronometrado(): Promise<void> {
      vi.spyOn(treinoService, 'getFila').mockResolvedValue({
        success: true,
        fila: { itens: [itemCronometrado], feitas_hoje: 0, total_hoje: 1, vencidos_total: 1, sessao_id: null }
      });
      await criarComponente();
    }

    it('mostra o relógio do jogador original antes de responder', async () => {
      await comCardCronometrado();

      expect(component.segundosRestantes()).toBe(65);
      expect(component.tempoEsgotado()).toBe(false);
      const relogio = fixture.nativeElement.querySelector('[role="timer"]') as HTMLElement;
      expect(relogio).not.toBeNull();
      expect(relogio.textContent).toContain('1:05');
    });

    it('card sem relógio não mostra cronômetro nenhum', async () => {
      vi.spyOn(treinoService, 'getFila').mockResolvedValue({ success: true, fila: mockFila });
      await criarComponente();

      expect(component.segundosRestantes()).toBeNull();
      expect(fixture.nativeElement.querySelector('[role="timer"]')).toBeNull();
    });

    it('envia os segundos gastos junto com o lance', async () => {
      /** Sem isso o backend não teria como rebaixar o agendamento, e o
       * cronômetro viraria enfeite numa categoria cuja falha medida É o
       * tempo. */
      await comCardCronometrado();
      const responder = vi
        .spyOn(treinoService, 'responder')
        .mockResolvedValue({ success: true, resultado: mockResultado });

      component.lance.set('Rd7');
      await component.responder();

      expect(responder).toHaveBeenCalledWith(42, 'Rd7', expect.any(Number));
    });

    it('card sem relógio envia null em vez de um número inventado', async () => {
      vi.spyOn(treinoService, 'getFila').mockResolvedValue({ success: true, fila: mockFila });
      await criarComponente();
      const responder = vi
        .spyOn(treinoService, 'responder')
        .mockResolvedValue({ success: true, resultado: mockResultado });

      component.lance.set('e4');
      await component.responder();

      expect(responder).toHaveBeenCalledWith(7, 'e4', null);
    });

    it('formatarRelogio usa o formato do relógio de xadrez', () => {
      fixture = TestBed.createComponent(TreinoDoDiaComponent);
      component = fixture.componentInstance;

      expect(component.formatarRelogio(65)).toBe('1:05');
      expect(component.formatarRelogio(9)).toBe('0:09');
      expect(component.formatarRelogio(0)).toBe('0:00');
    });

    it('revela a partida de origem só depois de responder', async () => {
      await comCardCronometrado();
      vi.spyOn(treinoService, 'responder').mockResolvedValue({
        success: true,
        resultado: {
          ...mockResultado,
          partida_referencia: 'GM Moranda, Wojciech × CM Klepek, Witold — Anderssen (2026)',
          partida_url: 'https://lichess.org/broadcast/x/y/z'
        }
      });

      // Antes de responder, nada de procedência na tela.
      let texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(texto).not.toContain('Moranda');

      component.lance.set('Rd7');
      await component.responder();
      fixture.detectChanges();

      texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(texto).toContain('GM Moranda, Wojciech');
      expect(texto).toContain('Ver a partida no Lichess');
    });

    it('avisa quando a resposta saiu fora do tempo', async () => {
      await comCardCronometrado();
      vi.spyOn(treinoService, 'responder').mockResolvedValue({
        success: true,
        resultado: { ...mockResultado, fora_do_tempo: true }
      });

      component.lance.set('Rd7');
      await component.responder();
      fixture.detectChanges();

      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(texto).toContain('fora do tempo');
      // O julgamento do lance continua sendo o do motor: são dois fatos.
      expect(texto).toContain('BOM');
    });
  });
});

describe('TreinoDoDiaComponent com ?sessao= (D-56)', () => {
  const SESSAO = 'sessao-abc';
  let treinoService: TreinoService;

  beforeEach(async () => {
    TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [TreinoDoDiaComponent],
      providers: [
        provideHttpClient(),
        provideRouter([]),
        TreinoService,
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: { queryParamMap: convertToParamMap({ sessao: SESSAO }) }
          }
        }
      ]
    }).compileComponents();
    treinoService = TestBed.inject(TreinoService);
  });

  it('pede só os exercícios da sessão e avisa que a fila está filtrada', async () => {
    const getFila = vi.spyOn(treinoService, 'getFila').mockResolvedValue({
      success: true,
      fila: { itens: [], feitas_hoje: 0, total_hoje: 0, vencidos_total: 0, sessao_id: SESSAO }
    });

    const fixture = TestBed.createComponent(TreinoDoDiaComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(getFila).toHaveBeenCalledWith(SESSAO);
    expect(fixture.componentInstance.sessaoId()).toBe(SESSAO);
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    // Sem este aviso a tela pareceria o Treino Diário normal com
    // misteriosamente menos cards.
    expect(texto).toContain('sessão de treino focado');
    expect(texto).toContain('Ver a fila completa');
  });
});

describe('TreinoDoDiaComponent — refazer o trecho (D-66)', () => {
  let treinoService: TreinoService;

  const cardDeTrecho = {
    fila_id: 21,
    fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    origem: 'lance_critico' as const,
    tipo_evento: 'EROSAO' as const,
    numero_lance: 12,
    numero_lance_fim: 19,
    trecho: { total_lances: 8, lances_feitos: 0, historico: [] },
    cor_jogada: 'BRANCAS',
    data_partida: '2026-09-10',
    plataforma: 'LICHESS',
    categoria: null,
    segundos_sugeridos: null,
    repeticoes: 0,
    total_revisoes: 0
  };

  function passo(extras: Partial<ResultadoTrecho> = {}): ResultadoTrecho {
    return {
      lance_interpretado: 'Cf3',
      lance_oponente: 'Bc5',
      fen: 'rnbqkbnr/pppp1ppp/8/4p3/8/5N2/PPPPPPPP/RNBQKB1R b KQkq - 1 2',
      lances_feitos: 1,
      total_lances: 8,
      historico: ['Cf3', 'Bc5'],
      concluido: false,
      fim_de_partida: false,
      qualidade_lance: null,
      queda_liquida: null,
      queda_original: null,
      resumo: null,
      curva: [],
      raiz_conceitual_violada: null,
      tags_falha: [],
      livro_citado: null,
      capitulo_citado: null,
      pagina_citada: null,
      proxima_revisao_data: null,
      repeticoes: null,
      ...extras
    };
  }

  async function montar(): Promise<ComponentFixture<TreinoDoDiaComponent>> {
    const fixture = TestBed.createComponent(TreinoDoDiaComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TreinoDoDiaComponent],
      providers: [provideHttpClient(), provideRouter([]), TreinoService]
    }).compileComponents();
    treinoService = TestBed.inject(TreinoService);
    vi.spyOn(treinoService, 'getFila').mockResolvedValue({
      success: true,
      fila: {
        itens: [cardDeTrecho],
        feitas_hoje: 0,
        total_hoje: 1,
        vencidos_total: 1,
        sessao_id: null
      }
    });
  });

  it('mostra a janela, o progresso e explica por que o formato é outro', async () => {
    const fixture = await montar();
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';

    expect(texto).toContain('Lances 12 a 19');
    expect(texto).toContain('Lance 1 de 8');
    expect(texto).toContain('escorregou');
  });

  it('não mostra avaliação nenhuma no meio do trecho', async () => {
    // O ponto do formato: erosão é o que se perde sem perceber. Um "-4%" a
    // cada lance viraria oito exercícios táticos com placar.
    vi.spyOn(treinoService, 'jogarTrecho').mockResolvedValue({
      success: true,
      resultado: passo()
    });
    const fixture = await montar();
    fixture.componentInstance.lance.set('Cf3');

    await fixture.componentInstance.jogarLanceDoTrecho();
    fixture.detectChanges();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('O adversário respondeu');
    expect(texto).toContain('Bc5');
    expect(texto).toContain('Lance 2 de 8');
    expect(texto).not.toContain('Queda neste treino');
    expect(texto).not.toContain('O que cada lance custou');
  });

  it('usa a rota de trecho, não a de lance único', async () => {
    const jogarTrecho = vi.spyOn(treinoService, 'jogarTrecho').mockResolvedValue({
      success: true,
      resultado: passo()
    });
    const responder = vi.spyOn(treinoService, 'responder');
    const fixture = await montar();
    fixture.componentInstance.lance.set('Cf3');

    await fixture.componentInstance.responder();

    expect(jogarTrecho).toHaveBeenCalledWith(21, 'Cf3');
    expect(responder).not.toHaveBeenCalled();
  });

  it('ao fechar a janela revela a curva e a comparação com a partida', async () => {
    vi.spyOn(treinoService, 'jogarTrecho').mockResolvedValue({
      success: true,
      resultado: passo({
        concluido: true,
        lance_oponente: null,
        qualidade_lance: 'BOM',
        queda_liquida: 4.2,
        queda_original: 42,
        resumo: 'Você segurou o trecho: 4.2% de queda líquida ao longo da janela.',
        curva: [
          { numero: 1, lance: 'Cf3', win_antes: 61, win_depois: 59.5, queda: 1.5 },
          { numero: 2, lance: 'e3', win_antes: 59.5, win_depois: 62, queda: -2.5 }
        ],
        raiz_conceitual_violada: 'Peça sem função.',
        livro_citado: 'Meu Sistema',
        proxima_revisao_data: '2026-09-18',
        repeticoes: 1
      })
    });
    const fixture = await montar();
    fixture.componentInstance.lance.set('Cf3');

    await fixture.componentInstance.jogarLanceDoTrecho();
    fixture.detectChanges();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Você segurou o trecho');
    expect(texto).toContain('Queda neste treino');
    expect(texto).toContain('4.2%');
    expect(texto).toContain('42%');
    // Queda negativa é melhora, e aparece com o sinal trocado.
    expect(texto).toContain('−1.5%');
    expect(texto).toContain('+2.5%');
    expect(texto).toContain('Peça sem função.');
    expect(texto).toContain('2026-09-18');
  });

  it('trecho reiniciado pelo servidor recarrega a fila sem culpar o usuário', async () => {
    const getFila = vi.spyOn(treinoService, 'getFila');
    vi.spyOn(treinoService, 'jogarTrecho').mockResolvedValue({
      success: false,
      error: 'O progresso deste trecho ficou inconsistente e foi reiniciado.',
      trechoReiniciado: true
    });
    const fixture = await montar();
    fixture.componentInstance.lance.set('Cf3');

    await fixture.componentInstance.jogarLanceDoTrecho();

    expect(fixture.componentInstance.passoTrecho()).toBeNull();
    expect(fixture.componentInstance.erro()).toContain('reiniciado');
    expect(getFila).toHaveBeenCalledTimes(2);
  });

  it('avançar para o próximo card descarta o trecho anterior', async () => {
    vi.spyOn(treinoService, 'jogarTrecho').mockResolvedValue({
      success: true,
      resultado: passo()
    });
    const fixture = await montar();
    fixture.componentInstance.lance.set('Cf3');
    await fixture.componentInstance.jogarLanceDoTrecho();

    fixture.componentInstance.proxima();

    expect(fixture.componentInstance.passoTrecho()).toBeNull();
  });
});
