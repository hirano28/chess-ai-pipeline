import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { LanceTabuleiro, TabuleiroInterativoComponent } from './tabuleiro-interativo.component';

const INICIAL = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

describe('TabuleiroInterativoComponent (D-67)', () => {
  let fixture: ComponentFixture<TabuleiroInterativoComponent>;
  let emitidos: LanceTabuleiro[];

  function montar(fen: string, extras: Record<string, unknown> = {}): void {
    fixture = TestBed.createComponent(TabuleiroInterativoComponent);
    fixture.componentRef.setInput('fen', fen);
    for (const [nome, valor] of Object.entries(extras)) {
      fixture.componentRef.setInput(nome, valor);
    }
    emitidos = [];
    fixture.componentInstance.lanceJogado.subscribe((lance) => emitidos.push(lance));
    fixture.detectChanges();
  }

  function casa(nome: string): HTMLButtonElement {
    return (fixture.nativeElement as HTMLElement).querySelector(`[data-casa="${nome}"]`)!;
  }

  function clicar(nome: string): void {
    casa(nome).click();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [TabuleiroInterativoComponent] }).compileComponents();
  });

  it('desenha as 64 casas com a1 escura no canto de baixo', () => {
    montar(INICIAL);
    const casas = (fixture.nativeElement as HTMLElement).querySelectorAll('[data-casa]');
    expect(casas.length).toBe(64);
    expect(casas[56].getAttribute('data-casa')).toBe('a1');
    expect(casa('a1').className).toContain('bg-casa-escura');
  });

  it('vira o tabuleiro para quem joga de pretas', () => {
    montar(INICIAL, { orientacao: 'PRETAS' });
    const primeira = (fixture.nativeElement as HTMLElement).querySelector('[data-casa]');
    expect(primeira?.getAttribute('data-casa')).toBe('h1');
  });

  it('peça e depois casa emite o lance', () => {
    montar(INICIAL);
    clicar('g1');
    expect(fixture.componentInstance.selecionada()).toBe('g1');
    expect(casa('f3').getAttribute('aria-label')).toContain('mover para cá');

    clicar('f3');
    expect(emitidos).toEqual([{ from: 'g1', to: 'f3' }]);
    expect(fixture.componentInstance.selecionada()).toBeNull();
  });

  it('não seleciona peça de quem não está na vez nem aceita destino ilegal', () => {
    montar(INICIAL);
    clicar('e7');
    expect(fixture.componentInstance.selecionada()).toBeNull();

    clicar('e2');
    clicar('e5');
    expect(emitidos).toEqual([]);
  });

  it('promoção pergunta a peça antes de emitir', () => {
    montar('8/4P3/8/8/8/8/k7/4K3 w - - 0 1');
    clicar('e7');
    clicar('e8');
    expect(emitidos).toEqual([]);
    expect(fixture.componentInstance.promocaoPendente()).toEqual({ from: 'e7', to: 'e8' });

    fixture.componentInstance.escolherPromocao('n');
    expect(emitidos).toEqual([{ from: 'e7', to: 'e8', promotion: 'n' }]);
  });

  it('bloqueado não aceita clique', () => {
    montar(INICIAL, { bloqueado: true });
    fixture.componentInstance.clicar(fixture.componentInstance.casas().find((c) => c.nome === 'g1')!);
    expect(fixture.componentInstance.selecionada()).toBeNull();
  });
});
