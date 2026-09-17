import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { PerguntasPendentesComponent } from './perguntas-pendentes.component';
import { PerguntaPendente, SupabaseService } from '../../services/supabase.service';

describe('PerguntasPendentesComponent', () => {
  let component: PerguntasPendentesComponent;
  let fixture: ComponentFixture<PerguntasPendentesComponent>;
  let supabaseService: SupabaseService;

  const pergunta: PerguntaPendente = {
    id: 'q-1',
    perguntaTexto: 'O que você pensou nesse lance?',
    partidaId: 'p-1',
    numeroLance: 14,
    numeroLanceFim: null,
    lanceNotacao: 'Cxe5',
    tipoEvento: 'PICO',
    dataPartida: '2026-09-10T00:00:00Z',
    corJogada: 'BRANCAS',
    fenAntesLance: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
  };

  async function criarComponente(): Promise<void> {
    fixture = TestBed.createComponent(PerguntasPendentesComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PerguntasPendentesComponent],
      providers: [provideHttpClient(), provideRouter([]), SupabaseService]
    }).compileComponents();

    supabaseService = TestBed.inject(SupabaseService);
  });

  it('deve carregar e exibir as perguntas pendentes', async () => {
    vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue([pergunta]);
    await criarComponente();

    expect(component.loading()).toBe(false);
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('O que você pensou nesse lance?');
  });

  it('deve exibir mensagem de erro quando a busca falha', async () => {
    vi.spyOn(supabaseService, 'getPerguntasPendentes').mockRejectedValue(new Error('fora do ar'));
    await criarComponente();

    expect(component.error()).toContain('fora do ar');
  });

  it('responder() com sucesso remove a pergunta da lista', async () => {
    vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue([pergunta]);
    vi.spyOn(supabaseService, 'responderPergunta').mockResolvedValue({ success: true });
    await criarComponente();

    await component.responder(pergunta, 'Achei que era só um lance normal.');

    expect(component.perguntas()).toEqual([]);
    expect(component.enviando().has('q-1')).toBe(false);
  });

  it('responder() com falha mantém a pergunta e expõe o erro', async () => {
    vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue([pergunta]);
    vi.spyOn(supabaseService, 'responderPergunta').mockResolvedValue({
      success: false,
      error: 'Sessão expirada.'
    });
    await criarComponente();

    await component.responder(pergunta, 'Uma resposta qualquer.');

    expect(component.perguntas()).toEqual([pergunta]);
    expect(component.error()).toContain('Sessão expirada.');
  });

  it('responder() ignora texto vazio e não chama o serviço', async () => {
    vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue([pergunta]);
    const spy = vi.spyOn(supabaseService, 'responderPergunta');
    await criarComponente();

    await component.responder(pergunta, '   ');

    expect(spy).not.toHaveBeenCalled();
  });

  it('só a primeira pergunta abre o campo de resposta', async () => {
    /** D-53. Desde o D-64 as demais nem renderizam até o usuário expandir, e
     * por isso o teste expande antes: o que se afirma aqui é que expandir
     * revela o ENUNCIADO das outras, não seis textareas abertas. */
    const segunda: PerguntaPendente = { ...pergunta, id: 'q-2' };
    vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue([pergunta, segunda]);
    await criarComponente();

    component.alternarMostrarTodas();
    fixture.detectChanges();

    expect(component.respondendo('q-1')).toBe(true);
    expect(component.respondendo('q-2')).toBe(false);

    // Uma textarea só: as outras perguntas continuam legíveis, sem o campo.
    const campos = fixture.nativeElement.querySelectorAll('textarea');
    expect(campos.length).toBe(1);
    // O enunciado das duas segue visível, para dar pra escolher qual responder.
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Responder esta');
  });

  it('abrirResposta revela o campo da pergunta escolhida', async () => {
    const segunda: PerguntaPendente = { ...pergunta, id: 'q-2' };
    vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue([pergunta, segunda]);
    await criarComponente();

    component.alternarMostrarTodas();
    component.abrirResposta('q-2');
    fixture.detectChanges();

    expect(component.respondendo('q-2')).toBe(true);
    expect(fixture.nativeElement.querySelectorAll('textarea').length).toBe(2);
  });

  it('formatarData trata valores nulos e inválidos sem lançar', async () => {
    vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue([]);
    await criarComponente();

    expect(component.formatarData(null)).toBe('data indisponível');
    expect(component.formatarData('não-é-uma-data')).toBe('data indisponível');
  });

  describe('lista compacta (D-64)', () => {
    /** Seis cartões com miniatura de tabuleiro ocupavam quase metade da altura
     * da página ACIMA do radar. O diagnóstico, que é o produto, começava
     * abaixo de uma lista de tarefas que nunca foi respondida — 0 de 6 em toda
     * a vida do recurso. Uma pergunta por vez lê como convite; seis, como
     * cobrança. */
    const varias: PerguntaPendente[] = [1, 2, 3, 4, 5, 6].map((n) => ({
      ...pergunta,
      id: `q-${n}`,
      numeroLance: n,
      perguntaTexto: `Pergunta numero ${n}?`
    }));

    it('mostra só a primeira e esconde o resto atrás de um clique', async () => {
      vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue(varias);
      await criarComponente();

      expect(component.perguntasVisiveis().length).toBe(1);
      expect(component.quantidadeOculta()).toBe(5);
      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(texto).toContain('Pergunta numero 1?');
      expect(texto).not.toContain('Pergunta numero 6?');
      expect(texto).toContain('Ver as outras 5 perguntas');
    });

    it('o clique revela as demais e o botão passa a recolher', async () => {
      vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue(varias);
      await criarComponente();

      component.alternarMostrarTodas();
      fixture.detectChanges();

      expect(component.perguntasVisiveis().length).toBe(6);
      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(texto).toContain('Pergunta numero 6?');
      expect(texto).toContain('Mostrar só a primeira');
    });

    it('com uma pergunta só, nao oferece expandir', async () => {
      vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue([pergunta]);
      await criarComponente();

      expect(component.quantidadeOculta()).toBe(0);
      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(texto).not.toContain('Ver as outras');
    });

    it('o selo continua contando TODAS, nao so as visiveis', async () => {
      // Esconder o resto nao pode esconder o tamanho do que esta pendente.
      vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue(varias);
      await criarComponente();

      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(texto).toContain('6 aguardando resposta');
    });

    it('duas perguntas usam o singular no botao', async () => {
      vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue(varias.slice(0, 2));
      await criarComponente();

      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(texto).toContain('Ver as outras 1 pergunta');
    });
  });
});
