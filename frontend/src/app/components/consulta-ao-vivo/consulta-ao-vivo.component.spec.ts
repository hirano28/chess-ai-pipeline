import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConsultaAoVivoComponent } from './consulta-ao-vivo.component';
import { ConsultaAoVivo, ConsultaAoVivoService } from '../../services/consulta-ao-vivo.service';

function consultaFake(extras: Partial<ConsultaAoVivo> = {}): ConsultaAoVivo {
  return {
    id: 'c1',
    partida_espelho_id: 'p1',
    numero_lance: 3,
    fen: 'x',
    cor_jogador: 'BRANCAS',
    lances_san: ['e4', 'e5', 'Nf3', 'Nc6'],
    pensamento: null,
    camada_pensar: {
      leitura_da_posicao: 'O centro está em tensão.',
      sobre_o_seu_raciocinio: null,
      perguntas_guia: ['O que o adversário ameaça?'],
      planos: [{ titulo: 'Desenvolver', explicacao: 'Tire as peças da primeira fileira.' }]
    },
    camada_ideias: { ideias: [{ lance: 'Bb5', ideia: 'Pressiona o cavalo de c6.' }] },
    camada_motor: {
      melhor_lance: 'Bc4',
      avaliacao: '+0.40',
      win_percent_jogador: 53.7,
      linhas: [{ lance: 'Bc4', avaliacao: '+40', sequencia: ['Bc4', 'Bc5'] }]
    },
    gerado_por: 'gemini',
    consultas_restantes: 2,
    criado_em: null,
    ...extras
  };
}

