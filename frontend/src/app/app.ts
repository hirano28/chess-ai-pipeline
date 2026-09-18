import { NgTemplateOutlet } from '@angular/common';
import { Component, ElementRef, computed, effect, inject, signal, untracked, viewChild } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';
import { AuthService } from './services/auth.service';
import { ConsultaAoVivoService } from './services/consulta-ao-vivo.service';
import { PreferenciaTema, TemaService } from './services/tema.service';
import { ModalOnboardingContasComponent } from './components/modal-onboarding-contas/modal-onboarding-contas.component';

export interface ItemNavegacao {
  rota: string;
  rotulo: string;
  /** `d` de um <path> 24×24 com traço; vários subcaminhos cabem num só. */
  icone: string;
  /** Só a rota exata acende o item (a raiz "/" acenderia em todas). */
  exato?: boolean;
  /** Outras rotas que pertencem a este item, ex.: a execução de uma sessão do plano. */
  prefixosExtras?: string[];
  /** D-67: item que só aparece para quem o servidor libera. */
  exclusivoConsultaAoVivo?: boolean;
}

export interface GrupoNavegacao {
  titulo: string;
  itens: ItemNavegacao[];
}

/**
 * Mapa do app (D-71). Os grupos seguem o que a pessoa vai fazer: entender o
 * próprio jogo, praticar, ou usar uma ferramenta avulsa. A antiga página única
 * do Hexágono virou as quatro primeiras entradas.
 */
