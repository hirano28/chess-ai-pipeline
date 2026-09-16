import { Routes } from '@angular/router';
import { authGuard } from './guards/auth.guard';

// authGuard ligado nas rotas do dashboard (Fase B efetivamente concluída —
// ver D-23 em docs/DECISOES.md).
// Lazy-loading via loadComponent reduz drasticamente o chunk inicial do Angular (D-44).
export const routes: Routes = [
	{
		path: 'login',
		loadComponent: () => import('./components/login/login.component').then((m) => m.LoginComponent),
	},
	{
		path: '',
		loadComponent: () => import('./components/hexagono-radar/hexagono-radar.component').then((m) => m.HexagonoRadarComponent),
		canActivate: [authGuard],
	},
	{
		path: 'treino',
		loadComponent: () => import('./components/treino-do-dia/treino-do-dia.component').then((m) => m.TreinoDoDiaComponent),
		canActivate: [authGuard],
	},
	{
		path: 'laboratorio',
		loadComponent: () => import('./components/laboratorio-raciocinio/laboratorio-raciocinio.component').then((m) => m.LaboratorioRaciocinioComponent),
		canActivate: [authGuard],
	},
	{
		path: 'explicador',
		loadComponent: () => import('./components/explicador-posicao/explicador-posicao.component').then((m) => m.ExplicadorPosicaoComponent),
		canActivate: [authGuard],
	},
	{
		path: 'analisador',
		loadComponent: () => import('./components/analisador-partida/analisador-partida.component').then((m) => m.AnalisadorPartidaComponent),
		canActivate: [authGuard],
	},
	{
		path: 'perfil',
		loadComponent: () => import('./components/perfil-usuario/perfil-usuario.component').then((m) => m.PerfilUsuarioComponent),
		canActivate: [authGuard],
	},
	{ path: '**', redirectTo: '' }
];
