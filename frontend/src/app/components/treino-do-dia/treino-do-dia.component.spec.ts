import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { TreinoDoDiaComponent } from './treino-do-dia.component';
import { FilaTreino, ResultadoTreino, TreinoService } from '../../services/treino.service';

describe('TreinoDoDiaComponent', () => {
  let component: TreinoDoDiaComponent;
  let fixture: ComponentFixture<TreinoDoDiaComponent>;
  let treinoService: TreinoService;

  const item1 = {
    fila_id: 7,
    fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    origem: 'lance_critico' as const,
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

  const mockFila: FilaTreino = { itens: [item1, item2], feitas_hoje: 1, total_hoje: 3 };

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
      fila: { itens: [], feitas_hoje: 3, total_hoje: 3 }
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
      fila: { itens: [itemExercicio], feitas_hoje: 0, total_hoje: 1 }
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
        fila: { itens: [itemCronometrado], feitas_hoje: 0, total_hoje: 1 }
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
