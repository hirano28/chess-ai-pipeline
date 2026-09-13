import { Routes } from '@angular/router';
import { HexagonoRadarComponent } from './components/hexagono-radar/hexagono-radar.component';
import { LaboratorioRaciocinioComponent } from './components/laboratorio-raciocinio/laboratorio-raciocinio.component';
import { ExplicadorPosicaoComponent } from './components/explicador-posicao/explicador-posicao.component';
import { AnalisadorPartidaComponent } from './components/analisador-partida/analisador-partida.component';
import { LoginComponent } from './components/login/login.component';

// authGuard (./guards/auth.guard.ts) existe, funciona e tem teste, mas
// DELIBERADAMENTE não está aplicado aqui ainda. Aplicá-lo bloquearia hoje o
// acesso de qualquer pessoa sem conta no Supabase Auth - inclusive quem já
// usa o Laboratório só com X-API-Key - o que contradiz o objetivo desta fase
// B.1 (login sem travamento). Ligar o guard é decisão explícita de uma fase
// futura. Ver D-15 em docs/DECISOES.md.
export const routes: Routes = [
	{ path: 'login', component: LoginComponent },
	{ path: '', component: HexagonoRadarComponent },
	{ path: 'laboratorio', component: LaboratorioRaciocinioComponent },
	{ path: 'explicador', component: ExplicadorPosicaoComponent },
	{ path: 'analisador', component: AnalisadorPartidaComponent },
	{ path: '**', redirectTo: '' }
];
