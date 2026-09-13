import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { PerfilUsuarioComponent } from './perfil-usuario.component';
import { AuthService } from '../../services/auth.service';
import { SupabaseService } from '../../services/supabase.service';

describe('PerfilUsuarioComponent', () => {
  let component: PerfilUsuarioComponent;
  let fixture: ComponentFixture<PerfilUsuarioComponent>;
  let authService: AuthService;
  let supabaseService: SupabaseService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PerfilUsuarioComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(PerfilUsuarioComponent);
    component = fixture.componentInstance;
    authService = TestBed.inject(AuthService);
    supabaseService = TestBed.inject(SupabaseService);
  });

  it('deve carregar o perfil existente ao iniciar', async () => {
    vi.spyOn(supabaseService, 'getPerfilUsuario').mockResolvedValue({
      lichessUsername: 'laisxadrez',
      chesscomUsername: null
    });

    await component.ngOnInit();

    expect(component.lichessUsername()).toBe('laisxadrez');
    expect(component.chesscomUsername()).toBe('');
    expect(component.carregando()).toBe(false);
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

  it('salvar() mostra o erro do servidor quando a gravação falha', async () => {
    authService.usuario.set({ id: 'user-lais' } as any);
    component.lichessUsername.set('laisxadrez');
    vi.spyOn(supabaseService, 'salvarPerfilUsuario').mockResolvedValue({
      success: false,
      error: 'restrição violada'
    });

    await component.salvar();

    expect(component.salvo()).toBe(false);
    expect(component.erro()).toContain('restrição violada');
  });
});
