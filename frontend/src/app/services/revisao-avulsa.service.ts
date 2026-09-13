import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { AuthLocalService } from './auth-local.service';
import { AuthService } from './auth.service';

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
  /** Mesmo lance em notação portuguesa (C/T/D/R/B), como o backend o entendeu. */
  lance_interpretado: string;
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
  /** 1º lance do jogador em notação portuguesa, como foi entendido. */
  lance_interpretado: string;
  avaliacoes: AvaliacaoSequenciaItem[];
  resumo_geral: string | null;
}

export interface RevisarAvulsaResult {
  success: boolean;
  resultado?: ResultadoRevisaoAvulsa;
  error?: string;
  chaveInvalida?: boolean;
}

export interface ReconhecerPosicaoResult {
  success: boolean;
  fen?: string;
  error?: string;
  chaveInvalida?: boolean;
}

export interface ResolverFenResult {
  success: boolean;
  fen?: string;
  error?: string;
  chaveInvalida?: boolean;
}

export interface SalvarAvulsaResult {
  success: boolean;
  /** id da linha criada em revisao_exercicio_avulso; usado para marcar o exercício como "ativo" no histórico. */
  id?: string;
  error?: string;
  chaveInvalida?: boolean;
}

export interface RevisaoAvulsaRecenteItem {
  id: string;
  fen: string;
  lance_jogado: string;
  melhor_lance: string | null;
  queda_win_percent: number | null;
  texto_pensamento: string | null;
  qualidade_lance: string | null;
  qualidade_raciocinio: string | null;
  feedback_texto: string | null;
  created_at: string | null;
}

export interface ListarRevisoesAvulsasRecentesResult {
  success: boolean;
  itens?: RevisaoAvulsaRecenteItem[];
  error?: string;
  chaveInvalida?: boolean;
}

export interface AvaliacaoObjetiva {
  score_cp: number;
  mate: number | null;
  win_percent: number;
  lado_vencedor: string;
  descricao: string;
}

export interface LinhaTaticaItem {
  lance: string;
  avaliacao: string;
  pv_san: string[];
}

export interface RefutacaoDefesaItem {
  defesa: string;
  refutacao_linha: string[];
  detalhes: string;
}

export interface MaterialInfo {
  pontos_brancas: number;
  pontos_pretas: number;
  saldo_brancas: number;
  descricao: string;
  par_bispos_brancas: boolean;
  par_bispos_pretas: boolean;
}

export interface SegurancaReiInfo {
  casa: string;
  em_xeque: boolean;
  casas_vizinhas_atacadas: number;
  roque_disponivel: boolean;
  resumo: string;
}

export interface ElementosPosicionais {
  material: MaterialInfo;
  pecas_indefesas: {
    BRANCAS: string[];
    PRETAS: string[];
  };
  pecas_cravadas: {
    BRANCAS: string[];
    PRETAS: string[];
  };
  seguranca_rei: {
    BRANCAS?: SegurancaReiInfo;
    PRETAS?: SegurancaReiInfo;
  };
  ameacas_imediatas: {
    cheques: string[];
    capturas: string[];
  };
}

export interface ExplicacaoPosicaoData {
  veredito: string;
  ameaca_concreta: string;
  o_que_parece_bom_mas_falha: string;
  plano_conversao: string;
  resumo_didatico: string;
}

export interface ResultadoExplicadorPosicao {
  /** id da linha criada em explicacoes_posicao; ausente se a persistência falhar no servidor. */
  id?: string | null;
  fen: string;
  lado_a_jogar: string;
  lado_analisado: string;
  avaliacao: AvaliacaoObjetiva;
  linhas_taticas: LinhaTaticaItem[];
  refutacao_defesa?: RefutacaoDefesaItem | null;
  elementos_posicionais: ElementosPosicionais;
  explicacao: ExplicacaoPosicaoData;
}

export interface ExplicarPosicaoResult {
  success: boolean;
  resultado?: ResultadoExplicadorPosicao;
  error?: string;
  chaveInvalida?: boolean;
}

export interface ExplicacaoPosicaoRecenteItem {
  id: string;
  fen: string;
  lado_analisado: string | null;
  created_at: string | null;
  /** Resposta completa (mesmo shape de ResultadoExplicadorPosicao) - dá pra restaurar sem outra chamada. */
  resultado: ResultadoExplicadorPosicao;
}

