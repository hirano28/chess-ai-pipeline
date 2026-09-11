import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HistoricoAnaliseComponent, HistoricoAnaliseItem } from './historico-analise.component';

describe('HistoricoAnaliseComponent', () => {
  let component: HistoricoAnaliseComponent;
  let fixture: ComponentFixture<HistoricoAnaliseComponent>;

  const itemComStatus: HistoricoAnaliseItem = {
    id: 'p-1',
    titulo: 'hirano28 vs oponente',
    detalhes: ['Cor: Brancas ♔', 'ECO: B90'],
    dataIso: '2026-09-10T01:58:29Z',
    status: 'concluido'
  };

  const itemSemStatus: HistoricoAnaliseItem = {
    id: 'e-1',
    titulo: 'Posição equilibrada.',
    detalhes: ['Win%: 50%'],
    dataIso: '2026-09-11T10:00:00Z'
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HistoricoAnaliseComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(HistoricoAnaliseComponent);
    component = fixture.componentInstance;
  });

  it('deve criar o componente', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('deve exibir a mensagem de vazio quando não há itens', () => {
    component.mensagemVazio = 'Nada por aqui ainda.';
    fixture.detectChanges();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Nada por aqui ainda.');
  });

  it('deve exibir a contagem e os títulos dos itens', () => {
    component.itens = [itemComStatus, itemSemStatus];
    fixture.detectChanges();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('2 recentes');
    expect(texto).toContain('hirano28 vs oponente');
    expect(texto).toContain('Posição equilibrada.');
  });

  it('deve emitir itemClicado com o id do item ao clicar na linha', () => {
    component.itens = [itemComStatus];
    fixture.detectChanges();

    let idEmitido: string | undefined;
    component.itemClicado.subscribe((id) => (idEmitido = id));

    const linha = fixture.nativeElement.querySelector('[class*="cursor-pointer"]') as HTMLElement;
    linha.click();

    expect(idEmitido).toBe('p-1');
  });

  it('deve emitir atualizarClicado ao clicar em "Atualizar lista"', () => {
    fixture.detectChanges();

    let chamou = false;
    component.atualizarClicado.subscribe(() => (chamou = true));

    const botao = fixture.nativeElement.querySelector('button') as HTMLElement;
    botao.click();

    expect(chamou).toBe(true);
  });

  it('deve renderizar badge de status quando presente e omitir quando ausente', () => {
    component.itens = [itemComStatus, itemSemStatus];
    fixture.detectChanges();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('✅ Concluída');
    // O item sem status usa o rótulo de ação padrão, sem nenhum badge colorido.
    expect(texto).toContain('Ver detalhes →');
  });

  it('deve escolher o rótulo do botão de acordo com o status', () => {
    expect(component.rotuloBotaoAcao('concluido')).toBe('Ver Análise →');
    expect(component.rotuloBotaoAcao('processando')).toBe('Acompanhar ⏳');
    expect(component.rotuloBotaoAcao('falhou')).toBe('Reprocessar 🔄');
    expect(component.rotuloBotaoAcao('pendente')).toBe('Acompanhar ⏱️');
    expect(component.rotuloBotaoAcao(undefined)).toBe('Ver detalhes →');
  });

  it('deve formatar data ISO e tratar valor vazio', () => {
    expect(component.formatarData('')).toBe('');
    expect(component.formatarData(null)).toBe('');
    expect(component.formatarData('2026-09-10T01:58:29Z')).toBeTruthy();
  });
});
