import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders, HttpParams } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

export interface CandidatoLivro {
  uci?: string;
  san?: string;
  total_partidas: number;
  white: number;
  draws: number;
  black: number;
}

export interface StatsLivro {
  white: number;
  draws: number;
  black: number;
  total: number;
}

export interface TeoriaAbertura {
  sucesso: boolean;
  disponivel: boolean;
  ficou_no_livro?: boolean;
  ply_saida?: number;
  numero_lance_saida?: number;
  cor_saida?: 'BRANCAS' | 'PRETAS';
  quem_saiu?: 'JOGADOR' | 'OPONENTE';
  lance_uci?: string;
  lance_san?: string;
  nome_abertura?: string;
  eco?: string;
  stats_ultimo_livro?: StatsLivro;
  candidatos_recomendados?: CandidatoLivro[];
  motivo?: string;
}

export interface TeoriaAberturaResult {
  success: boolean;
  dados?: TeoriaAbertura;
  error?: string;
}

export interface MelhorLanceSyzygy {
  uci: string;
  san: string;
  categoria: string;
  dtz?: number;
  dtm?: number;
}

export interface SyzygyAvaliacao {
  elegivel_syzygy: boolean;
  num_pecas?: number;
  categoria_antes?: string;
  categoria_lance_jogado?: string;
  dtz?: number;
  dtm?: number;
  eh_blunder_teorico?: boolean;
  tipo_erro_final?: string;
  veredito_pt?: string;
  melhores_lances?: MelhorLanceSyzygy[];
  motivo?: string;
  dados?: any;
}

export interface SyzygyResult {
  success: boolean;
  dados?: SyzygyAvaliacao;
  error?: string;
}

@Injectable({
  providedIn: 'root'
})
export class TeoriaFinaisService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);
  private readonly apiUrl = environment.apiLocalUrl;

  private async headersComSessao(): Promise<HttpHeaders> {
    const token = await this.authService.obterAccessToken();
    return token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : new HttpHeaders();
  }

  async getTeoriaAbertura(partidaId: string): Promise<TeoriaAberturaResult> {
    try {
      const headers = await this.headersComSessao();
      const dados = await firstValueFrom(
        this.http.get<TeoriaAbertura>(
          `${this.apiUrl}/partidas/${encodeURIComponent(partidaId)}/teoria-abertura`,
          { headers }
        )
      );
      return { success: true, dados };
    } catch (error) {
      const msg =
        error instanceof HttpErrorResponse && error.error?.detail
          ? error.error.detail
          : error instanceof Error
            ? error.message
            : 'Falha ao consultar teoria de abertura';
      return { success: false, error: msg };
    }
  }

  async getAnaliseSyzygy(fen: string, lance?: string): Promise<SyzygyResult> {
    try {
      const headers = await this.headersComSessao();
      let params = new HttpParams().set('fen', fen);
      if (lance) {
        params = params.set('lance', lance);
      }
      const dados = await firstValueFrom(
        this.http.get<SyzygyAvaliacao>(`${this.apiUrl}/analise/syzygy`, {
          headers,
          params
        })
      );
      return { success: true, dados };
    } catch (error) {
      const msg =
        error instanceof HttpErrorResponse && error.error?.detail
          ? error.error.detail
          : error instanceof Error
            ? error.message
            : 'Falha ao consultar Syzygy Tablebase';
      return { success: false, error: msg };
    }
  }
}

