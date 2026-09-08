import { Injectable } from '@angular/core';
import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { environment } from '../../environments/environment';

export interface AnaliseHexagonoMetricas {
  frequencia_por_categoria?: Record<string, number>;
  gravidade_media_por_categoria?: Record<string, number>;
  [key: string]: unknown;
}

export interface ModuloTreino {
  nome: string;
  duracao_min: number;
  conteudo: string;
  livro?: string;
  capitulo?: string;
  pagina_aprox?: number;
}

export interface SprintTreinoPayload {
  titulo?: string;
  duracao_total_min?: number;
  modulos: ModuloTreino[];
}

export interface SessaoTreino {
  id: string;
  diagnostico_gargalo: string;
  modulos: ModuloTreino[] | SprintTreinoPayload;
  data_prescrita: string;
  data_concluida: string | null;
}

export interface AtualizacaoSessaoResult {
  success: boolean;
  dataConcluida?: string;
  error?: string;
}

export interface AnaliseHexagonoCompleta {
  narrativa: string | null;
  gargalo_sistemico_atual: string | null;
  data_analise: string;
}

export interface PerguntaPendente {
  id: string;
  perguntaTexto: string;
  partidaId: string;
  numeroLance: number;
  numeroLanceFim: number | null;
  lanceNotacao: string | null;
  tipoEvento: string;
  dataPartida: string | null;
  corJogada: string | null;
}

export interface RespostaPerguntaResult {
  success: boolean;
  error?: string;
}

/** Normaliza embeds do PostgREST, que podem vir como objeto único ou array. */
function primeiroOuProprio<T>(valor: T | T[] | null | undefined): T | null {
  if (Array.isArray(valor)) {
    return valor[0] ?? null;
  }
  return valor ?? null;
}

@Injectable({ providedIn: 'root' })
export class SupabaseService {
  private readonly client: SupabaseClient;

  constructor() {
    this.client = createClient(
      environment.supabaseUrl,
      environment.supabaseAnonKey
    );
  }

  async getUltimaAnaliseHexagono(): Promise<AnaliseHexagonoMetricas | null> {
    const { data, error } = await this.client
      .from('analises_hexagono')
      .select('metricas')
      .order('data_analise', { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error) {
      throw new Error(`Não foi possível carregar a análise: ${error.message}`);
    }

    return (data?.metricas as AnaliseHexagonoMetricas | null) ?? null;
  }

  async getUltimaAnaliseCompleta(): Promise<AnaliseHexagonoCompleta | null> {
    const { data, error } = await this.client
      .from('analises_hexagono')
      .select('narrativa, gargalo_sistemico_atual, data_analise')
      .order('data_analise', { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error) {
      throw new Error(`Não foi possível carregar a narrativa: ${error.message}`);
    }

    return (data as AnaliseHexagonoCompleta | null) ?? null;
  }

  async getSessoesTreino(): Promise<SessaoTreino[]> {
    const { data, error } = await this.client
      .from('sessoes_treino')
      .select('id, diagnostico_gargalo, modulos, data_prescrita, data_concluida')
      .order('data_prescrita', { ascending: false });

    if (error) {
      throw new Error(`Não foi possível carregar as sessões: ${error.message}`);
    }

    return (data ?? []).map((sessao) => ({
      ...sessao,
      id: String(sessao.id)
    })) as SessaoTreino[];
  }

  async marcarSessaoConcluida(id: string): Promise<AtualizacaoSessaoResult> {
    const dataConcluida = new Date().toISOString();
    const { error } = await this.client
      .from('sessoes_treino')
      .update({ data_concluida: dataConcluida })
      .eq('id', id);

    if (error) {
      return { success: false, error: error.message };
    }

    return { success: true, dataConcluida };
  }

  async getPerguntasPendentes(): Promise<PerguntaPendente[]> {
    const { data, error } = await this.client
      .from('perguntas_pendentes')
      .select(
        'id, pergunta_texto, created_at, ' +
          'lances_criticos(numero_lance, numero_lance_fim, lance_notacao, tipo_evento, partida_id, ' +
          'partidas(id, data_partida, cor_jogada))'
      )
      .eq('status', 'PENDENTE')
      .order('created_at', { ascending: false });

    if (error) {
      throw new Error(`Não foi possível carregar as perguntas pendentes: ${error.message}`);
    }

    return (data ?? [])
      .map((row: any) => {
        const lance = primeiroOuProprio(row.lances_criticos);
        if (!lance) {
          return null;
        }
        const partida = primeiroOuProprio(lance.partidas);
        return {
          id: String(row.id),
          perguntaTexto: row.pergunta_texto,
          partidaId: partida ? String(partida.id) : String(lance.partida_id),
          numeroLance: lance.numero_lance,
          numeroLanceFim: lance.numero_lance_fim ?? null,
          lanceNotacao: lance.lance_notacao ?? null,
          tipoEvento: lance.tipo_evento,
          dataPartida: partida?.data_partida ?? null,
          corJogada: partida?.cor_jogada ?? null
        } satisfies PerguntaPendente;
      })
      .filter((item: PerguntaPendente | null): item is PerguntaPendente => item !== null);
  }

  async responderPergunta(perguntaId: string, texto: string): Promise<RespostaPerguntaResult> {
    const { data: pergunta, error: fetchError } = await this.client
      .from('perguntas_pendentes')
      .select('id, lances_criticos(partida_id, numero_lance)')
      .eq('id', perguntaId)
      .single();

    if (fetchError || !pergunta) {
      return { success: false, error: fetchError?.message ?? 'Pergunta não encontrada.' };
    }

    const lance = primeiroOuProprio((pergunta as any).lances_criticos);
    if (!lance) {
      return { success: false, error: 'Lance relacionado à pergunta não foi encontrado.' };
    }

    const { error: insertError } = await this.client.from('anotacoes_pensamento').upsert(
      {
        partida_id: lance.partida_id,
        numero_lance: lance.numero_lance,
        texto_pensamento: texto,
        origem: 'PERGUNTA_RETROATIVA'
      },
      { onConflict: 'partida_id,numero_lance' }
    );

    if (insertError) {
      return { success: false, error: insertError.message };
    }

    const { error: updateError } = await this.client
      .from('perguntas_pendentes')
      .update({ status: 'RESPONDIDA' })
      .eq('id', perguntaId);

    if (updateError) {
      return { success: false, error: updateError.message };
    }

    return { success: true };
  }
}
