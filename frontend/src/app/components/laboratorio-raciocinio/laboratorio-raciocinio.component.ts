import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { debounceTime, distinctUntilChanged, from, switchMap } from 'rxjs';
import {
  GuiaPasso,
  ResultadoRevisaoAvulsa,
  RevisaoAvulsaRecenteItem,
  RevisaoAvulsaService
} from '../../services/revisao-avulsa.service';
import { AuthLocalService } from '../../services/auth-local.service';
import { TabuleiroPreviewComponent } from '../tabuleiro-preview/tabuleiro-preview.component';
import {
  HistoricoAnaliseComponent,
  HistoricoAnaliseItem
} from '../historico-analise/historico-analise.component';
import { urlAnaliseLichess } from '../../shared/lichess';

const DEBOUNCE_PREVIEW_FEN_MS = 600;

/** Chave de localStorage que sobrevive a um F5, mesmo padrão do Analisador de Partida. */
export const STORAGE_KEY_LABORATORIO_ATIVO = 'chess_laboratorio_ativo';

/** Nome por extensão da inicial em português, para o texto de conferência. */
const NOME_DA_PECA_PT: Record<string, string> = {
  C: 'Cavalo',
  T: 'Torre',
  D: 'Dama',
  R: 'Rei',
  B: 'Bispo'
};

@Component({
  selector: 'app-laboratorio-raciocinio',
  standalone: true,
  imports: [TabuleiroPreviewComponent, HistoricoAnaliseComponent],
  templateUrl: './laboratorio-raciocinio.component.html'
})
export class LaboratorioRaciocinioComponent implements OnInit {
  readonly posicao = signal('');
  readonly lance = signal('');
  readonly pensamento = signal('');

  // Pré-visualização do tabuleiro: atualizada com debounce a partir de `posicao`,
  // tanto por digitação manual quanto pelo preenchimento via reconhecimento de foto.
  readonly fenPreview = signal('');

  // Link para abrir a MESMA posição do preview no analisador do Lichess.
  // Nulo enquanto não houver FEN resolvida — aí o link nem é renderizado.
  readonly linkLichess = computed(() => urlAnaliseLichess(this.fenPreview()));

  readonly carregando = signal(false);
  readonly erro = signal<string | null>(null);
  readonly resultado = signal<ResultadoRevisaoAvulsa | null>(null);

  readonly reconhecendoImagem = signal(false);
  readonly erroReconhecimento = signal<string | null>(null);
  readonly avisoConferirPosicao = signal(false);

  readonly salvando = signal(false);
  readonly salvo = signal(false);

  // Resumo leve dos 8 passos do guia (buscado de GET /guia-passos, discreto).
  readonly guiaPassos = signal<GuiaPasso[]>([]);
  readonly guiaAberto = signal(false);

  // Histórico de exercícios avulsos já SALVOS manualmente (revisao_exercicio_avulso).
  // Diferente do Analisador: o registro salvo não guarda top_candidatos/
  // analise_mestre/checklist_rotina, então reabrir um item do histórico mostra
  // um card resumido e somente-leitura (visualizandoHistorico), não o mesmo
  // card rico de uma análise recém-gerada (resultado).
  readonly historico = signal<RevisaoAvulsaRecenteItem[]>([]);
  readonly carregandoHistorico = signal(false);
  readonly visualizandoHistorico = signal<RevisaoAvulsaRecenteItem | null>(null);

  readonly itensHistoricoComponent = computed<HistoricoAnaliseItem[]>(() =>
    this.historico().map((item) => ({
      id: item.id,
      titulo: `Lance ${item.lance_jogado}`,
      detalhes: [
        `Qualidade: ${item.qualidade_lance ?? '—'}`,
        `Raciocínio: ${item.qualidade_raciocinio ?? '—'}`
      ],
      dataIso: item.created_at
      // Sem 'status': é sempre um registro já salvo e completo.
    }))
  );

  private readonly revisaoAvulsaService = inject(RevisaoAvulsaService);
  private readonly authLocalService = inject(AuthLocalService);