export interface ListarExplicacoesRecentesResult {
  success: boolean;
  itens?: ExplicacaoPosicaoRecenteItem[];
  error?: string;
  chaveInvalida?: boolean;
}

export interface PontoCriticoPartida {
  numero_lance: number;
  tipo_evento: string;
  tags_falha: string[];
}

export interface ResumoPartidaData {
  narrativa: string;
  pontos_criticos: PontoCriticoPartida[];
  momento_chave_estrategico: string | null;
}

export interface StatusPartidaResponse {
  partida_id: string;
  external_id?: string | null;
  status: 'pendente' | 'processando' | 'concluido' | 'falhou';
  resumo: ResumoPartidaData | null;
}

export interface SubmeterPartidaResult {
  success: boolean;
  partidaId?: string;
  externalId?: string;
  error?: string;
  chaveInvalida?: boolean;
}

export interface ConsultarStatusPartidaResult {
  success: boolean;
  dados?: StatusPartidaResponse;
  error?: string;
  chaveInvalida?: boolean;
}

export interface PartidaRecenteItem {
  partida_id: string;
  external_id?: string | null;
  status: 'pendente' | 'processando' | 'concluido' | 'falhou';
  cor_jogada?: string | null;
  resultado?: string | null;
  eco_abertura?: string | null;
  data_partida?: string | null;
  created_at?: string | null;
  jogadores?: string | null;
}

export interface ListarPartidasRecentesResult {
  success: boolean;
  partidas?: PartidaRecenteItem[];
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
  private readonly authService = inject(AuthService);

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

