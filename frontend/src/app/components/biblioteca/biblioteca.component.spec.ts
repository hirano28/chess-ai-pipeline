import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { vi, describe, beforeEach, afterEach, it, expect } from 'vitest';
import {
  BibliotecaComponent,
  PERGUNTA_MAX_CARACTERES,
  STORAGE_KEY_BIBLIOTECA_ATIVA
} from './biblioteca.component';
import { BibliotecaService, RespostaBiblioteca } from '../../services/biblioteca.service';

const RESPOSTA: RespostaBiblioteca = {
  id: 'consulta-1',
  pergunta: 'o que é cravada?',
  resposta: 'A cravada imobiliza a peça.',
  fontes: [{ livro: 'Meu Sistema', capitulo: 'A Peça Cravada', pagina_aprox: 111 }]
};

async function montar(queryParams: Record<string, string> = {}) {
  await TestBed.configureTestingModule({
    imports: [BibliotecaComponent],
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { queryParamMap: convertToParamMap(queryParams) } }
      }
    ]
  }).compileComponents();

  const fixture = TestBed.createComponent(BibliotecaComponent);
  const service = TestBed.inject(BibliotecaService);
  return { fixture, component: fixture.componentInstance, service };
}

describe('BibliotecaComponent', () => {
  let fixture: ComponentFixture<BibliotecaComponent>;
  let component: BibliotecaComponent;
  let service: BibliotecaService;

  afterEach(() => {
    localStorage.clear();
    TestBed.resetTestingModule();
    vi.restoreAllMocks();
  });

  describe('sem query param', () => {
    beforeEach(async () => {
      ({ fixture, component, service } = await montar());
      vi.spyOn(service, 'listarRecentes').mockResolvedValue({ success: true, dados: [] });
    });

    it('não consulta sozinho ao abrir a tela', async () => {
      const consultar = vi.spyOn(service, 'consultar');

      await component.ngOnInit();

      expect(consultar).not.toHaveBeenCalled();
    });

    it('bloqueia pergunta vazia e pergunta acima do limite do backend', () => {
      component.pergunta.set('   ');
      expect(component.formularioValido).toBe(false);

      component.pergunta.set('a'.repeat(PERGUNTA_MAX_CARACTERES + 1));
      expect(component.formularioValido).toBe(false);

      component.pergunta.set('pergunta válida');
      expect(component.formularioValido).toBe(true);
    });

    it('guarda a última resposta para sobreviver a um F5', async () => {
      vi.spyOn(service, 'consultar').mockResolvedValue({ success: true, dados: RESPOSTA });
      component.pergunta.set('o que é cravada?');

      await component.consultar();

      expect(component.resultado()).toEqual(RESPOSTA);
      expect(localStorage.getItem(STORAGE_KEY_BIBLIOTECA_ATIVA)).toContain('cravada');
    });

    it('mostra o erro do backend sem apagar a pergunta digitada', async () => {
      vi.spyOn(service, 'consultar').mockResolvedValue({
        success: false,
        error: 'Limite diário atingido, tente novamente amanhã.'
      });
      component.pergunta.set('uma pergunta');

      await component.consultar();

      expect(component.erro()).toContain('Limite diário');
      expect(component.pergunta()).toBe('uma pergunta');
      expect(component.resultado()).toBeNull();
    });

    it('resume o histórico pelos livros citados', async () => {
      vi.spyOn(service, 'listarRecentes').mockResolvedValue({
        success: true,
        dados: [
          {
            id: 'c1',
            pergunta: 'o que é cravada?',
            resposta: {
              resposta: 'texto',
              fontes: [
                { livro: 'Meu Sistema', capitulo: 'A', pagina_aprox: 1 },
                { livro: 'Meu Sistema', capitulo: 'B', pagina_aprox: 2 },
                { livro: 'Arte do Ataque', capitulo: 'C', pagina_aprox: 3 }
              ]
            },
            created_at: '2026-09-17T22:00:00Z'
          }
        ]
      });

      await component.carregarHistorico();

      const item = component.itensHistoricoComponent()[0];
      expect(item.detalhes).toEqual(['Meu Sistema · Arte do Ataque']);
    });
  });

  describe('com pergunta na URL', () => {
    it('consulta automaticamente o que a tela de Aberturas mandou', async () => {
      ({ fixture, component, service } = await montar({
        pergunta: 'Quais são os planos da Defesa Siciliana jogando de pretas?'
      }));
      vi.spyOn(service, 'listarRecentes').mockResolvedValue({ success: true, dados: [] });
      const consultar = vi
        .spyOn(service, 'consultar')
        .mockResolvedValue({ success: true, dados: RESPOSTA });

      await component.ngOnInit();

      expect(consultar).toHaveBeenCalledWith(
        'Quais são os planos da Defesa Siciliana jogando de pretas?'
      );
    });
  });
});
