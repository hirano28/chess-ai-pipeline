import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { ConsultaAoVivoService } from '../services/consulta-ao-vivo.service';

/**
 * A consulta ao vivo é exclusiva do dono do projeto (D-67). Quem digitar a URL
 * sem estar liberado volta para o Hexágono — a regra de quem pode mora no
 * servidor, e este guard só pergunta a ele. Roda depois do `authGuard`.
 */
export const consultaAoVivoGuard: CanActivateFn = async () => {
  const service = inject(ConsultaAoVivoService);
  const router = inject(Router);
  const acesso = await service.acesso();
  return acesso.habilitado ? true : router.parseUrl('/');
};
