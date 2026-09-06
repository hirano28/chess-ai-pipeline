import { Injectable } from '@angular/core';
import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { environment } from '../../environments/environment';

export interface AnaliseHexagonoMetricas {
  frequencia_por_categoria?: Record<string, number>;
  gravidade_media_por_categoria?: Record<string, number>;
  [key: string]: unknown;
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
}