  /** Envia a foto de um diagrama para reconhecimento de posição via Gemini (visão). */
  async reconhecerPosicao(imagem: File): Promise<ReconhecerPosicaoResult> {
    try {
      const formData = new FormData();
      formData.append('imagem', imagem, imagem.name);
      const resposta = await firstValueFrom(
        this.http.post<{ fen: string }>(
          `${environment.apiLocalUrl}/reconhecer-posicao`,
          formData,
          { headers: this.headersComChave() }
        )
      );
      return { success: true, fen: resposta.fen };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        this.authLocalService.clearKey();
        return { success: false, error: MENSAGEM_CHAVE_INVALIDA, chaveInvalida: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  /**
   * Resolve FEN/PGN para o FEN final - só parsing local (GET /resolver-fen), sem
   * Gemini nem Stockfish. Usado para a pré-visualização do tabuleiro em tempo real.
   */
  async resolverFen(posicao: string): Promise<ResolverFenResult> {
    try {
      const resposta = await firstValueFrom(
        this.http.get<{ fen: string }>(`${environment.apiLocalUrl}/resolver-fen`, {
          params: { posicao },
          headers: this.headersComChave()
        })
      );
      return { success: true, fen: resposta.fen };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        this.authLocalService.clearKey();
        return { success: false, error: MENSAGEM_CHAVE_INVALIDA, chaveInvalida: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  async explicarPosicao(
    posicao: string,
    lado?: string | null
  ): Promise<ExplicarPosicaoResult> {
    try {
      const payload: { posicao: string; lado?: string } = { posicao };
      if (lado && lado.trim()) {
        payload.lado = lado.trim();
      }
      const resultado = await firstValueFrom(
        this.http.post<ResultadoExplicadorPosicao>(
          `${environment.apiLocalUrl}/explicar-posicao`,
          payload,
          { headers: await this.headersComChaveEAuth() }
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

  async submeterPartidaPgn(
    pgn: string,
    cor?: string | null
  ): Promise<SubmeterPartidaResult> {
    try {
      const payload: { pgn: string; cor?: string | null } = { pgn };
      if (cor && cor.trim() && cor !== 'AUTO') {
        payload.cor = cor.trim();
      }
      const resposta = await firstValueFrom(
        this.http.post<{ partida_id: string; external_id: string }>(
          `${environment.apiLocalUrl}/analisar-pgn`,
          payload,
          { headers: await this.headersComChaveEAuth() }
        )
      );
      return {
        success: true,
        partidaId: resposta.partida_id,
        externalId: resposta.external_id
      };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        this.authLocalService.clearKey();
        return { success: false, error: MENSAGEM_CHAVE_INVALIDA, chaveInvalida: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  async consultarStatusPartida(
    partidaId: string
  ): Promise<ConsultarStatusPartidaResult> {
    try {
      const dados = await firstValueFrom(
        this.http.get<StatusPartidaResponse>(
          `${environment.apiLocalUrl}/partidas/${partidaId}/resumo`,
          { headers: this.headersComChave() }
        )
      );
      return { success: true, dados };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        this.authLocalService.clearKey();
        return { success: false, error: MENSAGEM_CHAVE_INVALIDA, chaveInvalida: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  async listarPartidasRecentes(limite: number = 20): Promise<ListarPartidasRecentesResult> {
    try {
      const partidas = await firstValueFrom(
        this.http.get<PartidaRecenteItem[]>(
          `${environment.apiLocalUrl}/partidas/recentes?limite=${limite}`,
          { headers: this.headersComChave() }
        )
      );
      return { success: true, partidas };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        this.authLocalService.clearKey();
        return { success: false, error: MENSAGEM_CHAVE_INVALIDA, chaveInvalida: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  /** Histórico de explicações de posição já geradas (mesmo padrão de listarPartidasRecentes). */
  async listarExplicacoesRecentes(limite: number = 20): Promise<ListarExplicacoesRecentesResult> {
    try {
      const itens = await firstValueFrom(
        this.http.get<ExplicacaoPosicaoRecenteItem[]>(
          `${environment.apiLocalUrl}/explicacoes-posicao/recentes?limite=${limite}`,
          { headers: this.headersComChave() }
        )
      );
      return { success: true, itens };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        this.authLocalService.clearKey();
        return { success: false, error: MENSAGEM_CHAVE_INVALIDA, chaveInvalida: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  /** Histórico de exercícios avulsos já salvos manualmente (mesmo padrão de listarPartidasRecentes). */
  async listarRevisoesAvulsasRecentes(
    limite: number = 20
  ): Promise<ListarRevisoesAvulsasRecentesResult> {
    try {
      const itens = await firstValueFrom(
        this.http.get<RevisaoAvulsaRecenteItem[]>(
          `${environment.apiLocalUrl}/revisoes-avulsas/recentes?limite=${limite}`,
          { headers: this.headersComChave() }
        )
      );
      return { success: true, itens };
    } catch (cause: unknown) {
      if (this.isUnauthorized(cause)) {
        this.authLocalService.clearKey();
        return { success: false, error: MENSAGEM_CHAVE_INVALIDA, chaveInvalida: true };
      }
      return { success: false, error: this.mensagemDeErro(cause) };
    }
  }

  async reprocessarPartida(partidaId: string): Promise<SubmeterPartidaResult> {
    try {
      const resposta = await firstValueFrom(
        this.http.post<{ partida_id: string; external_id: string }>(
          `${environment.apiLocalUrl}/partidas/${partidaId}/reprocessar`,
          {},
          { headers: this.headersComChave() }
        )
      );
      return {
        success: true,
        partidaId: resposta.partida_id,
        externalId: resposta.external_id
      };
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
      const resposta = await firstValueFrom(
        this.http.post<{ status: string; id?: string }>(
          `${environment.apiLocalUrl}/revisar-avulso/salvar`,
          { ...avaliacao, fen, texto_pensamento: textoPensamento },
          { headers: await this.headersComChaveEAuth() }
        )
      );
      return { success: true, id: resposta.id };
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

  /**
   * X-API-Key (como sempre, continua controlando o acesso ao endpoint) +
   * Authorization: Bearer quando há sessão Supabase Auth ativa (Fase B.2 —
   * D-17). Os dois convivem: Authorization só refina QUEM é o dono da
   * escrita no banco (user_id real em vez de DEFAULT_USER_ID); quem só usa
   * X-API-Key e nunca criou conta continua gravando exatamente como antes.
   */
  private async headersComChaveEAuth(): Promise<HttpHeaders> {
    let headers = this.headersComChave();
    if (this.authService.autenticado()) {
      const token = await this.authService.obterAccessToken();
      if (token) {
        headers = headers.set('Authorization', `Bearer ${token}`);
      }
    }
    return headers;
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

