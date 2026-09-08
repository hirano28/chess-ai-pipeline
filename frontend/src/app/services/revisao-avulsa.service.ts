import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthLocalService } from './auth-local.service';

export interface CandidatoMotor {
  lance: string;
  avaliacao: string;
}

export interface GuiaPasso {
  numero: number;
  titulo: string;
}

export interface AvaliacaoSequenciaItem {
  indice_na_sequencia: number;
  lance_jogado: string;
  melhor_lance: string | null;
  queda_win_percent: number;
  qualidade_lance: string;
  qualidade_raciocinio: string;
  feedback_texto: string;
  analise_mestre: string;
  top_candidatos: CandidatoMotor[];
  checklist_rotina: Record<string, string>;
}

export interface ResultadoRevisaoAvulsa {
  fen: string;
  lances: string[];
  avaliacoes: AvaliacaoSequenciaItem[];
  resumo_geral: string | null;
}

export interface RevisarAvulsaResult {
  success: boolean;
  resultado?: ResultadoRevisaoAvulsa;
  error?: string;
  chaveInvalida?: boolean;
}

export interface SalvarAvulsaResult {
  success: boolean;
  error?: string;
  chaveInvalida?: boolean;
}

const MENSAGEM_SERVIDOR_OFFLINE =
  'Não foi possível conectar ao servidor local. Confirme que ele está rodando ' +
  '(uvicorn backend.api.api_server:app --port 8000).';

const MENSAGEM_CHAVE_INVALIDA = 'Chave inválida, tente novamente.';

@Injectable({ providedIn: 'root' })
export class RevisaoAvulsaService {
  private readonly http = inject(HttpClient);
  private readonly authLocalService = inject(AuthLocalService);

  async revisar(
    posicao: string,
    lances: string[],
    pensamento: string
  ): Promise<RevisarAvulsaResult> {
    try {
      const resultado = await firstValueFrom(
        this.http.post<ResultadoRevisaoAvulsa>(
          `${environment.apiLocalUrl}/revisar-avulso`,
          { posicao, lances, pensamento },
          { headers: this.headersComChave() }
        )
      );
      return { success: true, resultado };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        this.authLocalService.clearKey();
        return { success: false, error: MENSAGEM_CHAVE_INVALIDA, chaveInvalida: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  async salvar(
    avaliacao: AvaliacaoSequenciaItem,
    fen: string,
    textoPensamento: string
  ): Promise<SalvarAvulsaResult> {
    try {
      await firstValueFrom(
        this.http.post(
          `${environment.apiLocalUrl}/revisar-avulso/salvar`,
          { ...avaliacao, fen, texto_pensamento: textoPensamento },
          { headers: this.headersComChave() }
        )
      );
      return { success: true };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        this.authLocalService.clearKey();
        return { success: false, error: MENSAGEM_CHAVE_INVALIDA, chaveInvalida: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  private headersComChave(): HttpHeaders {
    const chave = this.authLocalService.getKey();
    return chave ? new HttpHeaders({ 'X-API-Key': chave }) : new HttpHeaders();
  }

  /** Busca só os títulos dos 8 passos do guia (endpoint público, sem chave). */
  async guiaPassos(): Promise<GuiaPasso[]> {
    try {
      const resposta = await firstValueFrom(
        this.http.get<{ passos: GuiaPasso[] }>(
          `${environment.apiLocalUrl}/guia-passos`
        )
      );
      return resposta.passos ?? [];
    } catch {
      return [];
    }
  }

  private isUnauthorized(cause: unknown): boolean {
    return cause instanceof HttpErrorResponse && cause.status === 401;
  }

  private mensagemDeErro(cause: unknown): string {
    if (cause instanceof HttpErrorResponse) {
      if (cause.status === 0) {
        return MENSAGEM_SERVIDOR_OFFLINE;
      }
      const detail = (cause.error as { detail?: string } | null)?.detail;
      return detail ?? `Erro ${cause.status} ao comunicar com o servidor local.`;
    }
    return cause instanceof Error ? cause.message : 'Erro desconhecido.';
  }
}

