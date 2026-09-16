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

  it('deve exibir o erro em vez da mensagem de vazio quando erro está definido', () => {
    component.erro = 'Não foi possível carregar o histórico.';
    component.itens = [];
    fixture.detectChanges();

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Não foi possível carregar o histórico.');
    expect(texto).not.toContain('Nenhuma análise recente registrada.');
  });

  it('deve emitir itemClicado ao pressionar Enter na linha (acessibilidade)', () => {
    component.itens = [itemComStatus];
    fixture.detectChanges();

    let idEmitido: string | undefined;
    component.itemClicado.subscribe((id) => (idEmitido = id));

    const linha = fixture.nativeElement.querySelector('[role="button"]') as HTMLElement;
    linha.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));

    expect(idEmitido).toBe('p-1');
  });

  it('a linha clicável tem role="button" e é alcançável por teclado (tabindex)', () => {
    component.itens = [itemComStatus];
    fixture.detectChanges();

    const linha = fixture.nativeElement.querySelector('[role="button"]') as HTMLElement;
    expect(linha).toBeTruthy();
    expect(linha.getAttribute('tabindex')).toBe('0');
  });

  it('deve desenhar a miniatura do tabuleiro só nos itens que trazem fen', () => {
    component.itens = [
      { ...itemComStatus, fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1' },
      itemSemStatus
    ];
    fixture.detectChanges();

    const miniaturas = fixture.nativeElement.querySelectorAll('app-tabuleiro-preview');
    expect(miniaturas.length).toBe(1);
    // 64 casas desenhadas = o FEN foi de fato repassado e parseado.
    expect(miniaturas[0].querySelectorAll('.aspect-square').length).toBe(64);
  });

  it('a miniatura respeita a orientação pedida pelo item', () => {
    const fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    component.itens = [{ ...itemComStatus, fen, orientacao: 'PRETAS' }];
    fixture.detectChanges();

    const primeiraPeca = fixture.nativeElement.querySelector(
      'app-tabuleiro-preview img'
    ) as HTMLImageElement;
    // De pretas, o canto superior esquerdo é h1 (torre branca); de brancas seria a8.
    expect(primeiraPeca.getAttribute('alt')).toBe('wR');
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
    expect(texto).toContain('Concluída');
    // O item sem status usa o rótulo de ação padrão, sem nenhum badge colorido.
    expect(texto).toContain('Ver detalhes →');
  });

  it('deve escolher a variante de selo de acordo com o status', () => {
    expect(component.corBadgeStatus('concluido')).toBe('selo-sucesso');
    expect(component.corBadgeStatus('processando')).toBe('selo-info');
    expect(component.corBadgeStatus('falhou')).toBe('selo-perigo');
    expect(component.corBadgeStatus('pendente')).toBe('selo-latao');
  });

  it('deve escolher o rótulo do botão de acordo com o status', () => {
    expect(component.rotuloBotaoAcao('concluido')).toBe('Ver análise →');
    expect(component.rotuloBotaoAcao('processando')).toBe('Acompanhar');
    expect(component.rotuloBotaoAcao('falhou')).toBe('Reprocessar');
    expect(component.rotuloBotaoAcao('pendente')).toBe('Acompanhar');
    expect(component.rotuloBotaoAcao(undefined)).toBe('Ver detalhes →');
  });

  it('deve formatar data ISO e tratar valor vazio', () => {
    expect(component.formatarData('')).toBe('');
    expect(component.formatarData(null)).toBe('');
    expect(component.formatarData('2026-09-10T01:58:29Z')).toBeTruthy();
  });
});
