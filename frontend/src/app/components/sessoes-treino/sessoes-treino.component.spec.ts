import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { SessoesTreinoComponent } from './sessoes-treino.component';
import { SessaoTreino, SupabaseService } from '../../services/supabase.service';

describe('SessoesTreinoComponent (P-4 / D-38)', () => {
  let component: SessoesTreinoComponent;
  let fixture: ComponentFixture<SessoesTreinoComponent>;
  let supabaseService: SupabaseService;

  const sessoesExemplo: SessaoTreino[] = [
    {
      id: 'sessao-1',
      diagnostico_gargalo: 'TATICA: cálculo tático deficiente',
      modulos: [
        {
          nome: 'Cálculo de variantes forçadas',
          duracao_min: 20,
          conteudo: 'Exercícios de lances forçados.',
          livro: 'Manual de Tática',
          capitulo: 'Capítulo 2',
          pagina_aprox: 45
        }
      ],
      data_prescrita: '2026-09-01T10:00:00Z',
      data_concluida: '2026-09-05T12:00:00Z',
      eficacia_medida: 60.0,
      observacoes: 'Frequência de TATICA caiu de 10 para 4 ocorrências (60.0% de redução).'
    },
    {
      id: 'sessao-2',
      diagnostico_gargalo: 'FINAIS: erro técnico de final',
      modulos: [],
      data_prescrita: '2026-09-08T10:00:00Z',
      data_concluida: '2026-09-10T12:00:00Z',
      eficacia_medida: null,
      observacoes: null
    },
    {
      id: 'sessao-3',
      diagnostico_gargalo: 'ESTRUTURA_DE_PEOES: fraqueza estrutural',
      modulos: [],
      data_prescrita: '2026-09-12T10:00:00Z',
      data_concluida: null,
      eficacia_medida: null,
      observacoes: null
    }
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SessoesTreinoComponent],
      providers: [
        // D-54: o cartão da sessão aberta agora leva para /sessao/:id, então o
        // template usa RouterLink.
        provideRouter([]),
        {
          provide: SupabaseService,
          useValue: {
            getSessoesTreino: vi.fn().mockResolvedValue(sessoesExemplo),
            marcarSessaoConcluida: vi.fn().mockResolvedValue({
              success: true,
              dataConcluida: '2026-09-14T15:00:00Z'
            }),
            desmarcarSessaoConcluida: vi.fn().mockResolvedValue({
              success: true
            })
          }
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(SessoesTreinoComponent);
    component = fixture.componentInstance;
    supabaseService = TestBed.inject(SupabaseService);
  });

  it('inicializa e carrega as sessões de treino com métricas de resumo', async () => {
    fixture.detectChanges();
    await fixture.whenStable();

    expect(component.loading()).toBe(false);
    expect(component.sessoes().length).toBe(3);
    expect(component.totalPrescritas()).toBe(3);
    expect(component.totalConcluidas()).toBe(2);
    expect(component.mediaEficacia()).toBe(60.0);
  });

  it('exibe badge e observação corretos quando a eficácia está medida', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('↓ 60.0% de falhas');
    expect(compiled.textContent).toContain('Frequência de TATICA caiu de 10 para 4 ocorrências');
  });

  it('exibe mensagem de aguardando janela quando concluída sem eficácia ainda', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Aguardando partidas suficientes pós-treino');
  });

  it('permite marcar uma sessão aberta como concluída', async () => {
    fixture.detectChanges();
    await fixture.whenStable();

    const sessaoAberta = component.sessoes()[2]; // sessao-3
    expect(sessaoAberta.data_concluida).toBeNull();

    await component.marcarComoConcluida(sessaoAberta);

    expect(supabaseService.marcarSessaoConcluida).toHaveBeenCalledWith('sessao-3');
    const sessaoAtualizada = component.sessoes().find((s) => s.id === 'sessao-3');
    expect(sessaoAtualizada?.data_concluida).toBe('2026-09-14T15:00:00Z');
    expect(component.totalConcluidas()).toBe(3);
  });

  it('a sessão aberta oferece executar, não só declarar concluída (D-54)', async () => {
    /** 5 sessões prescritas e 0 concluídas em produção: o botão manual era o
     * único caminho e ninguém o usava. A ação principal agora leva para a tela
     * de execução. */
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const links = Array.from(
      fixture.nativeElement.querySelectorAll('a[href^="/sessao/"]')
    ) as HTMLAnchorElement[];
    expect(links.length).toBe(1);
    expect(links[0].getAttribute('href')).toBe('/sessao/sessao-3');
    expect(links[0].textContent).toContain('Iniciar sessão');
  });

  it('sessão já iniciada convida a continuar, não a recomeçar', async () => {
    (supabaseService.getSessoesTreino as ReturnType<typeof vi.fn>).mockResolvedValue([
      { ...sessoesExemplo[2], data_iniciada: '2026-09-13T10:00:00Z' }
    ]);
    fixture = TestBed.createComponent(SessoesTreinoComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const link = fixture.nativeElement.querySelector(
      'a[href^="/sessao/"]'
    ) as HTMLAnchorElement;
    expect(link.textContent).toContain('Continuar sessão');
  });

  it('permite desmarcar / reabrir uma sessão concluída', async () => {
    fixture.detectChanges();
    await fixture.whenStable();

    const sessaoConcluida = component.sessoes()[0]; // sessao-1
    expect(sessaoConcluida.data_concluida).not.toBeNull();

    await component.desmarcarComoConcluida(sessaoConcluida);

    expect(supabaseService.desmarcarSessaoConcluida).toHaveBeenCalledWith('sessao-1');
    const sessaoAtualizada = component.sessoes().find((s) => s.id === 'sessao-1');
    expect(sessaoAtualizada?.data_concluida).toBeNull();
    expect(sessaoAtualizada?.eficacia_medida).toBeNull();
    expect(sessaoAtualizada?.observacoes).toBeNull();
    expect(component.totalConcluidas()).toBe(1);
  });

  it('formata adequadamente badges de eficácia positiva, negativa e neutra', () => {
    const badgePositivo = component.obterBadgeEficacia(40.5);
    expect(badgePositivo.texto).toBe('↓ 40.5% de falhas');
    expect(badgePositivo.classe).toBe('selo-sucesso');

    const badgeNegativo = component.obterBadgeEficacia(-25.0);
    expect(badgeNegativo.texto).toBe('↑ 25.0% de falhas');
    expect(badgeNegativo.classe).toBe('selo-perigo');

    const badgeNeutro = component.obterBadgeEficacia(0);
    expect(badgeNeutro.texto).toBe('0.0% de variação');
    expect(badgeNeutro.classe).toBe('selo-neutro');
  });

  it('trata erro ao carregar sessões', async () => {
    vi.spyOn(supabaseService, 'getSessoesTreino').mockRejectedValue(new Error('Falha de rede'));

    const fixtureErro = TestBed.createComponent(SessoesTreinoComponent);
    const componentErro = fixtureErro.componentInstance;
    fixtureErro.detectChanges();
    await fixtureErro.whenStable();

    expect(componentErro.loading()).toBe(false);
    expect(componentErro.error()).toContain('Não foi possível carregar as sessões de treino');
  });

  it('trata erro ao marcar sessão como concluída', async () => {
    fixture.detectChanges();
    await fixture.whenStable();

    vi.spyOn(supabaseService, 'marcarSessaoConcluida').mockResolvedValue({
      success: false,
      error: 'Permissão negada'
    });

    await component.marcarComoConcluida(component.sessoes()[2]);

    expect(component.error()).toContain('Não foi possível concluir a sessão');
  });

  it('só a sessão mais recente abre expandida', async () => {
    fixture.detectChanges();
    await fixture.whenStable();

    const sessoes = component.sessoes();
    expect(sessoes.length).toBeGreaterThan(1);
    expect(component.expandida(sessoes[0].id)).toBe(true);
    for (const antiga of sessoes.slice(1)) {
      expect(component.expandida(antiga.id)).toBe(false);
    }
  });

  it('alternarExpansao abre e fecha a mesma sessão', async () => {
    fixture.detectChanges();
    await fixture.whenStable();

    const antiga = component.sessoes()[1];
    component.alternarExpansao(antiga.id);
    expect(component.expandida(antiga.id)).toBe(true);

    component.alternarExpansao(antiga.id);
    expect(component.expandida(antiga.id)).toBe(false);
    // Fechar uma não pode fechar a outra.
    expect(component.expandida(component.sessoes()[0].id)).toBe(true);
  });

  it('a sessão fechada ainda diz quantos módulos e quantos minutos tem', async () => {
    fixture.detectChanges();
    await fixture.whenStable();

    const resumo = component.resumoDosModulos(component.sessoes()[0]);
    expect(resumo).toMatch(/módulos?/);
    expect(resumo).toContain('min');
  });
});
