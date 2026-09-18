import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

export interface FonteBiblioteca {
  livro: string;
  capitulo?: string | null;
  pagina_aprox?: number | null;
}

export interface RespostaBiblioteca {
  id?: string | null;
  pergunta: string;
  resposta: string;
  fontes: FonteBiblioteca[];
}

export interface ConsultaBibliotecaRecenteItem {
  id: string;
  pergunta: string;
  resposta: { resposta: string; fontes: FonteBiblioteca[] };
  created_at: string;
}

export interface ResultadoBiblioteca {
  success: boolean;
  dados?: RespostaBiblioteca;
  error?: string;
  sessaoExpirada?: boolean;
}

export interface ResultadoHistoricoBiblioteca {
  success: boolean;
  dados?: ConsultaBibliotecaRecenteItem[];
  error?: string;
}

/** Formata uma fonte como o leitor a procuraria na estante (D-81). */
export function formatarFonte(fonte: FonteBiblioteca): string {
  const partes = [fonte.livro];
  if (fonte.capitulo) {
    partes.push(fonte.capitulo);
  }
  const base = partes.join(' — ');
  return fonte.pagina_aprox != null ? `${base} (pág. ${fonte.pagina_aprox})` : base;
}

@Injectable({ providedIn: 'root' })
export class BibliotecaService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);
  private readonly apiUrl = environment.apiLocalUrl;

  private async headersComSessao(): Promise<HttpHeaders> {
    const token = await this.authService.obterAccessToken();
    return token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : new HttpHeaders();
  }

  async consultar(pergunta: string): Promise<ResultadoBiblioteca> {
    try {
      const headers = await this.headersComSessao();
      const dados = await firstValueFrom(
        this.http.post<RespostaBiblioteca>(
          `${this.apiUrl}/biblioteca/consultar`,
          { pergunta },
          { headers }
        )
      );
      return { success: true, dados };
    } catch (error) {
      if (error instanceof HttpErrorResponse && error.status === 401) {
        return {
          success: false,
          sessaoExpirada: true,
          error: 'Sua sessão expirou. Entre de novo para continuar.'
        };
      }
      const msg =
        error instanceof HttpErrorResponse && error.error?.detail
          ? error.error.detail
          : error instanceof Error
            ? error.message
            : 'Falha ao consultar a biblioteca';
      return { success: false, error: msg };
    }
  }

  async listarRecentes(): Promise<ResultadoHistoricoBiblioteca> {
    try {
      const headers = await this.headersComSessao();
      const dados = await firstValueFrom(
        this.http.get<ConsultaBibliotecaRecenteItem[]>(
          `${this.apiUrl}/biblioteca/recentes`,
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
            : 'Falha ao carregar o histórico da biblioteca';
      return { success: false, error: msg };
    }
  }
}
