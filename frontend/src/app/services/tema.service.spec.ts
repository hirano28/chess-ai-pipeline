import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CHAVE_TEMA, TemaService } from './tema.service';

function simularSistema(escuro: boolean): (novoValor: boolean) => void {
  let ouvinte: ((evento: { matches: boolean }) => void) | null = null;
  vi.stubGlobal('matchMedia', () => ({
    matches: escuro,
    addEventListener: (_: string, fn: (evento: { matches: boolean }) => void) => (ouvinte = fn)
  }));
  return (novoValor) => ouvinte?.({ matches: novoValor });
}

describe('TemaService (D-71)', () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset['tema'];
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    TestBed.resetTestingModule();
  });

  function criar(): TemaService {
    const servico = TestBed.inject(TemaService);
    TestBed.tick();
    return servico;
  }

  it('sem escolha, segue o aparelho e acompanha a mudança dele', () => {
    const mudarSistema = simularSistema(true);
    const servico = criar();
    expect(servico.preferencia()).toBe('sistema');
    expect(document.documentElement.dataset['tema']).toBe('escuro');

    mudarSistema(false);
    TestBed.tick();
    expect(servico.tema()).toBe('claro');
    expect(document.documentElement.dataset['tema']).toBe('claro');
  });

  it('a escolha manual vence o aparelho e fica salva', () => {
    simularSistema(true);
    const servico = criar();
    servico.escolher('claro');
    TestBed.tick();

    expect(document.documentElement.dataset['tema']).toBe('claro');
    expect(document.documentElement.style.colorScheme).toBe('light');
    expect(localStorage.getItem(CHAVE_TEMA)).toBe('claro');
  });

  it('volta a seguir o sistema apagando a escolha salva', () => {
    simularSistema(false);
    localStorage.setItem(CHAVE_TEMA, 'escuro');
    const servico = criar();
    expect(servico.tema()).toBe('escuro');

    servico.escolher('sistema');
    TestBed.tick();
    expect(localStorage.getItem(CHAVE_TEMA)).toBeNull();
    expect(servico.tema()).toBe('claro');
  });

  it('valor salvo inválido conta como "sistema"', () => {
    simularSistema(false);
    localStorage.setItem(CHAVE_TEMA, 'roxo');
    expect(criar().preferencia()).toBe('sistema');
  });
});
