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
    const segunda: PerguntaPendente = { ...pergunta, id: 'q-2' };
    vi.spyOn(supabaseService, 'getPerguntasPendentes').mockResolvedValue([pergunta, segunda]);
    await criarComponente();

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
});
