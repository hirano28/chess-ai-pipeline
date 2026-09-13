import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { LoginComponent } from './login.component';
import { AuthService } from '../../services/auth.service';

describe('LoginComponent', () => {
  let component: LoginComponent;
  let fixture: ComponentFixture<LoginComponent>;
  let authService: AuthService;
  let router: Router;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: new Map() } }
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(LoginComponent);
    component = fixture.componentInstance;
    authService = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
  });

  it('deve criar o componente no modo login por padrão', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
    expect(component.modo()).toBe('login');
  });

  it('formulário só fica válido com e-mail e senha de pelo menos 6 caracteres', () => {
    expect(component.formularioValido).toBe(false);
    component.email.set('ana@teste.com');
    component.senha.set('12345');
    expect(component.formularioValido).toBe(false);
    component.senha.set('123456');
    expect(component.formularioValido).toBe(true);
  });

  it('entrar() navega pra "/" em caso de sucesso', async () => {
    component.email.set('ana@teste.com');
    component.senha.set('senha123');
    vi.spyOn(authService, 'login').mockResolvedValue({ success: true });

    await component.entrar();

    expect(router.navigateByUrl).toHaveBeenCalledWith('/');
    expect(component.erro()).toBeNull();
  });

  it('entrar() mostra o erro e não navega quando a credencial falha', async () => {
    component.email.set('ana@teste.com');
    component.senha.set('senha-errada');
    vi.spyOn(authService, 'login').mockResolvedValue({
      success: false,
      error: 'Invalid login credentials'
    });

    await component.entrar();

    expect(router.navigateByUrl).not.toHaveBeenCalled();
    expect(component.erro()).toBe('Invalid login credentials');
  });

  it('cadastrar() mostra o aviso de confirmação pendente sem navegar', async () => {
    component.modo.set('cadastro');
    component.email.set('nova@teste.com');
    component.senha.set('senha123');
    vi.spyOn(authService, 'cadastrar').mockResolvedValue({
      success: true,
      confirmacaoPendente: true
    });

    await component.cadastrar();

    expect(component.confirmacaoPendente()).toBe(true);
    expect(router.navigateByUrl).not.toHaveBeenCalled();
  });

  it('alternarModo limpa erro e aviso de confirmação pendente', () => {
    component.erro.set('algum erro');
    component.confirmacaoPendente.set(true);

    component.alternarModo('cadastro');

    expect(component.modo()).toBe('cadastro');
    expect(component.erro()).toBeNull();
    expect(component.confirmacaoPendente()).toBe(false);
  });
});
