import { Routes } from '@angular/router';
import { RuleListComponent } from './rule-list/rule-list.component';
import { RuleDetailComponent } from './rule-detail/rule-detail.component';
import { RuleHistoryComponent } from './rule-history/rule-history.component';
import { RuleCreateComponent } from './rule-create/rule-create.component';
import { LabelsComponent } from './labels/labels.component';
import { OutcomesComponent } from './outcomes/outcomes.component';
import { LabelAnalyticsComponent } from './label-analytics/label-analytics.component';

export const routes: Routes = [
  { path: '', component: RuleListComponent },
  { path: 'rules', component: RuleListComponent },
  { path: 'rules/create', component: RuleCreateComponent },
  { path: 'rules/:id/history', component: RuleHistoryComponent },
  { path: 'rules/:id/revisions/:revision', component: RuleDetailComponent },
  { path: 'rules/:id', component: RuleDetailComponent },
  { path: 'labels', component: LabelsComponent },
  { path: 'outcomes', component: OutcomesComponent },
  { path: 'label_analytics', component: LabelAnalyticsComponent }
];
