import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  ItemFilaTreino,
  ROTULOS_CATEGORIA_HEXAGONO,
  ResultadoTreino,
  TreinoService
} from '../../services/treino.service';
import { TabuleiroPreviewComponent } from '../tabuleiro-preview/tabuleiro-preview.component';

@Component({
  selector: 'app-treino-do-dia',
  standalone: true,
  imports: [RouterLink, TabuleiroPreviewComponent],
  templateUrl: './treino-do-dia.component.html'
})
export class TreinoDoDiaComponent implements OnInit {
  readonly fila = signal<ItemFilaTreino[]>([]);
  readonly feitasHoje = signal(0);
  readonly totalHoje = signal(0);

  readonly carregando = signal(true);
  readonly enviando = signal(false);
  readonly erro = signal<string | null>(null);

  readonly lance = signal('');
  readonly resultado = signal<ResultadoTreino | null>(null);

  readonly itemAtual = computed<ItemFilaTreino | null>(() => this.fila()[0] ?? null);
  readonly formularioValido = computed(
    () => this.lance().trim().length > 0 && !this.enviando()
  );

  private readonly treinoService = inject(TreinoService);

  ngOnInit(): void {
    this.carregarFila();
  }

  async carregarFila(): Promise<void> {
    this.carregando.set(true);
    this.erro.set(null);

    const resposta = await this.treinoService.getFila();
    if (resposta.sessaoExpirada) {
      this.erro.set(resposta.error ?? 'Sessão expirada.');
      this.carregando.set(false);
      return;
    }
    if (!resposta.success || !resposta.fila) {
      this.erro.set(resposta.error ?? 'Não foi possível carregar a fila de treino.');
      this.carregando.set(false);
      return;
    }

    this.fila.set(resposta.fila.itens);
    this.feitasHoje.set(resposta.fila.feitas_hoje);
    this.totalHoje.set(resposta.fila.total_hoje);
    this.carregando.set(false);
  }

  async responder(): Promise<void> {
    const item = this.itemAtual();
    if (!item || !this.formularioValido() || this.enviando()) {
      return;
    }

    this.enviando.set(true);
    this.erro.set(null);

    const resposta = await this.treinoService.responder(item.fila_id, this.lance().trim());

    if (resposta.sessaoExpirada) {
      this.erro.set(resposta.error ?? 'Sessão expirada.');
      this.enviando.set(false);
      return;
    }
    if (!resposta.success || !resposta.resultado) {
      this.erro.set(resposta.error ?? 'Não foi possível avaliar o lance.');
      this.enviando.set(false);
      return;
    }

    this.resultado.set(resposta.resultado);
    this.enviando.set(false);
  }

  /** Avança para o próximo card da fila, descartando o feedback do anterior. */
  proxima(): void {
    this.fila.update((itens) => itens.slice(1));
    this.feitasHoje.update((n) => n + 1);
    this.lance.set('');
    this.resultado.set(null);
    this.erro.set(null);
  }

  /** Rótulo amigável da categoria de um exercício de catálogo (D-49). */
  rotuloCategoria(categoria: string | null): string {
    return (categoria && ROTULOS_CATEGORIA_HEXAGONO[categoria]) || 'Exercício tático';
  }

  /** Variante de `.selo` (ver src/styles.css) — mesmo mapeamento do Laboratório. */
  corBadgeQualidadeLance(qualidade: string): string {
    switch (qualidade) {
      case 'BOM':
        return 'selo-sucesso';
      case 'SUBOTIMO':
        return 'selo-latao';
      default:
        return 'selo-perigo';
    }
  }
}