export const NAVEGACAO: GrupoNavegacao[] = [
  {
    titulo: 'Diagnóstico',
    itens: [
      { rota: '/', rotulo: 'Visão geral', exato: true, icone: 'M12 2.75 20 7.38v9.24l-8 4.63-8-4.63V7.38z M12 8.5l3 1.75v3.5L12 15.5l-3-1.75v-3.5z' },
      { rota: '/aberturas', rotulo: 'Aberturas', icone: 'M3 5.5c3-1 6-1 9 1 3-2 6-2 9-1v13c-3-1-6-1-9 1-3-2-6-2-9-1z M12 6.5v13' },
      { rota: '/puzzles', rotulo: 'Puzzles', icone: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z M12 7.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9z M12 11.25a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5z' },
      { rota: '/plano', rotulo: 'Plano de treino', prefixosExtras: ['/sessao/'], icone: 'M8 3v3 M16 3v3 M4 9h16 M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M8.5 14.5l2 2 4-4' }
    ]
  },
  {
    titulo: 'Praticar',
    itens: [
      { rota: '/treino', rotulo: 'Treino diário', icone: 'M4 12a8 8 0 0 1 13.66-5.66L20 8.5 M20 4v4.5h-4.5 M20 12a8 8 0 0 1-13.66 5.66L4 15.5 M4 20v-4.5h4.5' },
      { rota: '/laboratorio', rotulo: 'Laboratório', icone: 'M9 3h6 M10 3v6l-5.5 9.5A1.5 1.5 0 0 0 5.8 21h12.4a1.5 1.5 0 0 0 1.3-2.5L14 9V3 M7 15h10' }
    ]
  },
  {
    titulo: 'Ferramentas',
    itens: [
      { rota: '/biblioteca', rotulo: 'Biblioteca', icone: 'M5 4h5v16H5z M10 4h5v16h-5z M15.5 5.2l3.8 1 -3.2 15.5 -3.8-1z' },
      { rota: '/explicador', rotulo: 'Explicador', icone: 'M4 5h16v11H9l-5 4z M8 9.5h8 M8 12.5h5' },
      { rota: '/analisador', rotulo: 'Analisador', icone: 'M4 4v16h16 M7.5 15l4-5 3 3 5-6' },
      { rota: '/consulta-ao-vivo', rotulo: 'Ao vivo', exclusivoConsultaAoVivo: true, icone: 'M10 12a2 2 0 1 0 4 0 2 2 0 0 0-4 0 M7.76 7.76a6 6 0 0 0 0 8.48 M16.24 7.76a6 6 0 0 1 0 8.48 M4.93 4.93a10 10 0 0 0 0 14.14 M19.07 4.93a10 10 0 0 1 0 14.14' }
    ]
  }
];

export const ITEM_PERFIL: ItemNavegacao = {
  rota: '/perfil',
  rotulo: 'Perfil',
  icone: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4.5 20a7.5 7.5 0 0 1 15 0'
};

export const OPCOES_TEMA: { valor: PreferenciaTema; rotulo: string; icone: string }[] = [
  { valor: 'claro', rotulo: 'Claro', icone: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M12 2.5v2 M12 19.5v2 M2.5 12h2 M19.5 12h2 M5.3 5.3l1.4 1.4 M17.3 17.3l1.4 1.4 M5.3 18.7l1.4-1.4 M17.3 6.7l1.4-1.4' },
  { valor: 'escuro', rotulo: 'Escuro', icone: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z' },
  { valor: 'sistema', rotulo: 'Sistema', icone: 'M4 5h16v11H4z M9 20h6 M12 16v4' }
];

/** A partir daqui a navegação lateral é fixa; abaixo, é gaveta. */
const CONSULTA_DESKTOP = '(min-width: 1024px)';

function semQueryNemFragmento(url: string): string {
  return url.split(/[?#]/)[0] || '/';
}

@Component({
  selector: 'app-root',
  imports: [NgTemplateOutlet, RouterOutlet, RouterLink, ModalOnboardingContasComponent],
  templateUrl: './app.html',
  styleUrl: './app.css',
  host: { '(document:keydown.escape)': 'fecharMenu(true)' }
})
export class App {
  protected readonly authService = inject(AuthService);
  protected readonly temaService = inject(TemaService);
  private readonly router = inject(Router);
  private readonly consultaAoVivoService = inject(ConsultaAoVivoService);

  protected readonly opcoesTema = OPCOES_TEMA;
  protected readonly itemPerfil = ITEM_PERFIL;

  /** D-67: o link da consulta ao vivo só aparece para quem o servidor libera. */
  protected readonly consultaAoVivoHabilitada = signal(false);

  protected readonly grupos = computed(() =>
    NAVEGACAO.map((grupo) => ({
      ...grupo,
      itens: grupo.itens.filter(
        (item) => !item.exclusivoConsultaAoVivo || this.consultaAoVivoHabilitada()
      )
    }))
  );

  private readonly urlAtual = toSignal(
    this.router.events.pipe(
      filter((evento): evento is NavigationEnd => evento instanceof NavigationEnd),
      map((evento) => semQueryNemFragmento(evento.urlAfterRedirects))
    ),
    { initialValue: semQueryNemFragmento(this.router.url) }
  );

  /** Gaveta aberta (só tem efeito abaixo de lg). */
  protected readonly menuAberto = signal(false);
  private readonly botaoMenu = viewChild<ElementRef<HTMLButtonElement>>('botaoMenu');
  private readonly botaoFechar = viewChild<ElementRef<HTMLButtonElement>>('botaoFechar');

  constructor() {
    effect(() => {
      const usuarioId = this.authService.usuario()?.id ?? null;
      if (!usuarioId) {
        this.consultaAoVivoHabilitada.set(false);
        return;
      }
      void this.consultaAoVivoService
        .acesso()
        .then((acesso) => this.consultaAoVivoHabilitada.set(acesso.habilitado));
    });

    // Trocar de tela fecha a gaveta: é o que se espera ao tocar num item.
    // `untracked` não é detalhe: fecharMenu() lê menuAberto(), e sem isso o
    // efeito passaria a depender dele e fecharia a gaveta no instante em que
    // ela abrisse.
    effect(() => {
      this.urlAtual();
      untracked(() => this.fecharMenu());
    });

    // Com a gaveta aberta a página por trás não rola — senão o dedo que
    // arrasta a lista de itens arrasta junto o conteúdo escondido.
    effect(() => {
      if (typeof document !== 'undefined') {
        document.body.style.overflow = this.menuAberto() ? 'hidden' : '';
      }
    });

    // Girar o tablet para paisagem ou alargar a janela com a gaveta aberta
    // deixaria o scroll travado numa tela onde a gaveta nem existe mais.
    if (typeof matchMedia === 'function') {
      matchMedia(CONSULTA_DESKTOP).addEventListener?.('change', (evento) => {
        if (evento.matches) {
          this.fecharMenu();
        }
      });
    }
  }

  ativo(item: ItemNavegacao): boolean {
    const url = this.urlAtual();
    if (item.exato) {
      return url === item.rota;
    }
    const prefixos = [item.rota, ...(item.prefixosExtras ?? [])];
    return prefixos.some((prefixo) => url === prefixo || url.startsWith(prefixo.endsWith('/') ? prefixo : `${prefixo}/`));
  }

  abrirMenu(): void {
    this.menuAberto.set(true);
    // Foco para dentro da gaveta, senão quem usa teclado continua atrás dela.
    setTimeout(() => this.botaoFechar()?.nativeElement.focus());
  }

  fecharMenu(devolverFoco = false): void {
    if (!this.menuAberto()) {
      return;
    }
    this.menuAberto.set(false);
    if (devolverFoco) {
      this.botaoMenu()?.nativeElement.focus();
    }
  }

  async sair(): Promise<void> {
    this.fecharMenu();
    await this.authService.logout();
    await this.router.navigateByUrl('/login');
  }
}
