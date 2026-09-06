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
}
