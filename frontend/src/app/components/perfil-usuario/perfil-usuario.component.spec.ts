import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { ActivatedRoute, Router } from '@angular/router';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { PerfilUsuarioComponent } from './perfil-usuario.component';
import { AuthService } from '../../services/auth.service';
import { SupabaseService } from '../../services/supabase.service';
import { LichessOauthService } from '../../services/lichess-oauth.service';

describe('PerfilUsuarioComponent (D-28, D-35)', () => {
  let component: PerfilUsuarioComponent;
  let fixture: ComponentFixture<PerfilUsuarioComponent>;
  let authService: AuthService;
  let supabaseService: SupabaseService;
  let lichessOauthService: LichessOauthService;
  let router: Router;

  const mockActivatedRoute = {
    snapshot: {
      queryParams: {} as Record<string, string>
    }
  };

  beforeEach(async () => {
    mockActivatedRoute.snapshot.queryParams = {};

    await TestBed.configureTestingModule({
      imports: [PerfilUsuarioComponent],
      providers: [
        provideHttpClient(),
        { provide: ActivatedRoute, useValue: mockActivatedRoute },
        { provide: Router, useValue: { navigate: vi.fn() } }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(PerfilUsuarioComponent);
    component = fixture.componentInstance;
    authService = TestBed.inject(AuthService);
    supabaseService = TestBed.inject(SupabaseService);
    lichessOauthService = TestBed.inject(LichessOauthService);
    router = TestBed.inject(Router);
  });

  it('deve carregar o perfil e status OAuth ao iniciar', async () => {
    vi.spyOn(supabaseService, 'getPerfilUsuario').mockResolvedValue({
      lichessUsername: 'laisxadrez',
      chesscomUsername: null
    });
    vi.spyOn(lichessOauthService, 'obterStatus').mockResolvedValue({
      conectado: true,
      expires_at: '2027-01-01T00:00:00+00:00'
    });

    await component.ngOnInit();

    expect(component.lichessUsername()).toBe('laisxadrez');
    expect(component.chesscomUsername()).toBe('');
    expect(component.oauthStatus()?.conectado).toBe(true);
    expect(component.carregando()).toBe(false);
    expect(component.oauthCarregando()).toBe(false);
  });

  it('processa query param ?conectado=lichess com mensagem de sucesso', async () => {
    mockActivatedRoute.snapshot.queryParams = { conectado: 'lichess' };
    vi.spyOn(supabaseService, 'getPerfilUsuario').mockResolvedValue(null);
    vi.spyOn(lichessOauthService, 'obterStatus').mockResolvedValue({ conectado: true });

    await component.ngOnInit();

    expect(component.oauthMensagemSucesso()).toContain('vinculada com sucesso');
    expect(router.navigate).toHaveBeenCalledWith([], expect.objectContaining({ replaceUrl: true }));
  });

  it('processa query param ?erro=lichess_negado com mensagem explicativa', async () => {
    mockActivatedRoute.snapshot.queryParams = { erro: 'lichess_negado' };
    vi.spyOn(supabaseService, 'getPerfilUsuario').mockResolvedValue(null);
    vi.spyOn(lichessOauthService, 'obterStatus').mockResolvedValue({ conectado: false });

    await component.ngOnInit();

    expect(component.oauthMensagemErro()).toContain('recusou');
    expect(router.navigate).toHaveBeenCalledWith([], expect.objectContaining({ replaceUrl: true }));
  });

  it('formulário só fica válido com pelo menos uma das duas contas preenchida', () => {
    expect(component.formularioValido).toBe(false);
    component.lichessUsername.set('   ');
    expect(component.formularioValido).toBe(false);
    component.chesscomUsername.set('laisxadrez');
    expect(component.formularioValido).toBe(true);
  });

  it('salvar() grava com o user_id da sessão logada', async () => {
    authService.usuario.set({ id: 'user-lais' } as any);
    component.chesscomUsername.set('laisxadrez');
    const salvarSpy = vi
      .spyOn(supabaseService, 'salvarPerfilUsuario')
      .mockResolvedValue({ success: true });

    await component.salvar();

    expect(salvarSpy).toHaveBeenCalledWith('user-lais', '', 'laisxadrez');
    expect(component.salvo()).toBe(true);
    expect(component.erro()).toBeNull();
  });

  it('salvar() mostra erro e não chama o serviço sem sessão', async () => {
    authService.usuario.set(null);
    component.lichessUsername.set('laisxadrez');
    const salvarSpy = vi.spyOn(supabaseService, 'salvarPerfilUsuario');

    await component.salvar();

    expect(salvarSpy).not.toHaveBeenCalled();
    expect(component.erro()).toContain('sessão expirou');
  });

  it('desconectarLichess() atualiza status para desconectado', async () => {
    vi.spyOn(lichessOauthService, 'desconectar').mockResolvedValue(true);
    component.oauthStatus.set({ conectado: true });

    await component.desconectarLichess();

    expect(component.oauthStatus()?.conectado).toBe(false);
    expect(component.oauthMensagemSucesso()).toContain('desvinculada');
  });
});