  readonly chaveConfigurada = signal(this.authLocalService.isConfigured());
  readonly chaveInput = signal('');
  readonly erroChave = signal<string | null>(null);

  get chaveFormularioValido(): boolean {
    return this.chaveInput().trim().length > 0;
  }

  constructor() {
    // Observa `posicao` (digitação manual OU preenchimento via foto - mesmo
    // signal) e resolve o FEN final com debounce, só para alimentar o preview
    // visual do tabuleiro. Nunca chama Gemini/Stockfish (GET /resolver-fen é
    // parsing puro), então é seguro disparar a cada mudança "estabilizada".
    toObservable(this.posicao)
      .pipe(
        debounceTime(DEBOUNCE_PREVIEW_FEN_MS),
        distinctUntilChanged(),
        switchMap((valor) => from(this.resolverFenParaPreview(valor))),
        takeUntilDestroyed()
      )
      .subscribe();
  }

  private async resolverFenParaPreview(valor: string): Promise<void> {
    const texto = valor.trim();
    if (!texto) {
      this.fenPreview.set('');
      return;
    }

    const resposta = await this.revisaoAvulsaService.resolverFen(texto);
    if (resposta.chaveInvalida) {
      this.tratarChaveInvalida();
      return;
    }
    if (resposta.success && resposta.fen) {
      this.fenPreview.set(resposta.fen);
    }
    // Posição inválida/incompleta (ainda digitando): não mexe no preview -
    // mantém o último tabuleiro válido em tela, sem mostrar erro nenhum.
  }

  async ngOnInit(): Promise<void> {
    this.guiaPassos.set(await this.revisaoAvulsaService.guiaPassos());
    if (this.chaveConfigurada()) {
      await this.carregarHistorico();
      this.restaurarAtivoSalvo();
    }
  }

  toggleGuia(): void {
    this.guiaAberto.update((aberto) => !aberto);
  }

  async carregarHistorico(): Promise<void> {
    this.carregandoHistorico.set(true);
    try {
      const res = await this.revisaoAvulsaService.listarRevisoesAvulsasRecentes(20);
      if (res.chaveInvalida) {
        this.tratarChaveInvalida();
        return;
      }
      if (res.success && res.itens) {
        this.historico.set(res.itens);
      }
    } finally {
      this.carregandoHistorico.set(false);
    }
  }

  /** O item embute tudo o que foi persistido - restaurar é local, sem chamada de rede. */
  selecionarHistorico(id: string): void {
    const item = this.historico().find((i) => i.id === id);
    if (!item) {
      return;
    }
    this.visualizandoHistorico.set(item);
    this.resultado.set(null);
    this.erro.set(null);
    this.salvarAtivo(id);
  }

  private restaurarAtivoSalvo(): void {
    try {
      const salvo = localStorage.getItem(STORAGE_KEY_LABORATORIO_ATIVO);
      if (salvo) {
        this.selecionarHistorico(salvo);
      }
    } catch {
      // Ignora erro de acesso a localStorage em ambientes restritos
    }
  }

  private salvarAtivo(id: string | null): void {
    try {
      if (id) {
        localStorage.setItem(STORAGE_KEY_LABORATORIO_ATIVO, id);
      } else {
        localStorage.removeItem(STORAGE_KEY_LABORATORIO_ATIVO);
      }
    } catch {
      // Ignora erro de acesso a localStorage
    }
  }

  salvarChave(): void {
    if (!this.chaveFormularioValido) {
      return;
    }
    this.authLocalService.setKey(this.chaveInput().trim());
    this.chaveInput.set('');
    this.erroChave.set(null);
    this.chaveConfigurada.set(true);
    void this.carregarHistorico();
    this.restaurarAtivoSalvo();
  }

  private tratarChaveInvalida(): void {
    this.chaveConfigurada.set(false);
    this.erroChave.set('Chave inválida, tente novamente.');
  }

