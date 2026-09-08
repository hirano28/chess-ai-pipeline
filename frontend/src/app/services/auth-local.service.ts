import { Injectable } from '@angular/core';

const STORAGE_KEY = 'lab_api_key';

/** Guarda a chave de acesso ao servidor Python (backend/api) no localStorage. */
@Injectable({ providedIn: 'root' })
export class AuthLocalService {
  getKey(): string | null {
    return localStorage.getItem(STORAGE_KEY);
  }

  setKey(chave: string): void {
    localStorage.setItem(STORAGE_KEY, chave);
  }

  clearKey(): void {
    localStorage.removeItem(STORAGE_KEY);
  }

  isConfigured(): boolean {
    return !!this.getKey();
  }
}
