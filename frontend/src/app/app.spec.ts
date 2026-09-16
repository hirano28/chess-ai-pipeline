import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { computed, signal } from '@angular/core';
import { User } from '@supabase/supabase-js';
import { App } from './app';
import { AuthService } from './services/auth.service';

describe('App', () => {
  const usuario = signal<User | null>(null);

  const authFake = {
    usuario,
    sessaoPronta: signal(true),
    autenticado: computed(() => usuario() !== null),
    logout: async () => usuario.set(null)
  };

  beforeEach(async () => {
    usuario.set(null);

    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        { provide: AuthService, useValue: authFake }
      ]
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  // Sem sessão a única rota alcançável é /login (authGuard, D-23): exibir a
  // navegação ali seria oferecer links que voltam todos para a mesma tela.
  it('não deve renderizar a navegação sem sessão', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('nav')).toBeNull();
  });

  it('should render navigation links', async () => {
    usuario.set({ email: 'edson@exemplo.com' } as User);

    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const links = Array.from(compiled.querySelectorAll('nav a')).map((a) => a.textContent?.trim());
    expect(links).toContain('Hexágono');
    expect(links).toContain('Treino');
    expect(links).toContain('Laboratório');
    expect(links).toContain('Explicador');
    expect(links).toContain('Analisador');
    expect(links).toContain('Perfil');
  });
});
