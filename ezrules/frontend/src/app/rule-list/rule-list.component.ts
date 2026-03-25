import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { environment } from '../../environments/environment';
import { AuthService } from '../services/auth.service';
import { ACTION_PERMISSION_REQUIREMENTS, hasPermissionRequirement } from '../auth/permissions';
import { Rule, RuleService, RuleStatus } from '../services/rule.service';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-rule-list',
  standalone: true,
  imports: [CommonModule, RouterModule, SidebarComponent],
  templateUrl: './rule-list.component.html'
})
export class RuleListComponent implements OnInit {
  rules: Rule[] = [];
  evaluateEndpoint: string = `${environment.apiUrl}/api/v2/evaluate`;
  loading: boolean = true;
  error: string | null = null;
  showHowToRun: boolean = false;
  actionError: string | null = null;
  actionLoading: Record<number, 'promote' | 'archive'> = {};
  canCreateRules: boolean = false;
  canModifyRules: boolean = false;
  canPromoteRules: boolean = false;

  constructor(private ruleService: RuleService, private authService: AuthService) { }

  ngOnInit(): void {
    this.loadPermissions();
    this.loadRules();
  }

  loadPermissions(): void {
    this.authService.getCurrentUser().subscribe({
      next: (user) => {
        this.canCreateRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.createRule);
        this.canModifyRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.modifyRule);
        this.canPromoteRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.promoteRules);
      },
      error: () => {
        this.canCreateRules = false;
        this.canModifyRules = false;
        this.canPromoteRules = false;
      }
    });
  }

  loadRules(): void {
    this.loading = true;
    this.error = null;
    this.actionError = null;

    this.ruleService.getRules().subscribe({
      next: (response) => {
        this.rules = response.rules;
        this.loading = false;
      },
      error: (error) => {
        this.error = 'Failed to load rules. Please try again.';
        this.loading = false;
        console.error('Error loading rules:', error);
      }
    });
  }

  promoteRule(rule: Rule): void {
    if (rule.status !== 'draft') {
      return;
    }
    this.actionError = null;
    this.actionLoading[rule.r_id] = 'promote';
    this.ruleService.promoteRule(rule.r_id).subscribe({
      next: (response) => {
        delete this.actionLoading[rule.r_id];
        if (response.success) {
          this.loadRules();
          return;
        }
        this.actionError = response.error || 'Failed to promote rule.';
      },
      error: (error) => {
        delete this.actionLoading[rule.r_id];
        this.actionError = error.error?.detail || error.error?.error || 'Failed to promote rule.';
      }
    });
  }

  archiveRule(rule: Rule): void {
    if (rule.status === 'archived') {
      return;
    }
    const confirmed = window.confirm(`Archive rule ${rule.rid}?`);
    if (!confirmed) {
      return;
    }
    this.actionError = null;
    this.actionLoading[rule.r_id] = 'archive';
    this.ruleService.archiveRule(rule.r_id).subscribe({
      next: (response) => {
        delete this.actionLoading[rule.r_id];
        if (response.success) {
          this.loadRules();
          return;
        }
        this.actionError = response.error || 'Failed to archive rule.';
      },
      error: (error) => {
        delete this.actionLoading[rule.r_id];
        this.actionError = error.error?.detail || error.error?.error || 'Failed to archive rule.';
      }
    });
  }

  isActionLoading(ruleId: number, action: 'promote' | 'archive'): boolean {
    return this.actionLoading[ruleId] === action;
  }

  canPromote(rule: Rule): boolean {
    return this.canPromoteRules && rule.status === 'draft';
  }

  canArchive(rule: Rule): boolean {
    return this.canModifyRules && rule.status !== 'archived';
  }

  statusLabel(status: RuleStatus): string {
    if (status === 'active') return 'ACTIVE';
    if (status === 'archived') return 'ARCHIVED';
    return 'DRAFT';
  }

  statusClass(status: RuleStatus): string {
    if (status === 'active') return 'bg-green-100 text-green-800';
    if (status === 'archived') return 'bg-gray-200 text-gray-700';
    return 'bg-amber-100 text-amber-800';
  }

  toggleHowToRun(): void {
    this.showHowToRun = !this.showHowToRun;
  }

  formatDate(dateString: string | null): string {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  }

  showReadOnlyNotice(): boolean {
    return !this.canCreateRules && !this.canModifyRules && !this.canPromoteRules;
  }
}
