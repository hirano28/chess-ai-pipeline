import { Injectable, computed, inject, signal } from '@angular/core';
import { User } from '@supabase/supabase-js';
import { SupabaseService } from './supabase.service';

export interface AuthResultado {
  success: boolean;
  error?: string;
  /** true quando o projeto exige confirmação de e-mail (sem sessão ainda). */
  confirmacaoPendente?: boolean;
}

/**
 * Sessão do Supabase Auth (Fase B do multi-tenant — ver D-14/D-15 em DECISOES.md).
 *
 * B.1 é deliberadamente só "login sem travamento": nenhuma policy de RLS foi
 * alterada, então tanto usuário autenticado quanto anônimo continuam
 * enxergando o mesmo dado. Este serviço só existe pra dar a UI de login e
 * preparar o terreno — travar o acesso por usuário é passo futuro.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly supabaseService = inject(SupabaseService);

  readonly usuario = signal<User | null>(null);
  /** true assim que a checagem inicial de sessão (getSession) terminou. */
  readonly sessaoPronta = signal(false);
  readonly autenticado = computed(() => this.usuario() !== null);

  private readonly prontoPromise: Promise<void>;

  constructor() {
    this.prontoPromise = this.inicializar();
  }

  /** Usado pelo guard de rota: espera a sessão salva (se houver) ser restaurada. */
  aguardarSessaoPronta(): Promise<void> {
    return this.prontoPromise;
  }

  private async inicializar(): Promise<void> {
    const { data } = await this.supabaseService.auth.getSession();
    this.usuario.set(data.session?.user ?? null);
    this.sessaoPronta.set(true);

    // Mantém o signal em dia entre abas e após refresh de token, sem precisar
    // que cada componente escute isso manualmente.
    this.supabaseService.auth.onAuthStateChange((_evento, sessao) => {
      this.usuario.set(sessao?.user ?? null);
    });
  }

  async cadastrar(email: string, senha: string): Promise<AuthResultado> {
    const { data, error } = await this.supabaseService.auth.signUp({
      email,
      password: senha
    });

    if (error) {
      return { success: false, error: error.message };
    }

    // Com confirmação de e-mail habilitada no projeto (padrão do Supabase),
    // signUp devolve o usuário mas SEM sessão até o link ser confirmado.
    if (data.user && !data.session) {
      return { success: true, confirmacaoPendente: true };
    }

    this.usuario.set(data.user);
    return { success: true };
  }

  async login(email: string, senha: string): Promise<AuthResultado> {
    const { data, error } = await this.supabaseService.auth.signInWithPassword({
      email,
      password: senha
    });

    if (error) {
      return { success: false, error: error.message };
    }

    this.usuario.set(data.user);
    return { success: true };
  }

  async logout(): Promise<void> {
    await this.supabaseService.auth.signOut();
    this.usuario.set(null);
  }

  /**
   * Access token da sessão atual, para o backend validar via
   * `auth.get_user()` (Fase B.2 — D-17). `null` sem sessão ativa.
   */
  async obterAccessToken(): Promise<string | null> {
    const { data } = await this.supabaseService.auth.getSession();
    return data.session?.access_token ?? null;
  }
}
