import { Routes } from '@angular/router';
import { RuleListComponent } from './rule-list/rule-list.component';
import { RuleDetailComponent } from './rule-detail/rule-detail.component';
import { RuleHistoryComponent } from './rule-history/rule-history.component';
import { RuleCreateComponent } from './rule-create/rule-create.component';
import { LabelsComponent } from './labels/labels.component';
import { OutcomesComponent } from './outcomes/outcomes.component';
import { LabelAnalyticsComponent } from './label-analytics/label-analytics.component';
import { UserListsComponent } from './user-lists/user-lists.component';
import { DashboardComponent } from './dashboard/dashboard.component';
import { UserManagementComponent } from './user-management/user-management.component';
import { RoleManagementComponent } from './role-management/role-management.component';

export const routes: Routes = [
  { path: '', component: DashboardComponent },
  { path: 'dashboard', component: DashboardComponent },
  { path: 'rules', component: RuleListComponent },
  { path: 'rules/create', component: RuleCreateComponent },
  { path: 'rules/:id/history', component: RuleHistoryComponent },
  { path: 'rules/:id/revisions/:revision', component: RuleDetailComponent },
  { path: 'rules/:id', component: RuleDetailComponent },
  { path: 'labels', component: LabelsComponent },
  { path: 'outcomes', component: OutcomesComponent },
  { path: 'user-lists', component: UserListsComponent },
  { path: 'label_analytics', component: LabelAnalyticsComponent },
  { path: 'management/users', component: UserManagementComponent },
  { path: 'role_management', component: RoleManagementComponent }
];
