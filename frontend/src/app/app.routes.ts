import { Routes } from '@angular/router';
import { HexagonoRadarComponent } from './components/hexagono-radar/hexagono-radar.component';
import { LaboratorioRaciocinioComponent } from './components/laboratorio-raciocinio/laboratorio-raciocinio.component';

export const routes: Routes = [
	{ path: '', component: HexagonoRadarComponent },
	{ path: 'laboratorio', component: LaboratorioRaciocinioComponent },
	{ path: '**', redirectTo: '' }
];
