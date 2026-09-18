import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import {
  BibliotecaService,
  ConsultaBibliotecaRecenteItem,
  RespostaBiblioteca,
  formatarFonte
} from '../../services/biblioteca.service';
import {
  HistoricoAnaliseComponent,
  HistoricoAnaliseItem
} from '../historico-analise/historico-analise.component';

/** Chave de localStorage que sobrevive a um F5, mesmo padrão das outras telas. */
export const STORAGE_KEY_BIBLIOTECA_ATIVA = 'chess_biblioteca_ativa';

/** Limite do backend (`PERGUNTA_MAX_CARACTERES` em consultar_biblioteca.py). */
export const PERGUNTA_MAX_CARACTERES = 500;

const TITULO_HISTORICO_MAX_CHARS = 90;

/**
 * Sugestões de partida. Existem porque uma caixa de texto vazia não comunica
 * o que esta tela sabe responder — e o corpus é de teoria posicional, tática
 * e de finais, não de regras básicas.
 */
export const PERGUNTAS_SUGERIDAS = [
  'Por que um peão isolado na dama é fraco no final e forte no meio-jogo?',
  'Quando vale a pena trocar bispo por cavalo?',
  'Como atacar um rei que não rocou?',
  'O que faz um final de torres ser ganho ou empatado?'
];

@Component({
  selector: 'app-biblioteca',
  standalone: true,
  imports: [CommonModule, HistoricoAnaliseComponent],
  templateUrl: './biblioteca.component.html'
})
export class BibliotecaComponent implements OnInit {
  readonly pergunta = signal('');
  readonly carregando = signal(false);
  readonly erro = signal<string | null>(null);
  readonly sessaoExpirada = signal(false);
  readonly resultado = signal<RespostaBiblioteca | null>(null);

  readonly historico = signal<ConsultaBibliotecaRecenteItem[]>([]);
  readonly carregandoHistorico = signal(false);
  readonly erroHistorico = signal<string | null>(null);

  readonly sugestoes = PERGUNTAS_SUGERIDAS;
  readonly maxCaracteres = PERGUNTA_MAX_CARACTERES;

  readonly caracteresRestantes = computed(
    () => PERGUNTA_MAX_CARACTERES - this.pergunta().trim().length
  );

  readonly itensHistoricoComponent = computed<HistoricoAnaliseItem[]>(() =>
    this.historico().map((item) => {
      const titulo =
        item.pergunta.length > TITULO_HISTORICO_MAX_CHARS
          ? `${item.pergunta.slice(0, TITULO_HISTORICO_MAX_CHARS)}…`
          : item.pergunta;
      const fontes = item.resposta?.fontes ?? [];
      const livros = [...new Set(fontes.map((fonte) => fonte.livro))];
      return {
        id: item.id,
        titulo,
        detalhes: livros.length ? [livros.join(' · ')] : ['Sem fonte citada'],
        dataIso: item.created_at
      };
    })
  );

  private readonly bibliotecaService = inject(BibliotecaService);
  private readonly route = inject(ActivatedRoute);

  get formularioValido(): boolean {
    const texto = this.pergunta().trim();
    return texto.length > 0 && texto.length <= PERGUNTA_MAX_CARACTERES;
  }

  async ngOnInit(): Promise<void> {
    // D-81: a tela de Aberturas manda a pergunta pronta por query param — é o
    // que liga o diagnóstico de repertório ao acervo, já que "abertura" não é
    // (e não vai ser) uma categoria do Hexágono.
    const perguntaDaUrl = this.route.snapshot.queryParamMap.get('pergunta');
    await this.carregarHistorico();
    if (perguntaDaUrl) {
      this.pergunta.set(perguntaDaUrl.slice(0, PERGUNTA_MAX_CARACTERES));
      await this.consultar();
      return;
    }
    this.restaurarAtivoSalvo();
  }

  usarSugestao(sugestao: string): void {
    this.pergunta.set(sugestao);
  }

  async consultar(): Promise<void> {
    if (!this.formularioValido || this.carregando()) {
      return;
    }
    this.carregando.set(true);
    this.erro.set(null);
    this.sessaoExpirada.set(false);

    const resposta = await this.bibliotecaService.consultar(this.pergunta().trim());

    this.carregando.set(false);
    if (!resposta.success || !resposta.dados) {
      this.erro.set(resposta.error ?? 'Falha ao consultar a biblioteca');
      this.sessaoExpirada.set(resposta.sessaoExpirada === true);
      return;
    }

    this.resultado.set(resposta.dados);
    this.salvarAtivo(resposta.dados);
    await this.carregarHistorico();
  }

  async carregarHistorico(): Promise<void> {
    this.carregandoHistorico.set(true);
    this.erroHistorico.set(null);
    const resposta = await this.bibliotecaService.listarRecentes();
    this.carregandoHistorico.set(false);
    if (!resposta.success || !resposta.dados) {
      this.erroHistorico.set(resposta.error ?? 'Falha ao carregar o histórico');
      return;
    }
    this.historico.set(resposta.dados);
  }

  abrirDoHistorico(id: string): void {
    const item = this.historico().find((linha) => linha.id === id);
    if (!item) {
      return;
    }
    const dados: RespostaBiblioteca = {
      id: item.id,
      pergunta: item.pergunta,
      resposta: item.resposta?.resposta ?? '',
      fontes: item.resposta?.fontes ?? []
    };
    this.pergunta.set(item.pergunta);
    this.resultado.set(dados);
    this.salvarAtivo(dados);
  }

  descricaoFonte(fonte: { livro: string; capitulo?: string | null; pagina_aprox?: number | null }): string {
    return formatarFonte(fonte);
  }

  private salvarAtivo(dados: RespostaBiblioteca): void {
    try {
      localStorage.setItem(STORAGE_KEY_BIBLIOTECA_ATIVA, JSON.stringify(dados));
    } catch {
      // Cota cheia ou storage bloqueado não pode derrubar a tela.
    }
  }

  private restaurarAtivoSalvo(): void {
    try {
      const bruto = localStorage.getItem(STORAGE_KEY_BIBLIOTECA_ATIVA);
      if (!bruto) {
        return;
      }
      const dados = JSON.parse(bruto) as RespostaBiblioteca;
      if (dados?.resposta) {
        this.resultado.set(dados);
        this.pergunta.set(dados.pergunta ?? '');
      }
    } catch {
      // JSON corrompido é o mesmo que não ter nada salvo.
    }
  }
}
