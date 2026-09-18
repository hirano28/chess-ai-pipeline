import { Routes } from '@angular/router';
import { authGuard } from './guards/auth.guard';
import { consultaAoVivoGuard } from './guards/consulta-ao-vivo.guard';

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
	// D-71: os blocos que ficavam na rolagem da página do Hexágono ganharam rota.
	{
		path: 'aberturas',
		loadComponent: () => import('./components/diagnostico-secao/diagnostico-secao.component').then((m) => m.DiagnosticoSecaoComponent),
		canActivate: [authGuard],
		data: { secao: 'aberturas' },
	},
	{
		path: 'puzzles',
		loadComponent: () => import('./components/diagnostico-secao/diagnostico-secao.component').then((m) => m.DiagnosticoSecaoComponent),
		canActivate: [authGuard],
		data: { secao: 'puzzles' },
	},
	{
		path: 'plano',
		loadComponent: () => import('./components/diagnostico-secao/diagnostico-secao.component').then((m) => m.DiagnosticoSecaoComponent),
		canActivate: [authGuard],
		data: { secao: 'plano' },
	},
	{
		path: 'treino',
		loadComponent: () => import('./components/treino-do-dia/treino-do-dia.component').then((m) => m.TreinoDoDiaComponent),
		canActivate: [authGuard],
	},
	{
		path: 'sessao/:id',
		loadComponent: () => import('./components/sessao-execucao/sessao-execucao.component').then((m) => m.SessaoExecucaoComponent),
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
		// D-81: busca livre no acervo de livros já indexados.
		path: 'biblioteca',
		loadComponent: () => import('./components/biblioteca/biblioteca.component').then((m) => m.BibliotecaComponent),
		canActivate: [authGuard],
	},
	{
		path: 'analisador',
		loadComponent: () => import('./components/analisador-partida/analisador-partida.component').then((m) => m.AnalisadorPartidaComponent),
		canActivate: [authGuard],
	},
	{
		// D-67: exclusiva do dono do projeto; o segundo guard pergunta ao servidor.
		path: 'consulta-ao-vivo',
		loadComponent: () => import('./components/consulta-ao-vivo/consulta-ao-vivo.component').then((m) => m.ConsultaAoVivoComponent),
		canActivate: [authGuard, consultaAoVivoGuard],
	},
	{
		path: 'perfil',
		loadComponent: () => import('./components/perfil-usuario/perfil-usuario.component').then((m) => m.PerfilUsuarioComponent),
		canActivate: [authGuard],
	},
	{ path: '**', redirectTo: '' }
];
