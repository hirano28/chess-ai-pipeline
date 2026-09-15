import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

export interface ResumoPuzzles {
  total: number;
  acertos: number;
  erros: number;
  taxa_acerto_pct: number;
  rating_medio: number | null;
  rating_min: number | null;
  rating_max: number | null;
}

export interface TemaPuzzleStat {
  slug: string;
  nome: string;
  descricao: string;
  categoria: string;
  total: number;
  acertos: number;
  taxa_acerto_pct: number;
  url_treino: string;
}

export interface DiagnosticoGap {
  titulo: string;
  resumo_executivo: string;
  analise_comparativa: string;
  sugestao_foco: string;
}

export interface InsightsPuzzles {
  resumo: ResumoPuzzles;
  temas_vulneraveis: TemaPuzzleStat[];
  temas_dominados: TemaPuzzleStat[];
  todos_os_temas: TemaPuzzleStat[];
  diagnostico_gap: DiagnosticoGap;
}

export interface InsightsPuzzlesResult {
  success: boolean;
  dados?: InsightsPuzzles;
  error?: string;
  sessaoExpirada?: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class PuzzlesService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);
  private readonly apiUrl = environment.apiLocalUrl;

  private async headersComSessao(): Promise<HttpHeaders> {
    const token = await this.authService.obterAccessToken();
    return token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : new HttpHeaders();
  }

  async getInsightsPuzzles(): Promise<InsightsPuzzlesResult> {
    try {
      const headers = await this.headersComSessao();
      const dados = await firstValueFrom(
        this.http.get<InsightsPuzzles>(`${this.apiUrl}/insights/puzzles`, {
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
          : 'Falha ao carregar insights de puzzles';
      return { success: false, error: msg };
    }
  }
}

