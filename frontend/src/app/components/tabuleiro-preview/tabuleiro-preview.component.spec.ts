import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, beforeEach, it, expect } from 'vitest';
import { TabuleiroPreviewComponent } from './tabuleiro-preview.component';

describe('TabuleiroPreviewComponent', () => {
  let component: TabuleiroPreviewComponent;
  let fixture: ComponentFixture<TabuleiroPreviewComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TabuleiroPreviewComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(TabuleiroPreviewComponent);
    component = fixture.componentInstance;
  });

  it('deve ser criado com 64 casas', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
    expect(component.casas.length).toBe(64);
  });

  it('deve fazer parse correto da posição inicial do xadrez', () => {
    component.fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    fixture.detectChanges();

    // Primeira casa (a8) deve ter torre preta 'bR'
    expect(component.casas[0].peca).toBe('bR');
    // Última casa (h1) deve ter torre branca 'wR'
    expect(component.casas[63].peca).toBe('wR');
    expect(component.vezDeJogar()).toBe('BRANCAS');
  });

  it('deve identificar vez das pretas a partir do FEN', () => {
    component.fen = 'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2';
    fixture.detectChanges();

    expect(component.vezDeJogar()).toBe('PRETAS');
  });

  it('deve alternar a orientação entre BRANCAS e PRETAS', () => {
    component.fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    fixture.detectChanges();

    expect(component.orientacaoAtiva()).toBe('BRANCAS');
    expect(component.casas[0].peca).toBe('bR'); // a8 no topo esquerdo

    component.alternarOrientacao();
    fixture.detectChanges();

    expect(component.orientacaoAtiva()).toBe('PRETAS');
    expect(component.casas[0].peca).toBe('wR'); // h1 no topo esquerdo quando visto de pretas
  });

  it('deve gerar coordenadas de rank e file quando mostrarCoordenadas for true', () => {
    component.fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    component.mostrarCoordenadas = true;
    component.miniatura = false;
    fixture.detectChanges();

    // Na primeira casa (a8): rankLabel '8'
    expect(component.casas[0].rankLabel).toBe('8');
    // Na última casa da coluna a (a1, índice 56): rankLabel '1' e fileLabel 'a'
    expect(component.casas[56].rankLabel).toBe('1');
    expect(component.casas[56].fileLabel).toBe('a');
  });
});

