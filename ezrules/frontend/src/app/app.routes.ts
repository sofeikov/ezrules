import { Routes } from '@angular/router';
import { RuleListComponent } from './rule-list/rule-list.component';
import { RuleDetailComponent } from './rule-detail/rule-detail.component';
import { RuleHistoryComponent } from './rule-history/rule-history.component';
import { RuleCreateComponent } from './rule-create/rule-create.component';
import { LabelsComponent } from './labels/labels.component';
import { OutcomesComponent } from './outcomes/outcomes.component';
import { LabelAnalyticsComponent } from './label-analytics/label-analytics.component';
import { RuleQualityComponent } from './rule-quality/rule-quality.component';
import { UserListsComponent } from './user-lists/user-lists.component';
import { DashboardComponent } from './dashboard/dashboard.component';
import { UserManagementComponent } from './user-management/user-management.component';
import { RoleManagementComponent } from './role-management/role-management.component';
import { RolePermissionsComponent } from './role-permissions/role-permissions.component';
import { AuditTrailComponent } from './audit-trail/audit-trail.component';
import { LoginComponent } from './login/login.component';
import { FieldTypesComponent } from './field-types/field-types.component';
import { ShadowRulesComponent } from './shadow-rules/shadow-rules.component';
import { RolloutsComponent } from './rollouts/rollouts.component';
import { ApiKeysComponent } from './api-keys/api-keys.component';
import { TestedEventsComponent } from './tested-events/tested-events.component';
import { EventTesterComponent } from './event-tester/event-tester.component';
import { authGuard } from './auth/auth.guard';
import { ForgotPasswordComponent } from './forgot-password/forgot-password.component';
import { ResetPasswordComponent } from './reset-password/reset-password.component';
import { AcceptInviteComponent } from './accept-invite/accept-invite.component';
import { SettingsComponent } from './settings/settings.component';
import { AlertsComponent } from './alerts/alerts.component';
import { AccessDeniedComponent } from './access-denied/access-denied.component';
import { permissionGuard } from './auth/permission.guard';
import { ROUTE_PERMISSION_REQUIREMENTS } from './auth/permissions';

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  { path: 'forgot-password', component: ForgotPasswordComponent },
  { path: 'reset-password', component: ResetPasswordComponent },
  { path: 'accept-invite', component: AcceptInviteComponent },
  {
    path: '',
    component: DashboardComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.dashboard }
  },
  {
    path: 'dashboard',
    component: DashboardComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.dashboard }
  },
  {
    path: 'rules',
    component: RuleListComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.rules }
  },
  {
    path: 'rules/create',
    component: RuleCreateComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.ruleCreate }
  },
  {
    path: 'rules/:id/history',
    component: RuleHistoryComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.rules }
  },
  {
    path: 'rules/:id/revisions/:revision',
    component: RuleDetailComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.rules }
  },
  {
    path: 'rules/:id',
    component: RuleDetailComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.rules }
  },
  {
    path: 'labels',
    component: LabelsComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.labels }
  },
  {
    path: 'outcomes',
    component: OutcomesComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.outcomes }
  },
  {
    path: 'tested-events',
    component: TestedEventsComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.testedEvents }
  },
  {
    path: 'event-tester',
    component: EventTesterComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.eventTester }
  },
  {
    path: 'user-lists',
    component: UserListsComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.userLists }
  },
  {
    path: 'label_analytics',
    component: LabelAnalyticsComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.labelAnalytics }
  },
  {
    path: 'rule-quality',
    component: RuleQualityComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.ruleQuality }
  },
  {
    path: 'settings',
    component: SettingsComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.settings }
  },
  {
    path: 'alerts',
    component: AlertsComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.alerts }
  },
  {
    path: 'management/users',
    component: UserManagementComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.users }
  },
  {
    path: 'role_management',
    component: RoleManagementComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.roles }
  },
  {
    path: 'role_management/:id/permissions',
    component: RolePermissionsComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.roles }
  },
  {
    path: 'audit',
    component: AuditTrailComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.audit }
  },
  {
    path: 'field-types',
    component: FieldTypesComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.fieldTypes }
  },
  {
    path: 'shadow-rules',
    component: ShadowRulesComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.shadowRules }
  },
  {
    path: 'rule-rollouts',
    component: RolloutsComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.rollouts }
  },
  {
    path: 'api-keys',
    component: ApiKeysComponent,
    canActivate: [authGuard, permissionGuard],
    data: { permissionRequirement: ROUTE_PERMISSION_REQUIREMENTS.apiKeys }
  },
  { path: 'access-denied', component: AccessDeniedComponent, canActivate: [authGuard] },
  { path: '**', redirectTo: '/login' }
];