describe('ConsultaAoVivoComponent (D-67)', () => {
  let fixture: ComponentFixture<ConsultaAoVivoComponent>;
  let component: ConsultaAoVivoComponent;
  let service: ConsultaAoVivoService;

  async function montar(): Promise<void> {
    fixture = TestBed.createComponent(ConsultaAoVivoComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [ConsultaAoVivoComponent],
      providers: [provideHttpClient(), provideRouter([])]
    }).compileComponents();
    service = TestBed.inject(ConsultaAoVivoService);
    vi.spyOn(service, 'acesso').mockResolvedValue({ habilitado: true, limitePorPartida: 3 });
    vi.spyOn(service, 'listarDaPartida').mockResolvedValue({ success: true, dados: [] });
  });

  it('espelha lances do tabuleiro e do texto em português', async () => {
    await montar();
    component.jogarDoTabuleiro({ from: 'e2', to: 'e4' });
    component.lanceDigitado.set('e5');
    component.jogarDoTexto();
    component.lanceDigitado.set('Cf3');
    component.jogarDoTexto();

    expect(component.partida().lances).toEqual(['e4', 'e5', 'Nf3']);
    component.desfazer();
    expect(component.partida().lances).toEqual(['e4', 'e5']);
  });

  it('lance digitado ilegal mostra erro e não entra na partida', async () => {
    await montar();
    component.lanceDigitado.set('Dh5');
    component.jogarDoTexto();
    expect(component.erroLance()).toContain('não é um lance legal');
    expect(component.partida().lances).toEqual([]);
  });

  it('na vez do adversário a consulta fica desligada e diz por quê', async () => {
    await montar();
    component.jogarDoTabuleiro({ from: 'e2', to: 'e4' });
    fixture.detectChanges();

    expect(component.podeConsultar()).toBe(false);
    expect(texto()).toContain('espelhe o lance dele primeiro');
  });

  it('consulta manda os lances e o pensamento, e revela em camadas', async () => {
    const consultar = vi
      .spyOn(service, 'consultar')
      .mockResolvedValue({ success: true, dados: consultaFake() });
    await montar();
    for (const lance of ['e4', 'e5', 'Nf3', 'Nc6']) {
      component.lanceDigitado.set(lance);
      component.jogarDoTexto();
    }
    component.situacao.set('Não sei se ataco ou desenvolvo');

    await component.consultar();
    fixture.detectChanges();

    const enviado = consultar.mock.calls[0][0];
    expect(enviado.lances).toEqual(['e4', 'e5', 'Nf3', 'Nc6']);
    expect(enviado.pensamento).toEqual({
      situacao: 'Não sei se ataco ou desenvolvo',
      candidatos: null,
      trava: null
    });
    expect(enviado.partida_espelho_id).toBe(component.partida().id);

    // Camada 1 à vista; ideias e motor escondidos.
    expect(texto()).toContain('O centro está em tensão.');
    expect(texto()).toContain('O que o adversário ameaça?');
    expect(texto()).not.toContain('Pressiona o cavalo de c6.');
    expect(texto()).not.toContain('Melhor lance');

    component.revelar('c1', 2);
    fixture.detectChanges();
    expect(texto()).toContain('Pressiona o cavalo de c6.');
    expect(texto()).not.toContain('Melhor lance');

    component.revelar('c1', 3);
    fixture.detectChanges();
    expect(texto()).toContain('Melhor lance');
    expect(texto()).toContain('Bc4');

    // O campo de pensamento é limpo para a próxima dúvida.
    expect(component.situacao()).toBe('');
    expect(component.consultasRestantes()).toBe(2);
  });

  it('sem pensamento manda null, não três strings vazias', async () => {
    const consultar = vi
      .spyOn(service, 'consultar')
      .mockResolvedValue({ success: true, dados: consultaFake() });
    await montar();
    await component.consultar();
    expect(consultar.mock.calls[0][0].pensamento).toBeNull();
  });

  it('esgotar as consultas da partida desliga o botão com a explicação', async () => {
    vi.spyOn(service, 'consultar').mockResolvedValue({
      success: true,
      dados: consultaFake({ consultas_restantes: 0 })
    });
    await montar();
    await component.consultar();
    fixture.detectChanges();

    expect(component.podeConsultar()).toBe(false);
    expect(texto()).toContain('a decisão é sua');
  });

  it('erro do servidor aparece e não cria consulta', async () => {
    vi.spyOn(service, 'consultar').mockResolvedValue({
      success: false,
      error: 'Você já usou as 3 consultas desta partida.',
      limiteAtingido: true
    });
    await montar();
    await component.consultar();
    expect(component.erroConsulta()).toContain('3 consultas');
    expect(component.consultas()).toEqual([]);
  });

  it('recarregar a tela recupera a partida e as consultas dela', async () => {
    const salva = {
      id: '0b8f3c1e-5d2a-4e6b-9c7d-1a2b3c4d5e6f',
      fenInicial: null,
      lances: ['d4', 'd5'],
      cor: 'BRANCAS',
      plataforma: 'CHESSCOM',
      adversario: 'Bot'
    };
    localStorage.setItem('consulta-ao-vivo:partida', JSON.stringify(salva));
    const listar = vi
      .spyOn(service, 'listarDaPartida')
      .mockResolvedValue({ success: true, dados: [consultaFake({ id: 'antiga' })] });

    await montar();

    expect(component.partida().lances).toEqual(['d4', 'd5']);
    expect(listar).toHaveBeenCalledWith(salva.id);
    expect(component.consultas().length).toBe(1);
    // Já vista antes: volta toda aberta.
    expect(component.nivel('antiga')).toBe(3);
  });

  it('partida nova troca o id e zera lances e consultas', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(service, 'consultar').mockResolvedValue({ success: true, dados: consultaFake() });
    await montar();
    const idAntigo = component.partida().id;
    component.jogarDoTabuleiro({ from: 'e2', to: 'e4' });
    component.desfazer();
    await component.consultar();

    component.jogarDoTabuleiro({ from: 'e2', to: 'e4' });
    component.comecarNovaPartida();

    expect(component.partida().id).not.toBe(idAntigo);
    expect(component.partida().lances).toEqual([]);
    expect(component.consultas()).toEqual([]);
  });

  it('PGN colado substitui os lances', async () => {
    await montar();
    component.textoPgn.set('1. e4 c5 2. Nf3 d6 *');
    component.aplicarPgn();
    expect(component.partida().lances).toEqual(['e4', 'c5', 'Nf3', 'd6']);
    expect(component.listaDeLances()).toEqual([
      { numero: 1, brancas: 'e4', pretas: 'c5' },
      { numero: 2, brancas: 'Nf3', pretas: 'd6' }
    ]);
  });
});
