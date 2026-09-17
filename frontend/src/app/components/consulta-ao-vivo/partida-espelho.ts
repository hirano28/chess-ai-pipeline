import { Chess } from 'chess.js';
import { CorJogador, PlataformaEspelho } from '../../services/consulta-ao-vivo.service';

/** A partida que está sendo espelhada, do jeito que é guardada no navegador. */
export interface PartidaEspelho {
  id: string;
  fenInicial: string | null;
  lances: string[];
  cor: CorJogador;
  plataforma: PlataformaEspelho;
  adversario: string;
}

const CHAVE_ARMAZENAMENTO = 'consulta-ao-vivo:partida';

// Letra da peça em português -> inglês. "R" é Rei aqui e Torre em inglês, por
// isso a tradução é tentada ANTES do texto cru, na mesma ordem que o backend
// usa em resolver_lance_usuario.
const PECA_PT_PARA_EN: Record<string, string> = { R: 'K', D: 'Q', T: 'R', B: 'B', C: 'N' };

export function novoIdPartida(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // Ambientes sem randomUUID (jsdom antigo): mesmo formato, menos entropia.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function novaPartida(
  cor: CorJogador,
  plataforma: PlataformaEspelho,
  adversario: string,
  fenInicial: string | null = null
): PartidaEspelho {
  return { id: novoIdPartida(), fenInicial, lances: [], cor, plataforma, adversario };
}

/** Reconstrói o jogo a partir da partida. Lance inválido no meio corta ali. */
export function reconstruirJogo(partida: PartidaEspelho): Chess {
  const jogo = partida.fenInicial ? new Chess(partida.fenInicial) : new Chess();
  for (const lance of partida.lances) {
    try {
      jogo.move(lance);
    } catch {
      break;
    }
  }
  return jogo;
}

/** Converte "Cxe5", "Df3+", "exd8=D" para a notação que o chess.js entende. */
export function traduzirLancePt(texto: string): string {
  const limpo = texto.trim().replace(/0-0-0/g, 'O-O-O').replace(/0-0/g, 'O-O');
  const comPeca = limpo.replace(/^[RDTBC]/, (letra) => PECA_PT_PARA_EN[letra] ?? letra);
  return comPeca.replace(/=([DTBC])/, (_m, letra: string) => `=${PECA_PT_PARA_EN[letra]}`);
}

/**
 * Tenta um lance digitado, em português primeiro e em inglês depois. Devolve o
 * SAN canônico, ou null se o texto não é um lance legal na posição.
 */
export function resolverLanceDigitado(jogo: Chess, texto: string): string | null {
  const tentativas = [traduzirLancePt(texto), texto.trim()];
  for (const tentativa of tentativas) {
    if (!tentativa) {
      continue;
    }
    const copia = new Chess(jogo.fen());
    try {
      return copia.move(tentativa).san;
    } catch {
      // tenta a próxima leitura
    }
  }
  return null;
}

/**
 * Lê um PGN (ou uma FEN solta) para retomar a partida de onde ela está.
 * Útil quando o espelho ficou para trás: copiar o PGN do site é mais rápido que
 * clicar dez lances.
 */
export function lerPgnOuFen(texto: string): { fenInicial: string | null; lances: string[] } {
  const conteudo = texto.trim();
  if (!conteudo) {
    throw new Error('Cole um PGN ou uma FEN.');
  }
  if (/^[1-8pnbrqkPNBRQK/]+\s+[wb]\s/.test(conteudo)) {
    const jogo = new Chess(conteudo);
    return { fenInicial: jogo.fen(), lances: [] };
  }
  const jogo = new Chess();
  try {
    jogo.loadPgn(conteudo);
  } catch {
    throw new Error('Não consegui ler esse PGN.');
  }
  const cabecalhos = jogo.getHeaders();
  const fenInicial = cabecalhos['FEN'] ?? null;
  return { fenInicial, lances: jogo.history() };
}

export function salvarPartida(partida: PartidaEspelho | null): void {
  try {
    if (partida) {
      localStorage.setItem(CHAVE_ARMAZENAMENTO, JSON.stringify(partida));
    } else {
      localStorage.removeItem(CHAVE_ARMAZENAMENTO);
    }
  } catch {
    // Armazenamento indisponível: a partida só não sobrevive a recarregar.
  }
}

export function carregarPartida(): PartidaEspelho | null {
  try {
    const bruto = localStorage.getItem(CHAVE_ARMAZENAMENTO);
    if (!bruto) {
      return null;
    }
    const dados = JSON.parse(bruto) as Partial<PartidaEspelho>;
    if (
      typeof dados.id !== 'string' ||
      !Array.isArray(dados.lances) ||
      (dados.cor !== 'BRANCAS' && dados.cor !== 'PRETAS')
    ) {
      return null;
    }
    return {
      id: dados.id,
      fenInicial: typeof dados.fenInicial === 'string' ? dados.fenInicial : null,
      lances: dados.lances.filter((l): l is string => typeof l === 'string'),
      cor: dados.cor,
      plataforma:
        dados.plataforma === 'CHESSCOM' || dados.plataforma === 'OUTRA' ? dados.plataforma : 'LICHESS',
      adversario: typeof dados.adversario === 'string' ? dados.adversario : ''
    };
  } catch {
    return null;
  }
}
