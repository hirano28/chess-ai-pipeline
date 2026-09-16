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
export interface ItemFilaTreino {
  fila_id: number;
  fen: string;
  origem: 'lance_critico' | 'exercicio_tatico';
  numero_lance: number | null;
  cor_jogada: string | null;
  data_partida: string | null;
  plataforma: string | null;
  categoria: string | null;
  repeticoes: number;
  total_revisoes: number;
}

export interface FilaTreino {
  itens: ItemFilaTreino[];
  feitas_hoje: number;
  total_hoje: number;
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
  proxima_revisao_data: string;
  repeticoes: number;
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

  async getFila(): Promise<FilaTreinoResult> {
    try {
      const fila = await firstValueFrom(
        this.http.get<FilaTreino>(`${this.apiUrl}/treino/fila`, {
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

  async responder(filaId: number, lance: string): Promise<ResponderTreinoResult> {
    try {
      const resultado = await firstValueFrom(
        this.http.post<ResultadoTreino>(
          `${this.apiUrl}/treino/${filaId}/responder`,
          { lance },
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