  get formularioValido(): boolean {
    return (
      this.posicao().trim().length > 0 &&
      this.lancesSequencia().length > 0 &&
      this.pensamento().trim().length > 0
    );
  }

  /** Divide o campo "Seus lances" por espaço/vírgula, ignorando vazios. */
  lancesSequencia(): string[] {
    return this.lance()
      .replace(/,/g, ' ')
      .split(/\s+/)
      .map((l) => l.trim())
      .filter((l) => l.length > 0);
  }

  /** Envia a foto de um diagrama para /reconhecer-posicao e preenche o campo posição. */
  async onImagemSelecionada(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const arquivo = input.files?.[0];
    if (!arquivo) {
      return;
    }

    this.reconhecendoImagem.set(true);
    this.erroReconhecimento.set(null);
    this.avisoConferirPosicao.set(false);

    try {
      const resposta = await this.revisaoAvulsaService.reconhecerPosicao(arquivo);
      if (resposta.chaveInvalida) {
        this.tratarChaveInvalida();
        return;
      }
      if (!resposta.success || !resposta.fen) {
        throw new Error(resposta.error ?? 'Não foi possível reconhecer a posição nesta imagem.');
      }
      this.posicao.set(resposta.fen);
      this.avisoConferirPosicao.set(true);
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.erroReconhecimento.set(message);
    } finally {
      this.reconhecendoImagem.set(false);
      // Permite selecionar o mesmo arquivo de novo (ex: tentar outra vez após erro).
      input.value = '';
    }
  }

  async analisar(): Promise<void> {
    if (!this.formularioValido || this.carregando()) {
      return;
    }

    this.carregando.set(true);
    this.erro.set(null);
    this.resultado.set(null);
    this.salvo.set(false);
    this.avisoConferirPosicao.set(false);
    // Uma nova análise ao vivo abandona qualquer registro salvo que estivesse
    // sendo visualizado (evita mostrar os dois ao mesmo tempo).
    this.visualizandoHistorico.set(null);
    this.salvarAtivo(null);

    try {
      const resposta = await this.revisaoAvulsaService.revisar(
        this.posicao().trim(),
        this.lancesSequencia(),
        this.pensamento().trim()
      );
      if (resposta.chaveInvalida) {
        this.tratarChaveInvalida();
        return;
      }
      if (!resposta.success || !resposta.resultado) {
        throw new Error(resposta.error ?? 'O servidor não retornou um resultado.');
      }
      this.resultado.set(resposta.resultado);
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.erro.set(message);
    } finally {
      this.carregando.set(false);
    }
  }

  async salvarExercicio(): Promise<void> {
    const resultado = this.resultado();
    const primeira = resultado?.avaliacoes?.[0];
    if (!primeira || this.salvando()) {
      return;
    }

    this.salvando.set(true);
    this.erro.set(null);

    try {
      const resposta = await this.revisaoAvulsaService.salvar(
        primeira,
        resultado!.fen,
        this.pensamento().trim()
      );
      if (resposta.chaveInvalida) {
        this.tratarChaveInvalida();
        return;
      }
      if (!resposta.success) {
        throw new Error(resposta.error ?? 'O servidor não confirmou o salvamento.');
      }
      this.salvo.set(true);
      // O resultado ao vivo continua na tela (mais completo que o card
      // resumido do histórico) - só marcamos como "ativo" para sobreviver a
      // um F5, e atualizamos a lista para o item novo aparecer nela.
      if (resposta.id) {
        this.salvarAtivo(resposta.id);
      }
      void this.carregarHistorico();
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.erro.set(message);
    } finally {
      this.salvando.set(false);
    }
  }

  novaAnalise(): void {
    this.posicao.set('');
    this.lance.set('');
    this.pensamento.set('');
    this.resultado.set(null);
    this.erro.set(null);
    this.salvo.set(false);
    this.erroReconhecimento.set(null);
    this.avisoConferirPosicao.set(false);
    this.fenPreview.set('');
    this.visualizandoHistorico.set(null);
    this.salvarAtivo(null);
  }

