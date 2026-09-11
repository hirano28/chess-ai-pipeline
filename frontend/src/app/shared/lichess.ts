/** Helpers para abrir posições no analisador público do Lichess. */

const LICHESS_ANALYSIS_BASE = 'https://lichess.org/analysis/fromPosition';

/**
 * Monta a URL do analisador do Lichess para uma FEN já resolvida.
 *
 * O Lichess espera a FEN na própria rota, com os espaços trocados por "_".
 * Retorna null quando não há FEN utilizável — assim o chamador simplesmente
 * não renderiza o link, em vez de apontar para uma posição quebrada.
 */
export function urlAnaliseLichess(fen: string | null | undefined): string | null {
  const texto = (fen ?? '').trim();
  if (!texto) {
    return null;
  }

  // Checagem mínima de sanidade: o 1º campo da FEN precisa ter as 8 fileiras.
  const colocacao = texto.split(/\s+/)[0];
  if (colocacao.split('/').length !== 8) {
    return null;
  }

  return `${LICHESS_ANALYSIS_BASE}/${texto.replace(/\s+/g, '_')}`;
}
