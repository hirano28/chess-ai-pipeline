import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
    como_pensar: {
      tipo_de_posicao: 'O centro está em tensão.',
      sobre_o_seu_raciocinio: 'Você olhou o ataque antes de ver se suas peças estavam seguras.',
      roteiro: [
        { o_que_avaliar: 'O que o adversário ameaça.', por_que: 'Nenhum plano vale com uma peça caindo.' },
        { o_que_avaliar: 'Qual peça sua ainda não saiu.', por_que: 'Na abertura, tempo perdido pesa mais.' }
      ],
      principio: 'Desenvolva antes de abrir o centro.'
    },
    gerado_por: 'gemini',
    consultas_restantes: 2,
    criado_em: null,
    plataforma: 'LICHESS',
    adversario: null,
    desfecho: {
      status: 'pendente',
      lance_jogado: null,
      queda_win_percent: null,
      era_candidato: null,
      era_o_melhor: null,
      ligada_a_lance_critico: false
    },
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
    // O ngOnInit encadeia várias promessas (acesso, consultas da partida,
    // recentes); um ciclo de macrotarefa garante que todas assentaram.
    await new Promise((resolve) => setTimeout(resolve));
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
    vi.spyOn(service, 'listarRecentes').mockResolvedValue({ success: true, dados: [] });
  });

  describe('sincronização (D-69)', () => {
    afterEach(() => {
      vi.useRealTimers();
      fixture?.componentInstance.ngOnDestroy();
    });

    const partidaLichess = {
      plataforma: 'LICHESS' as const,
      game_id: 'abcd1234',
      partida_espelho_id: '5a1f0c2e-9b7d-5e3a-8c4f-2d6b1a0e9f71',
      cor: 'BRANCAS' as const,
      fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
      vez_do_jogador: true,
      adversario: 'Professor (1900)',
      ranqueada: false,
      ritmo: 'rapid',
      url: 'https://lichess.org/abcd1234'
    };

    function estado(lances: string[], extras: Record<string, unknown> = {}) {
      return {
        success: true,
        dados: { ...partidaLichess, fen_inicial: null, lances, historico_completo: true, ...extras }
      };
    }

    it('lista as partidas em andamento com os avisos da plataforma', async () => {
      vi.spyOn(service, 'listarPartidasEmAndamento').mockResolvedValue({
        success: true,
        dados: { partidas: [partidaLichess], avisos: ['Do Chess.com só aparecem partidas diárias.'] }
      });
      await montar();

      await component.buscarPartidas();
      fixture.detectChanges();

      expect(texto()).toContain('Lichess · Brancas contra Professor (1900) · rapid · casual');
      expect(texto()).toContain('sua vez');
      expect(texto()).toContain('partidas diárias');
    });

    it('sincronizar usa o id da partida real, carrega as consultas dela e trava o espelho à mão', async () => {
      const listar = vi.spyOn(service, 'listarDaPartida').mockResolvedValue({ success: true, dados: [] });
      vi.spyOn(service, 'estadoPartida').mockResolvedValue(estado(['e4', 'e5', 'Nf3']));
      await montar();

      await component.sincronizar(partidaLichess);
      fixture.detectChanges();

      expect(component.partida().id).toBe(partidaLichess.partida_espelho_id);
      expect(listar).toHaveBeenCalledWith(partidaLichess.partida_espelho_id);
      expect(component.partida().lances).toEqual(['e4', 'e5', 'Nf3']);
      expect(texto()).toContain('Sincronizada com o Lichess');

      // Lance à mão não entra numa partida sincronizada.
      component.jogarDoTabuleiro({ from: 'b8', to: 'c6' });
      component.desfazer();
      expect(component.partida().lances).toEqual(['e4', 'e5', 'Nf3']);
      component.ngOnDestroy();
    });

    it('a atualização periódica acompanha os lances novos', async () => {
      const estadoSpy = vi
        .spyOn(service, 'estadoPartida')
        .mockResolvedValueOnce(estado(['e4']))
        .mockResolvedValue(estado(['e4', 'e5']));
      await montar();
      // Só o setInterval é falso: o montar() e as promessas usam o relógio real.
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
      await component.sincronizar(partidaLichess);
      expect(component.partida().lances).toEqual(['e4']);

      await vi.advanceTimersByTimeAsync(4100);

      expect(estadoSpy).toHaveBeenCalledTimes(2);
      expect(component.partida().lances).toEqual(['e4', 'e5']);
      component.ngOnDestroy();
    });

    it('historico incompleto guarda a posição exata e avisa', async () => {
      const fen = 'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3';
      vi.spyOn(service, 'estadoPartida').mockResolvedValue(
        estado(['e4'], { historico_completo: false, fen })
      );
      await montar();
      await component.sincronizar(partidaLichess);
      fixture.detectChanges();

      expect(component.fen()).toBe(fen);
      expect(component.partida().lances).toEqual([]);
      expect(texto()).toContain('não pôde ser');
      component.ngOnDestroy();
    });

    it('partida que terminou para de sincronizar e explica o que vem depois', async () => {
      vi.spyOn(service, 'estadoPartida').mockResolvedValue({
        success: false,
        error: 'Not Found',
        terminou: true
      });
      await montar();
      await component.sincronizar(partidaLichess);

      expect(component.sincronizada()).toBeNull();
      expect(component.avisoFimDePartida()).toContain('coleta desta noite');
      // E não fica um temporizador rodando à toa.
      expect((component as unknown as { temporizador: unknown }).temporizador).toBeNull();
    });

    it('plataforma recusou: mostra o erro e espera antes de insistir', async () => {
      const estadoSpy = vi.spyOn(service, 'estadoPartida').mockResolvedValue({
        success: false,
        error: 'Tente de novo em um minuto.'
      });
      await montar();
      await component.sincronizar(partidaLichess);
      await component.atualizarPartida();

      expect(component.erroSincronizacao()).toContain('um minuto');
      // A segunda chamada caiu dentro da espera e nem foi feita.
      expect(estadoSpy).toHaveBeenCalledTimes(1);
      expect(component.sincronizada()).not.toBeNull();
      component.ngOnDestroy();
    });

    it('a consulta de partida sincronizada manda a referência, não só os lances', async () => {
      vi.spyOn(service, 'estadoPartida').mockResolvedValue(estado(['e4', 'e5']));
      const consultar = vi.spyOn(service, 'consultar').mockResolvedValue({ success: true, dados: consultaFake() });
      await montar();
      await component.sincronizar(partidaLichess);

      await component.consultar();

      expect(consultar.mock.calls[0][0].sincronizada).toEqual({ plataforma: 'LICHESS', game_id: 'abcd1234' });
      component.ngOnDestroy();
    });

    it('parar volta ao espelho à mão na posição em que estava', async () => {
      vi.spyOn(service, 'estadoPartida').mockResolvedValue(estado(['e4', 'e5']));
      await montar();
      await component.sincronizar(partidaLichess);

      component.pararSincronizacao();
      component.jogarDoTabuleiro({ from: 'g1', to: 'f3' });

      expect(component.sincronizada()).toBeNull();
      expect(component.partida().lances).toEqual(['e4', 'e5', 'Nf3']);
    });
  });

  describe('desfecho (D-68)', () => {
    function comDesfecho(desfecho: Partial<ConsultaAoVivo['desfecho']>): ConsultaAoVivo {
      const base = consultaFake();
      return { ...base, desfecho: { ...base.desfecho, ...desfecho } };
    }

    it('descreve cada situação numa frase honesta', async () => {
      await montar();
      expect(component.descreverDesfecho(comDesfecho({ status: 'pendente' }))).toContain('coleta');
      expect(component.descreverDesfecho(comDesfecho({ status: 'sem_partida' }))).toContain('desconhecido');
      expect(component.descreverDesfecho(comDesfecho({ status: 'casada' }))).toContain('terminou');
      expect(
        component.descreverDesfecho(
          comDesfecho({ status: 'casada', lance_jogado: 'Bc4', queda_win_percent: 12.4, era_candidato: false, era_o_melhor: false })
        )
      ).toBe('Você jogou Bc4: não estava entre os lances que o motor considerava e custou 12.4%.');
      expect(
        component.descreverDesfecho(
          comDesfecho({ status: 'casada', lance_jogado: 'Nf1', queda_win_percent: -0.5, era_candidato: true, era_o_melhor: true })
        )
      ).toBe('Você jogou Nf1: era o lance do motor e melhorou a posição em 0.5%.');
    });

    it('cor do desfecho separa o que custou caro do que não custou', async () => {
      await montar();
      expect(component.classeDesfecho(comDesfecho({ status: 'casada', lance_jogado: 'x', queda_win_percent: 15 }))).toBe('text-perigo');
      expect(component.classeDesfecho(comDesfecho({ status: 'casada', lance_jogado: 'x', queda_win_percent: 1 }))).toBe('text-sucesso');
      expect(component.classeDesfecho(comDesfecho({ status: 'pendente' }))).toBe('text-bruma-400');
    });

    it('lista as dúvidas de partidas anteriores, e não as da partida atual', async () => {
      const salva = {
        id: '0b8f3c1e-5d2a-4e6b-9c7d-1a2b3c4d5e6f',
        fenInicial: null,
        lances: [],
        cor: 'BRANCAS',
        plataforma: 'LICHESS',
        adversario: ''
      };
      localStorage.setItem('consulta-ao-vivo:partida', JSON.stringify(salva));
      vi.spyOn(service, 'listarRecentes').mockResolvedValue({
        success: true,
        dados: [
          { ...comDesfecho({ status: 'casada', lance_jogado: 'Bc4', queda_win_percent: 12, ligada_a_lance_critico: true }), id: 'velha', partida_espelho_id: 'outra', adversario: 'professor' },
          { ...consultaFake(), id: 'atual', partida_espelho_id: salva.id }
        ]
      });

      await montar();

      expect(component.duvidasAnteriores().map((c) => c.id)).toEqual(['velha']);
      expect(texto()).toContain('Suas dúvidas anteriores');
      expect(texto()).toContain('contra professor');
      expect(texto()).toContain('Você jogou Bc4');
      expect(texto()).toContain('alimenta o seu Treino');
    });
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

  it('consulta manda os lances e o pensamento, e mostra como avaliar sem lance nenhum', async () => {
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

    // D-70: tipo de posição, raciocínio, roteiro com o porquê e princípio.
    expect(texto()).toContain('O centro está em tensão.');
    expect(texto()).toContain('Você olhou o ataque antes');
    expect(texto()).toContain('O que o adversário ameaça.');
    expect(texto()).toContain('Nenhum plano vale com uma peça caindo.');
    expect(texto()).toContain('Desenvolva antes de abrir o centro.');
    // E nada que leve ao lance: nem botão de candidatos, nem de motor.
    expect(texto()).not.toContain('candidatas');
    expect(texto()).not.toContain('lance do motor');

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
