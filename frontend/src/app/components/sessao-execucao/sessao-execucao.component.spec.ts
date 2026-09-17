import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { SessaoExecucaoComponent } from './sessao-execucao.component';
import { ExecucaoSessao, SessaoService } from '../../services/sessao.service';

describe('SessaoExecucaoComponent', () => {
  let component: SessaoExecucaoComponent;
  let fixture: ComponentFixture<SessaoExecucaoComponent>;
  let sessaoService: SessaoService;

  const SESSAO_ID = 'sessao-1';

  function execucao(overrides: Partial<ExecucaoSessao> = {}): ExecucaoSessao {
    return {
      sessao_id: SESSAO_ID,
      titulo: 'Sprint de Superação Tática',
      categoria_foco: 'TATICA',
      data_prescrita: '2026-09-14T00:00:00Z',
      data_iniciada: null,
      data_concluida: null,
      duracao_total_min: 40,
      concluida: false,
      blocos: [
        {
          indice: 0,
          tipo: 'estudo',
          nome: 'Teoria: Ataques Descobertos',
          conteudo: 'Mecanismos do xeque descoberto.',
          duracao_min: 15,
          livro: 'Xadrez Vitorioso',
          capitulo: 'ATAQUES DESCOBERTOS',
          pagina_aprox: 23,
          concluido: false,
          categoria: null,
          exercicios_feitos: null,
          exercicios_total: null
        },
        {
          indice: 1,
          tipo: 'pratica',
          nome: 'Prática: 12 exercícios de Tática',
          conteudo: null,
          duracao_min: null,
          livro: null,
          capitulo: null,
          pagina_aprox: null,
          concluido: false,
          categoria: 'TATICA',
          exercicios_feitos: 3,
          exercicios_total: 12
        }
      ],
      ...overrides
    };
  }

  async function criarComponente(): Promise<void> {
    fixture = TestBed.createComponent(SessaoExecucaoComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SessaoExecucaoComponent],
      providers: [
        provideHttpClient(),
        provideRouter([]),
        SessaoService,
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ id: SESSAO_ID }) } }
        }
      ]
    }).compileComponents();

    sessaoService = TestBed.inject(SessaoService);
  });

  it('sessão não iniciada mostra o plano e o botão de iniciar', async () => {
    vi.spyOn(sessaoService, 'obterExecucao').mockResolvedValue({
      success: true,
      execucao: execucao()
    });
    await criarComponente();

    expect(component.iniciada()).toBe(false);
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Iniciar sessão');
    expect(texto).toContain('Sprint de Superação Tática');
    // Antes de iniciar não existe progresso nenhum para mostrar.
    expect(fixture.nativeElement.querySelector('[role="progressbar"]')).toBeNull();
  });

  it('iniciar() troca o estado pelo que o backend devolveu', async () => {
    vi.spyOn(sessaoService, 'obterExecucao').mockResolvedValue({
      success: true,
      execucao: execucao()
    });
    const iniciar = vi.spyOn(sessaoService, 'iniciar').mockResolvedValue({
      success: true,
      execucao: execucao({ data_iniciada: '2026-09-16T10:00:00Z' })
    });
    await criarComponente();

    await component.iniciar();
    fixture.detectChanges();

    expect(iniciar).toHaveBeenCalledWith(SESSAO_ID);
    expect(component.iniciada()).toBe(true);
    expect(fixture.nativeElement.querySelector('[role="progressbar"]')).not.toBeNull();
  });

  it('o percentual reflete os blocos concluídos', async () => {
    const blocos = execucao().blocos;
    blocos[0].concluido = true;
    vi.spyOn(sessaoService, 'obterExecucao').mockResolvedValue({
      success: true,
      execucao: execucao({ data_iniciada: '2026-09-16T10:00:00Z', blocos })
    });
    await criarComponente();

    expect(component.blocosConcluidos()).toBe(1);
    expect(component.totalBlocos()).toBe(2);
    expect(component.percentual()).toBe(50);
    // O bloco em aberto é o destacado como "agora".
    expect(component.blocoAtual()?.indice).toBe(1);
  });

  it('o bloco de prática não oferece "marcar como lido"', async () => {
    /** D-54: marcar prática à mão devolveria o "eu acho que terminei" que a
     * conclusão automática veio remover. */
    vi.spyOn(sessaoService, 'obterExecucao').mockResolvedValue({
      success: true,
      execucao: execucao({ data_iniciada: '2026-09-16T10:00:00Z' })
    });
    const concluir = vi.spyOn(sessaoService, 'concluirBloco');
    await criarComponente();

    const botoes = Array.from(
      fixture.nativeElement.querySelectorAll('button')
    ) as HTMLButtonElement[];
    const marcarComoLido = botoes.filter((botao) =>
      (botao.textContent ?? '').includes('Marcar como lido')
    );
    expect(marcarComoLido.length).toBe(1);

    await component.concluirBloco(component.blocos()[1]);
    expect(concluir).not.toHaveBeenCalled();
  });

  it('concluirBloco() envia o índice do bloco de estudo', async () => {
    vi.spyOn(sessaoService, 'obterExecucao').mockResolvedValue({
      success: true,
      execucao: execucao({ data_iniciada: '2026-09-16T10:00:00Z' })
    });
    const concluir = vi.spyOn(sessaoService, 'concluirBloco').mockResolvedValue({
      success: true,
      execucao: execucao({ data_iniciada: '2026-09-16T10:00:00Z' })
    });
    await criarComponente();

    await component.concluirBloco(component.blocos()[0]);

    expect(concluir).toHaveBeenCalledWith(SESSAO_ID, 0);
  });

  it('sessão concluída avisa que a eficácia será medida sozinha', async () => {
    const blocos = execucao().blocos.map((bloco) => ({ ...bloco, concluido: true }));
    vi.spyOn(sessaoService, 'obterExecucao').mockResolvedValue({
      success: true,
      execucao: execucao({
        data_iniciada: '2026-09-16T10:00:00Z',
        data_concluida: '2026-09-16T12:00:00Z',
        concluida: true,
        blocos
      })
    });
    await criarComponente();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Sessão concluída');
    expect(component.percentual()).toBe(100);
  });

  it('categoria sem catálogo explica em vez de travar a sessão', async () => {
    const blocos = execucao().blocos;
    blocos[1] = {
      ...blocos[1],
      categoria: 'ESTRATEGIA',
      exercicios_feitos: 0,
      exercicios_total: 0,
      concluido: true
    };
    vi.spyOn(sessaoService, 'obterExecucao').mockResolvedValue({
      success: true,
      execucao: execucao({ data_iniciada: '2026-09-16T10:00:00Z', blocos })
    });
    await criarComponente();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Ainda não há exercícios de catálogo em Estratégia');
  });

  it('erro de carregamento é exibido sem quebrar a tela', async () => {
    vi.spyOn(sessaoService, 'obterExecucao').mockResolvedValue({
      success: false,
      error: 'Sessão de treino não encontrada.'
    });
    await criarComponente();

    expect(component.erro()).toContain('não encontrada');
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Voltar ao plano de treino');
  });
});
