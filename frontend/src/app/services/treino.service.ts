import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

/**
 * Um card pendente de revisão hoje (D-48; D-49 acrescentou a origem
 * 'exercicio_tatico', do catálogo importado do Lichess). Deliberadamente sem
 * tags_falha, causa raiz ou citação — isso só chega na resposta de
 * `responder()`, depois do usuário tentar o lance.
 */
/**
 * Estado do "Refazer o trecho" num card de EROSAO (D-66). Vem junto do card
 * porque o trecho sobrevive a fechar o navegador — quem voltar no meio precisa
 * ver a posição onde parou. Sem nenhuma avaliação: erosão é o que se perde sem
 * perceber, e um "-4%" por lance viraria oito táticos com placar.
 */
export interface TrechoEmAndamento {
  total_lances: number;
  lances_feitos: number;
  historico: string[];
}

export interface ItemFilaTreino {
  fila_id: number;
  fen: string;
  origem: 'lance_critico' | 'exercicio_tatico' | 'exercicio_posicional';
  /** 'PICO' (um lance) ou 'EROSAO' (a janela inteira, refeita contra o motor).
   * O que muda o formato do card é este campo, não `origem`: um trecho também
   * é um lance crítico do próprio usuário. */
  tipo_evento: 'PICO' | 'EROSAO' | null;
  numero_lance_fim: number | null;
  trecho: TrechoEmAndamento | null;
  numero_lance: number | null;
  cor_jogada: string | null;
  data_partida: string | null;
  plataforma: string | null;
  categoria: string | null;
  /** Só nos cards de Gestão de Tempo (D-55): o mesmo relógio que o jogador da
   * partida original tinha. Chega antes da resposta porque a pressão de tempo
   * É o exercício. */
  segundos_sugeridos: number | null;
  repeticoes: number;
  total_revisoes: number;
}

export interface FilaTreino {
  itens: ItemFilaTreino[];
  feitas_hoje: number;
  total_hoje: number;
  /** Quantos cards de fato venceram. `itens` vem limitado por um teto (D-56);
   * este número preserva a verdade sobre o tamanho do atraso. */
  vencidos_total: number;
  /** Preenchido quando a fila veio filtrada por uma sessão de treino. */
  sessao_id: string | null;
}

/** Revelação completa após responder um card: qualidade, causa raiz e citação. */
export interface ResultadoTreino {
  qualidade_lance: string;
  lance_interpretado: string;
  melhor_lance: string | null;
  queda_win_percent: number;
  raiz_conceitual_violada: string | null;
  tags_falha: string[];
  livro_citado: string | null;
  capitulo_citado: string | null;
  pagina_citada: number | null;
  /** D-55: procedência do exercício posicional, revelada só depois de
   * responder. É também a atribuição exigida pela licença CC BY-SA dos
   * broadcasts do Lichess. */
  partida_referencia: string | null;
  partida_url: string | null;
  /** O lance pode ter sido bom E ter estourado o relógio — são dois fatos. */
  fora_do_tempo: boolean;
  proxima_revisao_data: string;
  repeticoes: number;
}

/** Quanto um lance do jogador custou, na revelação do fim do trecho (D-66). */
export interface LanceDaCurva {
  numero: number;
  lance: string;
  win_antes: number;
  win_depois: number;
  queda: number;
}

/**
 * Resposta de um lance dentro do trecho (D-66).
 *
 * Enquanto a janela corre, só os campos de andamento vêm preenchidos. Os de
 * veredito (`qualidade_lance` em diante) aparecem de uma vez quando
 * `concluido` é true — inclusive a curva lance a lance, que é onde dá para ver
 * em que ponto a posição começou a escorregar.
 */
export interface ResultadoTrecho {
  lance_interpretado: string;
  lance_oponente: string | null;
  fen: string;
  lances_feitos: number;
  total_lances: number;
  historico: string[];
  concluido: boolean;
  /** A partida acabou dentro do trecho (mate ou empate). */
  fim_de_partida: boolean;
  qualidade_lance: string | null;
  queda_liquida: number | null;
  /** Quanto o MESMO trecho custou na partida de verdade. */
  queda_original: number | null;
  resumo: string | null;
  curva: LanceDaCurva[];
  raiz_conceitual_violada: string | null;
  tags_falha: string[];
  livro_citado: string | null;
  capitulo_citado: string | null;
  pagina_citada: number | null;
  proxima_revisao_data: string | null;
  repeticoes: number | null;
}

export interface JogarTrechoResult {
  success: boolean;
  resultado?: ResultadoTrecho;
  error?: string;
  sessaoExpirada?: boolean;
  /** 409: o progresso ficou inconsistente e o servidor reiniciou o trecho. */
  trechoReiniciado?: boolean;
}

export interface FilaTreinoResult {
  success: boolean;
  fila?: FilaTreino;
  error?: string;
  sessaoExpirada?: boolean;
}

export interface ResponderTreinoResult {
  success: boolean;
  resultado?: ResultadoTreino;
  error?: string;
  sessaoExpirada?: boolean;
}

/** Resposta de focarCategoria() (D-49). */
export interface FocoTreinoResult {
  success: boolean;
  adicionados?: number;
  /** Só vem quando `adicionados === 0`: 'sem_catalogo' (categoria sem nenhum
   * exercício importado) ou 'ja_na_fila' (o usuário já tem todos). D-52. */
  motivo?: 'sem_catalogo' | 'ja_na_fila' | null;
  error?: string;
  sessaoExpirada?: boolean;
}

