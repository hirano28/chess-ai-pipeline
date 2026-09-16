/** Leitura mínima de FEN compartilhada entre as telas com miniatura. */

export type OrientacaoTabuleiro = 'BRANCAS' | 'PRETAS';

/**
 * Orientação natural para exibir uma posição: a perspectiva de quem está na
 * vez de jogar (2º campo do FEN). Usado nas miniaturas de histórico, onde o
 * item é sempre "uma posição para resolver" e mostrá-la de cabeça para baixo
 * atrapalha justamente o reconhecimento rápido que a miniatura existe para dar.
 *
 * Não valida a FEN — isso é trabalho do TabuleiroPreview. Qualquer entrada
 * ausente ou malformada cai no default BRANCAS.
 */
export function orientacaoDoFen(fen?: string | null): OrientacaoTabuleiro {
  return (fen ?? '').trim().split(/\s+/)[1]?.toLowerCase() === 'b'
    ? 'PRETAS'
    : 'BRANCAS';
}
