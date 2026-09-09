import { Routes } from '@angular/router';
import { HexagonoRadarComponent } from './components/hexagono-radar/hexagono-radar.component';
import { LaboratorioRaciocinioComponent } from './components/laboratorio-raciocinio/laboratorio-raciocinio.component';
import { ExplicadorPosicaoComponent } from './components/explicador-posicao/explicador-posicao.component';

export const routes: Routes = [
	{ path: '', component: HexagonoRadarComponent },
	{ path: 'laboratorio', component: LaboratorioRaciocinioComponent },
	{ path: 'explicador', component: ExplicadorPosicaoComponent },
	{ path: '**', redirectTo: '' }
];
