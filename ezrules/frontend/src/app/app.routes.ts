import { Routes } from '@angular/router';
import { RuleListComponent } from './rule-list/rule-list.component';
import { RuleDetailComponent } from './rule-detail/rule-detail.component';

export const routes: Routes = [
  { path: '', component: RuleListComponent },
  { path: 'rules', component: RuleListComponent },
  { path: 'rules/:id', component: RuleDetailComponent }
];
