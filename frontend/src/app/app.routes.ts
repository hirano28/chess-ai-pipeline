import { Routes } from '@angular/router';
import { HexagonoRadarComponent } from './components/hexagono-radar/hexagono-radar.component';

export const routes: Routes = [
	{ path: '', component: HexagonoRadarComponent },
	{ path: '**', redirectTo: '' }
];
