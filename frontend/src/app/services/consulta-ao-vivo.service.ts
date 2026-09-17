import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

export type CorJogador = 'BRANCAS' | 'PRETAS';
export type PlataformaEspelho = 'LICHESS' | 'CHESSCOM' | 'OUTRA';

/** O que o jogador diz estar pensando. Tudo opcional. */
export interface PensamentoConsulta {
  situacao: string | null;
  candidatos: string | null;
  trava: string | null;
}

export interface PlanoConsulta {
  titulo: string;
  explicacao: string;
}

/**
 * Consulta ao vivo (D-67). As três camadas chegam juntas, mas a tela revela
 * uma de cada vez: a ocultação é pedagógica, não uma barreira de segurança.
 */
export interface ConsultaAoVivo {
  id: string | null;
  partida_espelho_id: string;
  numero_lance: number;
  fen: string;
  cor_jogador: CorJogador;
  lances_san: string[];
  pensamento: PensamentoConsulta | null;
  /** Camada 1: pensar. Nenhum lance concreto. */
  camada_pensar: {
    leitura_da_posicao: string;
    sobre_o_seu_raciocinio: string | null;
    perguntas_guia: string[];
    planos: PlanoConsulta[];
  };
  /** Camada 2: candidatos em ordem alfabética, sem dizer qual é o melhor. */
  camada_ideias: { ideias: { lance: string; ideia: string | null }[] };
  /** Camada 3: o veredito do motor. */
  camada_motor: {
    melhor_lance: string | null;
    avaliacao: string;
    win_percent_jogador: number;
    linhas: { lance: string; avaliacao: string; sequencia: string[] }[];
  };
  gerado_por: 'gemini' | 'fallback';
  consultas_restantes: number;
  criado_em: string | null;
}

export interface NovaConsulta {
  partida_espelho_id: string;
  lances: string[];
  fen_inicial: string | null;
  cor_jogador: CorJogador;
  plataforma: PlataformaEspelho;
  adversario: string | null;
  pensamento: PensamentoConsulta | null;
}

export interface ResultadoServico<T> {
  success: boolean;
  dados?: T;
  error?: string;
  sessaoExpirada?: boolean;
  /** 429: acabaram as consultas desta partida ou do dia. */
  limiteAtingido?: boolean;
}

const MENSAGEM_SESSAO_EXPIRADA = 'Sua sessão expirou. Faça login novamente.';

@Injectable({ providedIn: 'root' })
export class ConsultaAoVivoService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);
  private readonly apiUrl = environment.apiLocalUrl;

  private async headers(): Promise<HttpHeaders> {
    const token = await this.authService.obterAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }

  private falha<T>(cause: unknown, fallback: string): ResultadoServico<T> {
    if (cause instanceof HttpErrorResponse) {
      if (cause.status === 401 || cause.status === 403) {
        return { success: false, error: MENSAGEM_SESSAO_EXPIRADA, sessaoExpirada: true };
      }
      if (cause.status === 0) {
        return { success: false, error: 'Não foi possível conectar ao servidor.' };
      }
      const detalhe = (cause.error as { detail?: string } | null)?.detail;
      return {
        success: false,
        error: detalhe ?? fallback,
        limiteAtingido: cause.status === 429
      };
    }
    return { success: false, error: cause instanceof Error ? cause.message : fallback };
  }

  /** Se esta sessão pode usar a feature. Qualquer falha conta como "não". */
  async acesso(): Promise<{ habilitado: boolean; limitePorPartida: number }> {
    try {
      const resposta = await firstValueFrom(
        this.http.get<{ habilitado: boolean; limite_por_partida: number }>(
          `${this.apiUrl}/consulta-ao-vivo/acesso`,
          { headers: await this.headers() }
        )
      );
      return { habilitado: resposta.habilitado, limitePorPartida: resposta.limite_por_partida };
    } catch {
      return { habilitado: false, limitePorPartida: 0 };
    }
  }

  async consultar(consulta: NovaConsulta): Promise<ResultadoServico<ConsultaAoVivo>> {
    try {
      const dados = await firstValueFrom(
        this.http.post<ConsultaAoVivo>(`${this.apiUrl}/consulta-ao-vivo`, consulta, {
          headers: await this.headers()
        })
      );
      return { success: true, dados };
    } catch (cause: unknown) {
      return this.falha(cause, 'Não foi possível consultar a posição.');
    }
  }

  async listarDaPartida(partidaEspelhoId: string): Promise<ResultadoServico<ConsultaAoVivo[]>> {
    try {
      const dados = await firstValueFrom(
        this.http.get<ConsultaAoVivo[]>(
          `${this.apiUrl}/consulta-ao-vivo/partida/${encodeURIComponent(partidaEspelhoId)}`,
          { headers: await this.headers() }
        )
      );
      return { success: true, dados };
    } catch (cause: unknown) {
      return this.falha(cause, 'Não foi possível carregar as consultas desta partida.');
    }
  }
}
