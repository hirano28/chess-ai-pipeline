import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AuthService } from './auth.service';
import { SupabaseService } from './supabase.service';

describe('AuthService', () => {
  let service: AuthService;
  let supabaseService: SupabaseService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    supabaseService = TestBed.inject(SupabaseService);
    // getSession/onAuthStateChange rodam de verdade no construtor (via
    // providedIn: 'root'); sem sessão salva no localStorage do jsdom elas
    // resolvem pra "sem sessão" rapidamente, mas travamos aqui pra controlar
    // exatamente o que cada teste espera.
    vi.spyOn(supabaseService.auth, 'getSession').mockResolvedValue({
      data: { session: null },
      error: null
    } as any);
    vi.spyOn(supabaseService.auth, 'onAuthStateChange').mockReturnValue({
      data: { subscription: { unsubscribe: () => {} } }
    } as any);

    service = TestBed.inject(AuthService);
  });

  it('sessaoPronta vira true depois que aguardarSessaoPronta resolve', async () => {
    // O timing exato de quando a microtask de getSession() resolve varia
    // conforme o test runner intercala hooks - o que importa é a garantia
    // que aguardarSessaoPronta() dá: depois dela, sessaoPronta é sempre true.
    await service.aguardarSessaoPronta();
    expect(service.sessaoPronta()).toBe(true);
    expect(service.autenticado()).toBe(false);
  });

  it('restaura o usuário de uma sessão já existente ao inicializar', async () => {
    // Precisa de uma instância nova: a sessão é lida uma única vez no construtor.
    vi.spyOn(supabaseService.auth, 'getSession').mockResolvedValue({
      data: { session: { user: { id: 'u1', email: 'ana@teste.com' } } },
      error: null
    } as any);

    const outraInstancia = TestBed.runInInjectionContext(() => new AuthService());
    await outraInstancia.aguardarSessaoPronta();

    expect(outraInstancia.autenticado()).toBe(true);
    expect(outraInstancia.usuario()?.email).toBe('ana@teste.com');
  });

  describe('login', () => {
    it('marca o usuário como autenticado em caso de sucesso', async () => {
      vi.spyOn(supabaseService.auth, 'signInWithPassword').mockResolvedValue({
        data: { user: { id: 'u1', email: 'ana@teste.com' }, session: {} as any },
        error: null
      } as any);

      const resultado = await service.login('ana@teste.com', 'senha123');

      expect(resultado.success).toBe(true);
      expect(service.autenticado()).toBe(true);
      expect(service.usuario()?.email).toBe('ana@teste.com');
    });

    it('devolve o erro sem autenticar quando a credencial é inválida', async () => {
      vi.spyOn(supabaseService.auth, 'signInWithPassword').mockResolvedValue({
        data: { user: null, session: null },
        error: { message: 'Invalid login credentials' }
      } as any);

      const resultado = await service.login('ana@teste.com', 'senha-errada');

      expect(resultado.success).toBe(false);
      expect(resultado.error).toBe('Invalid login credentials');
      expect(service.autenticado()).toBe(false);
    });
  });

  describe('cadastrar', () => {
    it('sinaliza confirmacaoPendente quando o Supabase devolve usuário sem sessão', async () => {
      // Comportamento real deste projeto: confirmação de e-mail está ligada
      // (verificado direto na API antes de implementar — ver D-15).
      vi.spyOn(supabaseService.auth, 'signUp').mockResolvedValue({
        data: { user: { id: 'u2', email: 'novo@teste.com' }, session: null },
        error: null
      } as any);

      const resultado = await service.cadastrar('novo@teste.com', 'senha123');

      expect(resultado.success).toBe(true);
      expect(resultado.confirmacaoPendente).toBe(true);
      expect(service.autenticado()).toBe(false);
    });

    it('autentica direto quando o projeto devolve sessão (confirmação desligada)', async () => {
      vi.spyOn(supabaseService.auth, 'signUp').mockResolvedValue({
        data: { user: { id: 'u3', email: 'novo2@teste.com' }, session: {} as any },
        error: null
      } as any);

      const resultado = await service.cadastrar('novo2@teste.com', 'senha123');

      expect(resultado.success).toBe(true);
      expect(resultado.confirmacaoPendente).toBeUndefined();
      expect(service.autenticado()).toBe(true);
    });

    it('devolve o erro do Supabase (ex.: e-mail já cadastrado)', async () => {
      vi.spyOn(supabaseService.auth, 'signUp').mockResolvedValue({
        data: { user: null, session: null },
        error: { message: 'User already registered' }
      } as any);

      const resultado = await service.cadastrar('ana@teste.com', 'senha123');

      expect(resultado.success).toBe(false);
      expect(resultado.error).toBe('User already registered');
    });
  });

  describe('logout', () => {
    it('limpa o usuário autenticado', async () => {
      vi.spyOn(supabaseService.auth, 'signInWithPassword').mockResolvedValue({
        data: { user: { id: 'u1', email: 'ana@teste.com' }, session: {} as any },
        error: null
      } as any);
      await service.login('ana@teste.com', 'senha123');
      expect(service.autenticado()).toBe(true);

      vi.spyOn(supabaseService.auth, 'signOut').mockResolvedValue({ error: null } as any);
      await service.logout();

      expect(service.autenticado()).toBe(false);
      expect(service.usuario()).toBeNull();
    });
  });

  describe('obterAccessToken', () => {
    it('devolve o access_token da sessão atual (Fase B.2 — D-17)', async () => {
      vi.spyOn(supabaseService.auth, 'getSession').mockResolvedValue({
        data: { session: { access_token: 'jwt-da-sessao' } as any },
        error: null
      } as any);

      const token = await service.obterAccessToken();

      expect(token).toBe('jwt-da-sessao');
    });

    it('devolve null sem sessão ativa', async () => {
      vi.spyOn(supabaseService.auth, 'getSession').mockResolvedValue({
        data: { session: null },
        error: null
      } as any);

      const token = await service.obterAccessToken();

      expect(token).toBeNull();
    });
  });
});
