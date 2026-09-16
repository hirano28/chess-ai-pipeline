import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { vi, describe, beforeEach, it, expect } from 'vitest';
import { NarrativaAnaliseComponent } from './narrativa-analise.component';
import { AnaliseHexagonoCompleta, SupabaseService } from '../../services/supabase.service';

describe('NarrativaAnaliseComponent', () => {
  let component: NarrativaAnaliseComponent;
  let fixture: ComponentFixture<NarrativaAnaliseComponent>;
  let supabaseService: SupabaseService;

  const mockAnalise: AnaliseHexagonoCompleta = {
    narrativa: 'Primeiro parágrafo.\n\nSegundo parágrafo.',
    gargalo_sistemico_atual: 'TATICA',
    data_analise: '2026-09-10T00:00:00Z'
  };

  async function criarComponente(): Promise<void> {
    fixture = TestBed.createComponent(NarrativaAnaliseComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NarrativaAnaliseComponent],
      providers: [provideHttpClient(), SupabaseService]
    }).compileComponents();

    supabaseService = TestBed.inject(SupabaseService);
  });

  it('deve exibir a narrativa e o gargalo quando a busca funciona', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseCompleta').mockResolvedValue(mockAnalise);
    await criarComponente();

    expect(component.loading()).toBe(false);
    expect(component.error()).toBeNull();
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Primeiro parágrafo.');
    expect(texto).toContain('Segundo parágrafo.');
    expect(texto).toContain('Gargalo atual: TATICA');
  });

  it('deve exibir o estado vazio quando ainda não há nenhuma análise', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseCompleta').mockResolvedValue(null);
    await criarComponente();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Nenhuma análise gerada ainda.');
  });

  it('deve exibir uma mensagem de erro quando a busca falha', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseCompleta').mockRejectedValue(new Error('fora do ar'));
    await criarComponente();

    expect(component.error()).toContain('fora do ar');
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('fora do ar');
  });

  it('paragrafosDaNarrativa separa por quebras de linha e descarta linhas vazias', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseCompleta').mockResolvedValue(null);
    await criarComponente();

    expect(component.paragrafosDaNarrativa('a\n\n  \nb\nc')).toEqual(['a', 'b', 'c']);
  });

  it('formatarData trata data inválida sem lançar', async () => {
    vi.spyOn(supabaseService, 'getUltimaAnaliseCompleta').mockResolvedValue(null);
    await criarComponente();

    expect(component.formatarData('não-é-uma-data')).toBe('data indisponível');
    expect(component.formatarData('2026-09-10T00:00:00Z')).not.toBe('data indisponível');
  });
});
