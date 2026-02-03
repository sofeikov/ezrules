import { Routes } from '@angular/router';
import { RuleListComponent } from './rule-list/rule-list.component';
import { RuleDetailComponent } from './rule-detail/rule-detail.component';
import { RuleHistoryComponent } from './rule-history/rule-history.component';

export const routes: Routes = [
  { path: '', component: RuleListComponent },
  { path: 'rules', component: RuleListComponent },
  { path: 'rules/:id/history', component: RuleHistoryComponent },
  { path: 'rules/:id/revisions/:revision', component: RuleDetailComponent },
  { path: 'rules/:id', component: RuleDetailComponent }
];
