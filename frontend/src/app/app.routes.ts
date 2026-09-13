import { Routes } from '@angular/router';
import { HexagonoRadarComponent } from './components/hexagono-radar/hexagono-radar.component';
import { LaboratorioRaciocinioComponent } from './components/laboratorio-raciocinio/laboratorio-raciocinio.component';
import { ExplicadorPosicaoComponent } from './components/explicador-posicao/explicador-posicao.component';
import { AnalisadorPartidaComponent } from './components/analisador-partida/analisador-partida.component';
import { LoginComponent } from './components/login/login.component';
import { authGuard } from './guards/auth.guard';

// authGuard ligado nas 4 rotas do dashboard (Fase B efetivamente concluída —
// ver D-23 em docs/DECISOES.md). Decisão explícita e confirmada: os 4 amigos
// que hoje só têm X-API-Key nomeada (D-7), sem conta Supabase Auth, ficam
// sem acesso a estas telas até migrarem — a migração citada como pendência
// em P-11 deixa de ser opcional a partir daqui. Login continua sem guard,
// óbvio, senão ninguém conseguiria entrar.
export const routes: Routes = [
	{ path: 'login', component: LoginComponent },
	{ path: '', component: HexagonoRadarComponent, canActivate: [authGuard] },
	{ path: 'laboratorio', component: LaboratorioRaciocinioComponent, canActivate: [authGuard] },
	{ path: 'explicador', component: ExplicadorPosicaoComponent, canActivate: [authGuard] },
	{ path: 'analisador', component: AnalisadorPartidaComponent, canActivate: [authGuard] },
	{ path: '**', redirectTo: '' }
];