/** Resposta de disponibilidadeFoco() (D-53). */
export interface DisponibilidadeFocoResult {
  success: boolean;
  /** Contagem por categoria; sempre com as 6 chaves quando `success`. */
  porCategoria?: Record<string, number>;
  error?: string;
  sessaoExpirada?: boolean;
}

const MENSAGEM_SESSAO_EXPIRADA = 'Sua sessão expirou. Faça login novamente.';

/** Rótulos amigáveis de HEXAGON_CATEGORIES (backend/agentes/agente2_analista.py),
 * reaproveitados no selo de origem do card (D-49) e no botão "Focar" do Hexágono. */
export const ROTULOS_CATEGORIA_HEXAGONO: Record<string, string> = {
  TATICA: 'Tática',
  ESTRATEGIA: 'Estratégia',
  FINAIS: 'Finais',
  ESTRUTURA_DE_PEOES: 'Estrutura de Peões',
  GESTAO_DE_TEMPO: 'Gestão de Tempo',
  CALCULO: 'Cálculo'
};

@Injectable({ providedIn: 'root' })
export class TreinoService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);
  private readonly apiUrl = environment.apiLocalUrl;

  private async headersComSessao(): Promise<HttpHeaders> {
    const token = await this.authService.obterAccessToken();
    return token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : new HttpHeaders();
  }

  private isUnauthorized(cause: unknown): boolean {
    return cause instanceof HttpErrorResponse && (cause.status === 401 || cause.status === 403);
  }

  private mensagemDeErro(cause: unknown): string {
    if (cause instanceof HttpErrorResponse) {
      if (cause.status === 0) {
        return 'Não foi possível conectar ao servidor. Verifique sua conexão.';
      }
      const detalhe = (cause.error as { detail?: string } | null)?.detail;
      if (detalhe) {
        return detalhe;
      }
    }
    return cause instanceof Error ? cause.message : 'Erro desconhecido';
  }

  /** Com `sessaoId`, traz só os exercícios do bloco de prática daquela sessão
   * ainda não respondidos — é o caminho reto entre o começo e o fim dela. */
  async getFila(sessaoId?: string | null): Promise<FilaTreinoResult> {
    try {
      const url = sessaoId
        ? `${this.apiUrl}/treino/fila?sessao_id=${encodeURIComponent(sessaoId)}`
        : `${this.apiUrl}/treino/fila`;
      const fila = await firstValueFrom(
        this.http.get<FilaTreino>(url, {
          headers: await this.headersComSessao()
        })
      );
      return { success: true, fila };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        return { success: false, error: MENSAGEM_SESSAO_EXPIRADA, sessaoExpirada: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  async responder(
    filaId: number,
    lance: string,
    segundosGastos?: number | null
  ): Promise<ResponderTreinoResult> {
    try {
      const resultado = await firstValueFrom(
        this.http.post<ResultadoTreino>(
          `${this.apiUrl}/treino/${filaId}/responder`,
          { lance, segundos_gastos: segundosGastos ?? null },
          { headers: await this.headersComSessao() }
        )
      );
      return { success: true, resultado };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        return { success: false, error: MENSAGEM_SESSAO_EXPIRADA, sessaoExpirada: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  /**
   * Joga um lance dentro do trecho de um card de EROSAO (D-66).
   *
   * Não manda posição nenhuma: a do servidor vem do replay do histórico
   * gravado, e é a única que vale. Cada chamada vale um lance do jogador mais
   * a resposta do motor.
   */
  async jogarTrecho(filaId: number, lance: string): Promise<JogarTrechoResult> {
    try {
      const resultado = await firstValueFrom(
        this.http.post<ResultadoTrecho>(
          `${this.apiUrl}/treino/${filaId}/trecho`,
          { lance },
          { headers: await this.headersComSessao() }
        )
      );
      return { success: true, resultado };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        return { success: false, error: MENSAGEM_SESSAO_EXPIRADA, sessaoExpirada: true };
      }
      if (cause instanceof HttpErrorResponse && cause.status === 409) {
        return {
          success: false,
          error: this.mensagemDeErro(cause),
          trechoReiniciado: true
        };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  /** Quantos exercícios de catálogo existem por categoria (D-53). Serve para a
   * tela não oferecer "Focar" numa categoria que não tem material nenhum. */
  async disponibilidadeFoco(): Promise<DisponibilidadeFocoResult> {
    try {
      const resposta = await firstValueFrom(
        this.http.get<{ por_categoria: Record<string, number> }>(
          `${this.apiUrl}/treino/foco/disponibilidade`,
          { headers: await this.headersComSessao() }
        )
      );
      return { success: true, porCategoria: resposta.por_categoria };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        return { success: false, error: MENSAGEM_SESSAO_EXPIRADA, sessaoExpirada: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  /** Injeta exercícios do catálogo tático (D-49) na fila de hoje, focados
   * numa categoria fraca do Hexágono. */
  async focarCategoria(categoria: string): Promise<FocoTreinoResult> {
    try {
      const resposta = await firstValueFrom(
        this.http.post<{ adicionados: number; motivo?: 'sem_catalogo' | 'ja_na_fila' | null }>(
          `${this.apiUrl}/treino/foco/${categoria}`,
          {},
          { headers: await this.headersComSessao() }
        )
      );
      return {
        success: true,
        adicionados: resposta.adicionados,
        motivo: resposta.motivo ?? null
      };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        return { success: false, error: MENSAGEM_SESSAO_EXPIRADA, sessaoExpirada: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }
}
