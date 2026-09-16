import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

/**
 * Um passo executável da sessão de treino focado (D-54).
 *
 * `estudo` vem dos módulos que o Agente 3 prescreveu (livro/capítulo/página) e
 * fecha quando o usuário marca como lido — é leitura, o sistema não tem como
 * verificar. `pratica` é montado pelo backend com exercícios reais da
 * categoria do gargalo e fecha sozinho quando eles são respondidos no Treino
 * Diário; é ele que dá um fim objetivo à sessão.
 */
export interface BlocoSessao {
  indice: number;
  tipo: 'estudo' | 'pratica';
  nome: string;
  conteudo: string | null;
  duracao_min: number | null;
  livro: string | null;
  capitulo: string | null;
  pagina_aprox: number | null;
  concluido: boolean;
  categoria: string | null;
  exercicios_feitos: number | null;
  exercicios_total: number | null;
}

export interface ExecucaoSessao {
  sessao_id: string;
  titulo: string;
  categoria_foco: string | null;
  data_prescrita: string;
  data_iniciada: string | null;
  data_concluida: string | null;
  duracao_total_min: number;
  blocos: BlocoSessao[];
  concluida: boolean;
}

export interface ExecucaoSessaoResult {
  success: boolean;
  execucao?: ExecucaoSessao;
  error?: string;
  sessaoExpirada?: boolean;
}

const MENSAGEM_SESSAO_EXPIRADA = 'Sua sessão expirou. Faça login novamente.';

@Injectable({ providedIn: 'root' })
export class SessaoService {
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

  private async executar(
    requisicao: (headers: HttpHeaders) => Promise<ExecucaoSessao>
  ): Promise<ExecucaoSessaoResult> {
    try {
      const execucao = await requisicao(await this.headersComSessao());
      return { success: true, execucao };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        return { success: false, error: MENSAGEM_SESSAO_EXPIRADA, sessaoExpirada: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  async obterExecucao(sessaoId: string): Promise<ExecucaoSessaoResult> {
    return this.executar((headers) =>
      firstValueFrom(
        this.http.get<ExecucaoSessao>(`${this.apiUrl}/sessoes/${sessaoId}/execucao`, {
          headers
        })
      )
    );
  }

  /** Abre a sessão e enfileira os exercícios do bloco de prática. Idempotente
   * no backend: reabrir não empilha mais exercícios. */
  async iniciar(sessaoId: string): Promise<ExecucaoSessaoResult> {
    return this.executar((headers) =>
      firstValueFrom(
        this.http.post<ExecucaoSessao>(
          `${this.apiUrl}/sessoes/${sessaoId}/iniciar`,
          {},
          { headers }
        )
      )
    );
  }

  async concluirBloco(sessaoId: string, indice: number): Promise<ExecucaoSessaoResult> {
    return this.executar((headers) =>
      firstValueFrom(
        this.http.post<ExecucaoSessao>(
          `${this.apiUrl}/sessoes/${sessaoId}/blocos/${indice}/concluir`,
          {},
          { headers }
        )
      )
    );
  }
}
