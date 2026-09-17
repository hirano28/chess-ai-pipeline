import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { Router, provideRouter } from '@angular/router';
import { computed, signal } from '@angular/core';
import { User } from '@supabase/supabase-js';
import { App } from './app';
import { AuthService } from './services/auth.service';
import { ConsultaAoVivoService } from './services/consulta-ao-vivo.service';
import { TemaService } from './services/tema.service';

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
        { provide: AuthService, useValue: authFake },
        {
          provide: ConsultaAoVivoService,
          useValue: { acesso: async () => ({ habilitado: false, limitePorPartida: 0 }) }
        }
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

  async function montarLogado() {
    usuario.set({ id: 'u1', email: 'edson@exemplo.com' } as User);
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  it('navegação lateral mostra os grupos e as subpáginas do diagnóstico (D-71)', async () => {
    const fixture = await montarLogado();
    const compiled = fixture.nativeElement as HTMLElement;

    const grupos = Array.from(compiled.querySelectorAll('.nav-grupo')).map((p) => p.textContent?.trim());
    expect(grupos).toEqual(['Diagnóstico', 'Praticar', 'Ferramentas']);

    const links = Array.from(compiled.querySelectorAll('aside a.nav-item')).map((a) => a.textContent?.trim());
    for (const rotulo of ['Visão geral', 'Aberturas', 'Puzzles', 'Plano de treino', 'Treino diário', 'Laboratório', 'Explicador', 'Analisador', 'Perfil']) {
      expect(links).toContain(rotulo);
    }
    // Exclusivo do dono: sem liberação do servidor, não aparece.
    expect(links).not.toContain('Ao vivo');
  });

  it('marca o item da rota atual, e a execução de uma sessão acende o Plano de treino', async () => {
    const fixture = await montarLogado();
    const app = fixture.componentInstance;
    const item = (rota: string) => ({ rota, rotulo: rota, icone: '' });

    expect(app.ativo({ ...item('/'), exato: true })).toBe(true);
    expect(app.ativo(item('/treino'))).toBe(false);

    const router = TestBed.inject(Router);
    router.resetConfig([
      { path: 'sessao/:id', children: [] },
      { path: 'treinamento', children: [] }
    ]);
    await router.navigateByUrl('/sessao/abc?origem=x');
    fixture.detectChanges();

    expect(app.ativo({ ...item('/plano'), prefixosExtras: ['/sessao/'] })).toBe(true);
    expect(app.ativo({ ...item('/'), exato: true })).toBe(false);

    // "/treinamento" não é "/treino": prefixo só vale inteiro.
    await router.navigateByUrl('/treinamento');
    expect(app.ativo(item('/treino'))).toBe(false);
  });

  it('gaveta abre pelo menu, fecha no Esc e trava a rolagem só enquanto aberta', async () => {
    const fixture = await montarLogado();
    const compiled = fixture.nativeElement as HTMLElement;
    const aside = compiled.querySelector('aside') as HTMLElement;

    (compiled.querySelector('[aria-label="Abrir o menu"]') as HTMLButtonElement).click();
    fixture.detectChanges();
    TestBed.tick();
    expect(aside.classList).toContain('lateral-aberta');
    expect(document.body.style.overflow).toBe('hidden');

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    fixture.detectChanges();
    TestBed.tick();
    expect(aside.classList).not.toContain('lateral-aberta');
    expect(document.body.style.overflow).toBe('');
  });

  it('seletor de tema aplica e marca a escolha', async () => {
    const fixture = await montarLogado();
    const compiled = fixture.nativeElement as HTMLElement;
    const botao = (rotulo: string) =>
      Array.from(compiled.querySelectorAll<HTMLButtonElement>('[aria-label="Tema"] button')).find(
        (b) => b.getAttribute('aria-label') === rotulo
      )!;

    botao('Escuro').click();
    fixture.detectChanges();
    TestBed.tick();
    expect(TestBed.inject(TemaService).preferencia()).toBe('escuro');
    expect(document.documentElement.dataset['tema']).toBe('escuro');
    expect(botao('Escuro').getAttribute('aria-pressed')).toBe('true');

    botao('Claro').click();
    fixture.detectChanges();
    TestBed.tick();
    expect(document.documentElement.dataset['tema']).toBe('claro');
    localStorage.clear();
  });
});
