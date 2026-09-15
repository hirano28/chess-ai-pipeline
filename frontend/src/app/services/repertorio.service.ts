import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

export interface TaxaVitoriaCorItem {
  total: number;
  vitorias: number;
  taxa_vitoria_pct: number;
}

export interface MetricasAberturaCorItem {
  abertura_normalizada: string;
  cor_jogada: string;
  total: number;
  vitorias: number;
  taxa_vitoria_pct: number;
  precisao_media_abertura?: number | null;
  precisao_media_meiojogo?: number | null;
  precisao_media_final?: number | null;
}

export interface LancePicoAberturaItem {
  abertura_normalizada: string;
  total_eventos: number;
  lance_medio: number;
  lance_mediano: number;
}

export interface InsightsRepertorio {
  taxa_vitoria_por_cor: {
    BRANCAS?: TaxaVitoriaCorItem;
    PRETAS?: TaxaVitoriaCorItem;
    [key: string]: TaxaVitoriaCorItem | undefined;
  };
  por_abertura_e_cor: MetricasAberturaCorItem[];
  lance_pico_por_abertura: LancePicoAberturaItem[];
  categorias_por_abertura: Record<string, Record<string, number>>;
}

export interface InsightsRepertorioResult {
  success: boolean;
  dados?: InsightsRepertorio;
  error?: string;
  sessaoExpirada?: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class RepertorioService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);
  private readonly apiUrl = environment.apiLocalUrl;

  private async headersComSessao(): Promise<HttpHeaders> {
    const token = await this.authService.obterAccessToken();
    return token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : new HttpHeaders();
  }

  async getInsightsRepertorio(): Promise<InsightsRepertorioResult> {
    try {
      const headers = await this.headersComSessao();
      const dados = await firstValueFrom(
        this.http.get<InsightsRepertorio>(`${this.apiUrl}/insights/repertorio`, {
          headers
        })
      );
      return { success: true, dados };
    } catch (error) {
      if (
        error instanceof HttpErrorResponse &&
        (error.status === 401 || error.status === 403)
      ) {
        return {
          success: false,
          sessaoExpirada: true,
          error: 'Sua sessão expirou. Faça login novamente.'
        };
      }
      const msg =
        error instanceof Error
          ? error.message
          : 'Falha ao carregar insights de repertório';
      return { success: false, error: msg };
    }
  }
}

