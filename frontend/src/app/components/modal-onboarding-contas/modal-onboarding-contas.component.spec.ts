import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { vi, describe, beforeEach, afterEach, it, expect } from 'vitest';
import {
  ModalOnboardingContasComponent,
  CHAVE_ONBOARDING_DISPENSADO
} from './modal-onboarding-contas.component';
import { AuthService } from '../../services/auth.service';
import { SupabaseService } from '../../services/supabase.service';
import { LichessOauthService } from '../../services/lichess-oauth.service';

describe('ModalOnboardingContasComponent (D-36)', () => {
  let component: ModalOnboardingContasComponent;
  let fixture: ComponentFixture<ModalOnboardingContasComponent>;
  let authService: AuthService;
  let supabaseService: SupabaseService;
  let lichessOauthService: LichessOauthService;
  let router: Router;

  beforeEach(async () => {
    sessionStorage.clear();

    await TestBed.configureTestingModule({
      imports: [ModalOnboardingContasComponent],
      providers: [
        provideHttpClient(),
        {
          provide: Router,
          useValue: { url: '/', navigate: vi.fn() }
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ModalOnboardingContasComponent);
    component = fixture.componentInstance;
    authService = TestBed.inject(AuthService);
    supabaseService = TestBed.inject(SupabaseService);
    lichessOauthService = TestBed.inject(LichessOauthService);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('não exibe modal se usuário não estiver autenticado', async () => {
    authService.usuario.set(null);
    await component.verificarNecessidadeOnboarding();
    expect(component.visivel()).toBe(false);
  });

  it('não exibe modal se usuário já dispensou nesta sessão', async () => {
    authService.usuario.set({ id: 'user-1' } as any);
    sessionStorage.setItem(CHAVE_ONBOARDING_DISPENSADO, 'true');

    await component.verificarNecessidadeOnboarding();

    expect(component.visivel()).toBe(false);
  });

  it('não exibe modal se rota atual for /login ou /perfil', async () => {
    authService.usuario.set({ id: 'user-1' } as any);
    Object.defineProperty(router, 'url', { value: '/perfil', configurable: true });

    await component.verificarNecessidadeOnboarding();

    expect(component.visivel()).toBe(false);
  });

  it('exibe modal se usuário logado não possui contas cadastradas', async () => {
    authService.usuario.set({ id: 'user-1' } as any);
    vi.spyOn(supabaseService, 'getPerfilUsuario').mockResolvedValue(null);

    await component.verificarNecessidadeOnboarding();

    expect(component.visivel()).toBe(true);
  });

  it('exibe modal se usuário logado tem perfil com usernames vazios', async () => {
    authService.usuario.set({ id: 'user-1' } as any);
    vi.spyOn(supabaseService, 'getPerfilUsuario').mockResolvedValue({
      lichessUsername: null,
      chesscomUsername: ''
    });

    await component.verificarNecessidadeOnboarding();

    expect(component.visivel()).toBe(true);
  });

  it('não exibe modal se usuário já tem pelo menos uma conta vinculada', async () => {
    authService.usuario.set({ id: 'user-1' } as any);
    vi.spyOn(supabaseService, 'getPerfilUsuario').mockResolvedValue({
      lichessUsername: 'tantofaz123',
      chesscomUsername: null
    });

    await component.verificarNecessidadeOnboarding();

    expect(component.visivel()).toBe(false);
  });

  it('fechar() oculta modal e marca no sessionStorage', () => {
    component.visivel.set(true);

    component.fechar();

    expect(component.visivel()).toBe(false);
    expect(sessionStorage.getItem(CHAVE_ONBOARDING_DISPENSADO)).toBe('true');
  });

  it('salvar() persiste as contas e aciona fechamento', async () => {
    authService.usuario.set({ id: 'user-1' } as any);
    component.lichessUsername.set('laisxadrez');
    const salvarSpy = vi
      .spyOn(supabaseService, 'salvarPerfilUsuario')
      .mockResolvedValue({ success: true });

    await component.salvar();

    expect(salvarSpy).toHaveBeenCalledWith('user-1', 'laisxadrez', '');
    expect(component.sucesso()).toBe(true);
  });

  it('salvar() não faz nada se formulário estiver em branco', async () => {
    const salvarSpy = vi.spyOn(supabaseService, 'salvarPerfilUsuario');
    component.lichessUsername.set('   ');
    component.chesscomUsername.set('');

    await component.salvar();

    expect(salvarSpy).not.toHaveBeenCalled();
  });

  it('Esc fecha o modal — sem isso não havia saída pelo teclado', () => {
    component.visivel.set(true);

    component.aoPressionarEsc();

    expect(component.visivel()).toBe(false);
  });

  it('Esc não fecha no meio de um salvamento', () => {
    component.visivel.set(true);
    component.salvando.set(true);

    component.aoPressionarEsc();

    expect(component.visivel()).toBe(true);
  });

  it('clique no scrim fecha, clique dentro do cartão não', () => {
    component.visivel.set(true);
    const scrim = document.createElement('div');
    const cartao = document.createElement('div');

    // Clique originado no próprio scrim.
    component.aoClicarNoFundo({ target: scrim, currentTarget: scrim } as unknown as MouseEvent);
    expect(component.visivel()).toBe(false);

    component.visivel.set(true);
    // Clique que borbulhou de dentro do cartão: não deve fechar.
    component.aoClicarNoFundo({ target: cartao, currentTarget: scrim } as unknown as MouseEvent);
    expect(component.visivel()).toBe(true);
  });
});

