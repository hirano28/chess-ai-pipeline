import { Component, inject, OnDestroy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  ResumoPartidaData,
  RevisaoAvulsaService
} from '../../services/revisao-avulsa.service';
import { AuthLocalService } from '../../services/auth-local.service';

export type EstadoAnalise =
  | 'INICIAL'
  | 'ENVIANDO'
  | 'PROCESSANDO'
  | 'CONCLUIDO'
  | 'FALHOU';

@Component({
  selector: 'app-analisador-partida',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './analisador-partida.component.html'
})
export class AnalisadorPartidaComponent implements OnDestroy {
  readonly pgn = signal('');
  readonly cor = signal<'AUTO' | 'BRANCAS' | 'PRETAS'>('AUTO');

  readonly estado = signal<EstadoAnalise>('INICIAL');
  readonly partidaId = signal<string | null>(null);
  readonly externalId = signal<string | null>(null);
  readonly resumo = signal<ResumoPartidaData | null>(null);
  readonly erro = signal<string | null>(null);
  readonly segundosProcessamento = signal(0);

  private readonly revisaoAvulsaService = inject(RevisaoAvulsaService);
  private readonly authLocalService = inject(AuthLocalService);

  readonly chaveConfigurada = signal(this.authLocalService.isConfigured());
  readonly chaveInput = signal('');
  readonly erroChave = signal<string | null>(null);

  private pollingTimer: ReturnType<typeof setInterval> | null = null;
  private timerSegundos: ReturnType<typeof setInterval> | null = null;

  ngOnDestroy(): void {
    this.pararTimers();
  }

  get chaveFormularioValido(): boolean {
    return this.chaveInput().trim().length > 0;
  }

  get formularioValido(): boolean {
    return this.pgn().trim().length > 0;
  }

  salvarChave(): void {
    if (!this.chaveFormularioValido) {
      return;
    }
    this.authLocalService.setKey(this.chaveInput().trim());
    this.chaveInput.set('');
    this.erroChave.set(null);
    this.chaveConfigurada.set(true);
  }

  private tratarChaveInvalida(): void {
    this.pararTimers();
    this.chaveConfigurada.set(false);
    this.erroChave.set('Chave inválida, tente novamente.');
    this.estado.set('INICIAL');
  }

  carregarExemplo(): void {
    // Partida real de teste com pontos críticos e reviravolta tática
    this.pgn.set(`[Event "Rated Blitz game"]
[Site "https://lichess.org/AmxiZxvj"]
[Date "2024.06.15"]
[White "hirano28"]
[Black "opponent123"]
[Result "0-1"]
[WhiteElo "1550"]
[BlackElo "1580"]
[ECO "B90"]

1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Be3 e5 7. Nb3 Be6 8. Qd2 Nbd7 9. O-O-O b5 10. f3 h5 11. Kb1 Be7 12. h4 Rc8 13. Nd5 Bxd5 14. exd5 Nb6 15. Bxb6 Qxb6 16. Na5 Nxd5 17. Qxd5 Qxa5 18. Bd3 Qc7 19. c3 Qc5 20. Qb7 Qc6 21. Qxc6+ Rxc6 22. Be4 Rc5 23. Rd5 Rxd5 24. Bxd5 Kd7 25. Bxf7 Bf6 26. Kc2 Ke7 27. Bd5 g5 28. hxg5 Bxg5 29. b4 h4 30. Bb7 Rb8 31. Bxa6 Kd7 32. a4 bxa4 33. Ra1 d5 34. Rxa4 d4 35. cxd4 exd4 36. b5 Bf6 37. Kd3 Kc7 38. Rc4+ Kd7 39. Rc6 Be5 40. Rh6 Rg8 41. Rxh4 Rxg2 42. Rh7+ Kd6 43. Rh6+ Kc5 44. Rc6+ Kb4 45. b6 Ka5 46. Bc8 Rb2 47. b7 Rb3+ 48. Ke4 Bb8 49. f4 d3 50. f5 d2 51. Rc5+ Kb6 52. Rd5 Rb4+ 53. Ke3 Bf4+ 54. Ke2 Re4+ 55. Kf3 Re1 56. Rxd2 Bb8 57. f6 Re8 58. Kg4 Rf8 59. Kf5 Kc7 60. Kg6 Ba7 61. Kg7 Bc5 62. Rc2 0-1`);
    this.cor.set('BRANCAS');
    this.erro.set(null);
  }

  async analisar(): Promise<void> {
    if (!this.formularioValido || this.estado() === 'ENVIANDO' || this.estado() === 'PROCESSANDO') {
      return;
    }

    this.erro.set(null);
    this.estado.set('ENVIANDO');
    this.segundosProcessamento.set(0);

    try {
      const corParam = this.cor() === 'AUTO' ? null : this.cor();
      const resposta = await this.revisaoAvulsaService.submeterPartidaPgn(
        this.pgn().trim(),
        corParam
      );

      if (resposta.chaveInvalida) {
        this.tratarChaveInvalida();
        return;
      }

      if (!resposta.success || !resposta.partidaId) {
        throw new Error(resposta.error ?? 'Falha ao enviar a partida.');
      }

      this.partidaId.set(resposta.partidaId);
      this.externalId.set(resposta.externalId ?? null);
      this.estado.set('PROCESSANDO');
      this.iniciarPolling(resposta.partidaId);
    } catch (cause: unknown) {
      const msg = cause instanceof Error ? cause.message : 'Erro desconhecido';
      this.erro.set(msg);
      this.estado.set('INICIAL');
    }
  }

  private iniciarPolling(partidaId: string): void {
    this.pararTimers();

    // Cronômetro decorrido
    this.timerSegundos = setInterval(() => {
      this.segundosProcessamento.update(s => s + 1);
    }, 1000);

    // Consulta periódica do status (a cada 3.5 segundos)
    this.pollingTimer = setInterval(async () => {
      try {
        const resultado = await this.revisaoAvulsaService.consultarStatusPartida(partidaId);

        if (resultado.chaveInvalida) {
          this.tratarChaveInvalida();
          return;
        }

        if (!resultado.success || !resultado.dados) {
          return;
        }

        const { status, resumo } = resultado.dados;

        if (status === 'concluido' && resumo) {
          this.pararTimers();
          this.resumo.set(resumo);
          this.estado.set('CONCLUIDO');
        } else if (status === 'falhou') {
          this.pararTimers();
          this.erro.set('Ocorreu uma falha no processamento do motor ou diagnóstico.');
          this.estado.set('FALHOU');
        }
      } catch (cause: unknown) {
        // Erros transitórios de rede no polling não abortam o fluxo imediatamente
      }
    }, 3500);
  }

  private pararTimers(): void {
    if (this.pollingTimer) {
      clearInterval(this.pollingTimer);
      this.pollingTimer = null;
    }
    if (this.timerSegundos) {
      clearInterval(this.timerSegundos);
      this.timerSegundos = null;
    }
  }

  novaAnalise(): void {
    this.pararTimers();
    this.pgn.set('');
    this.cor.set('AUTO');
    this.partidaId.set(null);
    this.externalId.set(null);
    this.resumo.set(null);
    this.erro.set(null);
    this.estado.set('INICIAL');
  }

  formatarTempo(segundos: number): string {
    const min = Math.floor(segundos / 60);
    const seg = segundos % 60;
    return `${min}:${seg < 10 ? '0' : ''}${seg}`;
  }

  formatarTag(tag: string): string {
    return tag.replace(/_/g, ' ').toUpperCase();
  }
}

