import { Component, EventEmitter, Input, Output } from '@angular/core';
import { formatarDataCurta } from '../../shared/data';

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
}

/**
 * Lista de histórico reutilizável entre as telas interativas (Analisador de
 * Partida, Explicador de Posição, Laboratório de Raciocínio).
 *
 * Extraído do Analisador de Partida (ver D-11 em docs/DECISOES.md): cada tela
 * mapeia seus próprios itens para HistoricoAnaliseItem e trata o clique via
 * (itemClicado) para restaurar o estado que só ELA sabe restaurar - este
 * componente não conhece FEN, PGN nem nenhuma regra de xadrez.
 */
@Component({
  selector: 'app-historico-analise',
  standalone: true,
  templateUrl: './historico-analise.component.html'
})
export class HistoricoAnaliseComponent {
  @Input() titulo = 'Histórico de Análises';
  @Input() itens: HistoricoAnaliseItem[] = [];
  @Input() carregando = false;
  @Input() mensagemVazio = 'Nenhuma análise recente registrada.';

  /** Emite o id do item clicado; quem usa o componente decide como restaurar. */
  @Output() itemClicado = new EventEmitter<string>();
  @Output() atualizarClicado = new EventEmitter<void>();

  corBadgeStatus(status: StatusHistoricoAnalise | undefined): string {
    switch (status) {
      case 'concluido':
        return 'border-[#2e613b] bg-[#1b3323] text-[#7ae89c]';
      case 'processando':
        return 'border-[#2b4c61] bg-[#1a2e3b] text-[#5bc0de]';
      case 'falhou':
        return 'border-[#765044] bg-[#2a211f] text-[#e7c4b3]';
      default:
        return 'border-[#7a6a2a] bg-[#332c14] text-[#e8cf7a]';
    }
  }

  rotuloBadgeStatus(status: StatusHistoricoAnalise | undefined): string {
    switch (status) {
      case 'concluido':
        return '✅ Concluída';
      case 'processando':
        return '⏳ Processando';
      case 'falhou':
        return '❌ Falhou';
      default:
        return '⏱️ Na Fila';
    }
  }

  rotuloBotaoAcao(status: StatusHistoricoAnalise | undefined): string {
    switch (status) {
      case 'concluido':
        return 'Ver Análise →';
      case 'processando':
        return 'Acompanhar ⏳';
      case 'falhou':
        return 'Reprocessar 🔄';
      case 'pendente':
        return 'Acompanhar ⏱️';
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
