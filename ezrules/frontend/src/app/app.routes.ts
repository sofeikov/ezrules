import { Routes } from '@angular/router';
import { RuleListComponent } from './rule-list/rule-list.component';

export const routes: Routes = [
  { path: '', component: RuleListComponent },
  { path: 'rules', component: RuleListComponent }
];
