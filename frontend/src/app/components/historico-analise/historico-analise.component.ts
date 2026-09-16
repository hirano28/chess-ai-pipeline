import { Component, EventEmitter, Input, Output } from '@angular/core';
import { formatarDataCurta } from '../../shared/data';
import { TabuleiroPreviewComponent } from '../tabuleiro-preview/tabuleiro-preview.component';

/**
 * Estado de processamento de um item de histórico, quando aplicável.
 * Telas com pipeline assíncrono (ex: Analisador de Partida) usam os 4
 * estados; telas que só persistem um resultado já pronto (Explicador,
 * Laboratório) deixam `status` indefinido e o badge simplesmente não aparece.
 */
export type StatusHistoricoAnalise = 'pendente' | 'processando' | 'concluido' | 'falhou';

/** Um item genérico de histórico, já mapeado pela tela que o consome. */
export interface HistoricoAnaliseItem {
  id: string;
  /** Linha principal, em destaque (ex: nome dos jogadores, o lance salvo). */
  titulo: string;
  /** Linha secundária: fatos curtos exibidos separados por "•". */
  detalhes?: string[];
  /** Data ISO (created_at); formatada aqui, não pela tela que consome. */
  dataIso?: string | null;
  status?: StatusHistoricoAnalise;
  /**
   * Posição que identifica visualmente o item. Quando presente, a linha ganha
   * uma miniatura do tabuleiro à esquerda — é o que permite reconhecer de qual
   * partida/análise/exercício a linha está falando sem ter que abrir. Ausente
   * (ou FEN inválido) simplesmente não desenha miniatura nenhuma.
   */
  fen?: string | null;
  /** Perspectiva da miniatura; default BRANCAS. */
  orientacao?: 'BRANCAS' | 'PRETAS';
}

/**
 * Lista de histórico reutilizável entre as telas interativas (Analisador de
 * Partida, Explicador de Posição, Laboratório de Raciocínio).
 *
 * Extraído do Analisador de Partida (ver D-11 em docs/DECISOES.md): cada tela
 * mapeia seus próprios itens para HistoricoAnaliseItem e trata o clique via
 * (itemClicado) para restaurar o estado que só ELA sabe restaurar - este
 * componente continua sem conhecer PGN nem regra de xadrez: o campo `fen` é
 * repassado cru para o TabuleiroPreview, que já é quem sabe fazer o parse (e
 * já trata FEN inválido desenhando tabuleiro vazio).
 */
@Component({
  selector: 'app-historico-analise',
  standalone: true,
  imports: [TabuleiroPreviewComponent],
  templateUrl: './historico-analise.component.html'
})
export class HistoricoAnaliseComponent {
  @Input() titulo = 'Histórico de Análises';
  @Input() itens: HistoricoAnaliseItem[] = [];
  @Input() carregando = false;
  @Input() mensagemVazio = 'Nenhuma análise recente registrada.';
  /** Auditoria de UX pós-D-49: sem isto, uma falha ao buscar o histórico
   * ficava indistinguível de "não há nada ainda" (mensagemVazio). */
  @Input() erro: string | null = null;

  /** Emite o id do item clicado; quem usa o componente decide como restaurar. */
  @Output() itemClicado = new EventEmitter<string>();
  @Output() atualizarClicado = new EventEmitter<void>();

  /** Variante de `.selo` (ver src/styles.css) correspondente ao status. */
  corBadgeStatus(status: StatusHistoricoAnalise | undefined): string {
    switch (status) {
      case 'concluido':
        return 'selo-sucesso';
      case 'processando':
        return 'selo-info';
      case 'falhou':
        return 'selo-perigo';
      default:
        return 'selo-latao';
    }
  }

  rotuloBadgeStatus(status: StatusHistoricoAnalise | undefined): string {
    switch (status) {
      case 'concluido':
        return 'Concluída';
      case 'processando':
        return 'Processando';
      case 'falhou':
        return 'Falhou';
      default:
        return 'Na fila';
    }
  }

  rotuloBotaoAcao(status: StatusHistoricoAnalise | undefined): string {
    switch (status) {
      case 'concluido':
        return 'Ver análise →';
      case 'processando':
        return 'Acompanhar';
      case 'falhou':
        return 'Reprocessar';
      case 'pendente':
        return 'Acompanhar';
      default:
        // Sem pipeline assíncrono (Explicador, Laboratório): item já é um
        // resultado salvo e pronto, só falta reabri-lo.
        return 'Ver detalhes →';
    }
  }

  /** Wrapper fino sobre o helper compartilhado, só para o template poder chamá-lo. */
  formatarData(iso?: string | null): string {
    return formatarDataCurta(iso);
  }
}
