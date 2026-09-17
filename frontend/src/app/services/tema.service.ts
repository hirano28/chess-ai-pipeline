import { Injectable, computed, effect, signal } from '@angular/core';

/** O que a pessoa escolheu. `sistema` segue o claro/escuro do aparelho. */
export type PreferenciaTema = 'sistema' | 'claro' | 'escuro';
/** O tema efetivamente aplicado. */
export type Tema = 'claro' | 'escuro';

/** Mesma chave lida pelo script inline de src/index.html — mudar uma é mudar as duas. */
export const CHAVE_TEMA = 'hexagono:tema';

/** Cor da barra do navegador no celular, igual ao fundo da página de cada tema. */
const COR_BARRA: Record<Tema, string> = { claro: '#f3f1eb', escuro: '#0c1519' };

const CONSULTA_ESCURO = '(prefers-color-scheme: dark)';

function lerPreferencia(): PreferenciaTema {
  try {
    const salvo = localStorage.getItem(CHAVE_TEMA);
    return salvo === 'claro' || salvo === 'escuro' ? salvo : 'sistema';
  } catch {
    return 'sistema';
  }
}

function sistemaEstaEscuro(): boolean {
  return typeof matchMedia === 'function' && matchMedia(CONSULTA_ESCURO).matches;
}

/**
 * Tema claro/escuro (D-71).
 *
 * As cores moram em src/styles.css como variáveis; trocar de tema é só trocar
 * `data-tema` no <html>. O script inline do index.html já aplica o tema antes
 * do Angular subir — sem ele, quem usa o claro veria um lampejo do escuro a
 * cada recarga. Este serviço assume dali em diante: aplica a escolha, guarda,
 * e acompanha o aparelho quando a preferência é "sistema".
 */
@Injectable({ providedIn: 'root' })
export class TemaService {
  readonly preferencia = signal<PreferenciaTema>(lerPreferencia());
  private readonly sistemaEscuro = signal(sistemaEstaEscuro());

  readonly tema = computed<Tema>(() => {
    const preferencia = this.preferencia();
    if (preferencia !== 'sistema') {
      return preferencia;
    }
    return this.sistemaEscuro() ? 'escuro' : 'claro';
  });

  constructor() {
    if (typeof matchMedia === 'function') {
      matchMedia(CONSULTA_ESCURO).addEventListener?.('change', (evento) =>
        this.sistemaEscuro.set(evento.matches)
      );
    }
    effect(() => this.aplicar(this.tema()));
  }

  escolher(preferencia: PreferenciaTema): void {
    this.preferencia.set(preferencia);
    try {
      if (preferencia === 'sistema') {
        localStorage.removeItem(CHAVE_TEMA);
      } else {
        localStorage.setItem(CHAVE_TEMA, preferencia);
      }
    } catch {
      // Sem armazenamento (aba privada, bloqueio): a escolha vale até recarregar.
    }
  }

  private aplicar(tema: Tema): void {
    if (typeof document === 'undefined') {
      return;
    }
    const raiz = document.documentElement;
    raiz.dataset['tema'] = tema;
    raiz.style.colorScheme = tema === 'escuro' ? 'dark' : 'light';
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', COR_BARRA[tema]);
  }
}
