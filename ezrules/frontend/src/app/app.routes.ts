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
import { RolePermissionsComponent } from './role-permissions/role-permissions.component';
import { AuditTrailComponent } from './audit-trail/audit-trail.component';
import { LoginComponent } from './login/login.component';
import { FieldTypesComponent } from './field-types/field-types.component';
import { authGuard } from './auth/auth.guard';

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  { path: '', component: DashboardComponent, canActivate: [authGuard] },
  { path: 'dashboard', component: DashboardComponent, canActivate: [authGuard] },
  { path: 'rules', component: RuleListComponent, canActivate: [authGuard] },
  { path: 'rules/create', component: RuleCreateComponent, canActivate: [authGuard] },
  { path: 'rules/:id/history', component: RuleHistoryComponent, canActivate: [authGuard] },
  { path: 'rules/:id/revisions/:revision', component: RuleDetailComponent, canActivate: [authGuard] },
  { path: 'rules/:id', component: RuleDetailComponent, canActivate: [authGuard] },
  { path: 'labels', component: LabelsComponent, canActivate: [authGuard] },
  { path: 'outcomes', component: OutcomesComponent, canActivate: [authGuard] },
  { path: 'user-lists', component: UserListsComponent, canActivate: [authGuard] },
  { path: 'label_analytics', component: LabelAnalyticsComponent, canActivate: [authGuard] },
  { path: 'management/users', component: UserManagementComponent, canActivate: [authGuard] },
  { path: 'role_management', component: RoleManagementComponent, canActivate: [authGuard] },
  { path: 'role_management/:id/permissions', component: RolePermissionsComponent, canActivate: [authGuard] },
  { path: 'audit', component: AuditTrailComponent, canActivate: [authGuard] },
  { path: 'field-types', component: FieldTypesComponent, canActivate: [authGuard] },
  { path: '**', redirectTo: '/login' }
];
