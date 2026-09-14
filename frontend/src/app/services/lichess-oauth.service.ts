import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

export interface LichessOauthStatus {
  conectado: boolean;
  expires_at?: string | null;
}

export interface IniciarLichessOauthResponse {
  url_autorizacao: string;
  expira_em: string;
}

@Injectable({
  providedIn: 'root'
})
export class LichessOauthService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);

  private async headersComSessao(): Promise<HttpHeaders> {
    const token = await this.authService.obterAccessToken();
    return token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : new HttpHeaders();
  }

  /** Consulta se o usuário logado tem token OAuth do Lichess ativo (D-35). */
  async obterStatus(): Promise<LichessOauthStatus> {
    try {
      const headers = await this.headersComSessao();
      return await firstValueFrom(
        this.http.get<LichessOauthStatus>(
          `${environment.apiLocalUrl}/lichess/oauth/status`,
          { headers }
        )
      );
    } catch {
      return { conectado: false };
    }
  }

  /** Inicia o fluxo PKCE e retorna a URL de autorização do Lichess. */
  async iniciarConexao(): Promise<string> {
    const headers = await this.headersComSessao();
    const resposta = await firstValueFrom(
      this.http.post<IniciarLichessOauthResponse>(
        `${environment.apiLocalUrl}/lichess/oauth/iniciar`,
        {},
        { headers }
      )
    );
    return resposta.url_autorizacao;
  }

  /** Remove o token OAuth do Lichess do usuário logado. */
  async desconectar(): Promise<boolean> {
    try {
      const headers = await this.headersComSessao();
      await firstValueFrom(
        this.http.post(
          `${environment.apiLocalUrl}/lichess/oauth/desconectar`,
          {},
          { headers }
        )
      );
      return true;
    } catch {
      return false;
    }
  }
}