  /**
   * Descreve por extenso o lance interpretado (ex: 'Cd5' -> 'Cavalo para d5'),
   * para o usuário confirmar de bate-pronto que entendemos a peça certa - o que
   * importa sobretudo no 'R' (Rei em português, Torre em inglês).
   * Devolve '' quando não dá para descrever com segurança.
   */
  descricaoLanceInterpretado(lancePt: string | undefined): string {
    const lance = (lancePt ?? '').trim();
    if (!lance) {
      return '';
    }
    if (/^O-O-O[+#]?$/.test(lance)) {
      return 'Roque longo';
    }
    if (/^O-O[+#]?$/.test(lance)) {
      return 'Roque curto';
    }

    const semSufixo = lance.replace(/[+#]$/, '');
    const promocao = semSufixo.match(/=([CTDRB])$/);
    const corpo = promocao ? semSufixo.slice(0, -2) : semSufixo;

    const destino = corpo.match(/([a-h][1-8])$/);
    if (!destino) {
      return '';
    }

    const casa = destino[1];
    const captura = corpo.includes('x');
    const peca = NOME_DA_PECA_PT[corpo[0]] ?? 'Peão';

    if (promocao) {
      const promovidaPara = NOME_DA_PECA_PT[promocao[1]] ?? promocao[1];
      const acao = captura ? 'captura em' : 'vai a';
      return `${peca} ${acao} ${casa} e promove a ${promovidaPara}`;
    }
    return captura ? `${peca} captura em ${casa}` : `${peca} para ${casa}`;
  }

  corBadgeQualidadeLance(qualidade: string): string {
    switch (qualidade) {
      case 'BOM':
        return 'border-[#3f6b4c] bg-[#173322] text-[#8fd6a6]';
      case 'SUBOTIMO':
        return 'border-[#7a6a2a] bg-[#332c14] text-[#e8cf7a]';
      default:
        return 'border-[#7a3a34] bg-[#331a17] text-[#e79a90]';
    }
  }

  corBadgeQualidadeRaciocinio(qualidade: string): string {
    switch (qualidade) {
      case 'SOLIDO':
        return 'border-[#3f6b4c] bg-[#173322] text-[#8fd6a6]';
      case 'FALHO':
        return 'border-[#7a3a34] bg-[#331a17] text-[#e79a90]';
      default:
        return 'border-[#40565c] bg-[#10191d] text-[#b9c7c8]';
    }
  }

  /** Rótulos legíveis e ordem canônica dos 8 passos da rubrica (chaves estáveis). */
  readonly checklistPassos: { chave: string; rotulo: string }[] = [
    { chave: 'pare_e_observe', rotulo: 'Parou e observou antes de calcular' },
    { chave: 'varredura_checks_capturas_ameacas', rotulo: 'Varredura de checks, capturas e ameaças' },
    { chave: 'perguntas_de_aagaard', rotulo: 'Respondeu as 3 perguntas de Aagaard' },
    { chave: 'candidatos_por_escrito', rotulo: 'Escreveu ao menos 3 candidatos' },
    { chave: 'calculo_ate_posicao_quieta', rotulo: 'Calculou cada candidato até posição quieta' },
    { chave: 'comparacao_dos_candidatos', rotulo: 'Comparou os candidatos entre si' },
    { chave: 'blundercheck', rotulo: 'Fez o blundercheck final' },
    { chave: 'registro_por_escrito', rotulo: 'Registrou o raciocínio por escrito' }
  ];

  iconeChecklist(valor: string | undefined): string {
    switch (valor) {
      case 'SIM':
        return '✓';
      case 'NAO':
        return '✗';
      default:
        return '?';
    }
  }

  corIconeChecklist(valor: string | undefined): string {
    switch (valor) {
      case 'SIM':
        return 'text-[#8fd6a6]';
      case 'NAO':
        return 'text-[#e79a90]';
      default:
        return 'text-[#8fa5a7]';
    }
  }
}
