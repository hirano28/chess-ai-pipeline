import { TestBed } from '@angular/core/testing';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';
import { describe, expect, it } from 'vitest';
import { DiagnosticoSecaoComponent, SecaoDiagnostico } from './diagnostico-secao.component';
import { PuzzlesInsightsComponent } from '../puzzles-insights/puzzles-insights.component';
import { RepertorioInsightsComponent } from '../repertorio-insights/repertorio-insights.component';
import { SessoesTreinoComponent } from '../sessoes-treino/sessoes-treino.component';
import { Component } from '@angular/core';

@Component({ selector: 'app-repertorio-insights', template: 'REPERTORIO' })
class RepertorioFalso {}
@Component({ selector: 'app-puzzles-insights', template: 'PUZZLES' })
class PuzzlesFalso {}
@Component({ selector: 'app-sessoes-treino', template: 'SESSOES' })
class SessoesFalso {}

async function montar(secao: SecaoDiagnostico): Promise<HTMLElement> {
  TestBed.resetTestingModule();
  await TestBed.configureTestingModule({
    imports: [DiagnosticoSecaoComponent],
    providers: [{ provide: ActivatedRoute, useValue: { data: of({ secao }), snapshot: { data: { secao } } } }]
  })
    // Os blocos reais buscam dados na montagem; aqui só importa qual entra.
    .overrideComponent(DiagnosticoSecaoComponent, {
      remove: { imports: [RepertorioInsightsComponent, PuzzlesInsightsComponent, SessoesTreinoComponent] },
      add: { imports: [RepertorioFalso, PuzzlesFalso, SessoesFalso] }
    })
    .compileComponents();
  const fixture = TestBed.createComponent(DiagnosticoSecaoComponent);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('DiagnosticoSecaoComponent (D-71)', () => {
  it('cada rota mostra o seu bloco com título próprio, e só ele', async () => {
    const casos: [SecaoDiagnostico, string, string][] = [
      ['aberturas', 'Aberturas', 'REPERTORIO'],
      ['puzzles', 'Puzzles', 'PUZZLES'],
      ['plano', 'Plano de treino', 'SESSOES']
    ];
    for (const [secao, titulo, bloco] of casos) {
      const tela = await montar(secao);
      expect(tela.querySelector('h1')?.textContent?.trim()).toBe(titulo);
      const texto = tela.textContent ?? '';
      expect(texto).toContain(bloco);
      for (const outro of ['REPERTORIO', 'PUZZLES', 'SESSOES'].filter((b) => b !== bloco)) {
        expect(texto).not.toContain(outro);
      }
    }
  });
});
