import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { map } from 'rxjs';
import { PuzzlesInsightsComponent } from '../puzzles-insights/puzzles-insights.component';
import { RepertorioInsightsComponent } from '../repertorio-insights/repertorio-insights.component';
import { SessoesTreinoComponent } from '../sessoes-treino/sessoes-treino.component';

export type SecaoDiagnostico = 'aberturas' | 'puzzles' | 'plano';

/** Só o título: cada bloco já traz a própria descrição, e repeti-la no
 *  cabeçalho da página era o texto dito duas vezes seguidas. */
const TITULOS: Record<SecaoDiagnostico, string> = {
  aberturas: 'Aberturas',
  puzzles: 'Puzzles',
  plano: 'Plano de treino'
};

/**
 * Subpáginas do diagnóstico (D-71). Até o D-70 estes blocos ficavam todos na
 * rolagem da página do Hexágono — cerca de 7.900 px no desktop. Cada um já era
 * um componente que busca os próprios dados; aqui só ganham rota e cabeçalho.
 * A seção vem de `data.secao` da rota.
 */
@Component({
  selector: 'app-diagnostico-secao',
  standalone: true,
  imports: [RepertorioInsightsComponent, PuzzlesInsightsComponent, SessoesTreinoComponent],
  template: `
    <main class="pagina">
      <section class="conteudo">
        <header>
          <p class="sobrelinha">Diagnóstico</p>
          <h1 class="titulo-pagina">{{ titulo() }}</h1>
        </header>

        @switch (secao()) {
          @case ('aberturas') {
            <app-repertorio-insights />
          }
          @case ('puzzles') {
            <app-puzzles-insights />
          }
          @case ('plano') {
            <app-sessoes-treino />
          }
        }
      </section>
    </main>
  `
})
export class DiagnosticoSecaoComponent {
  private readonly rota = inject(ActivatedRoute);

  readonly secao = toSignal(
    this.rota.data.pipe(map((dados) => (dados['secao'] as SecaoDiagnostico) ?? 'aberturas')),
    { initialValue: (this.rota.snapshot.data['secao'] as SecaoDiagnostico) ?? 'aberturas' }
  );

  readonly titulo = computed(() => TITULOS[this.secao()]);
}
