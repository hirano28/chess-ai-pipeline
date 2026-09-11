/** Formatação de datas compartilhada entre as telas com histórico. */

/**
 * Formata uma data ISO no padrão "dd/mm HH:mm" (pt-BR).
 * Retorna string vazia para valor ausente, e a string original se o parse falhar.
 */
export function formatarDataCurta(iso?: string | null): string {
  if (!iso) {
    return '';
  }
  try {
    const data = new Date(iso);
    return data.toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch {
    return iso;
  }
}
