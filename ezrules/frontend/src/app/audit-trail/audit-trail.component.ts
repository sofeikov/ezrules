import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { SidebarComponent } from '../components/sidebar.component';
import {
  AuditService,
  RuleHistoryEntry,
  ConfigHistoryEntry,
  UserListHistoryEntry,
  OutcomeHistoryEntry,
  LabelHistoryEntry,
  UserAccountHistoryEntry,
  RolePermissionHistoryEntry
} from '../services/audit.service';

@Component({
  selector: 'app-audit-trail',
  standalone: true,
  imports: [CommonModule, RouterModule, SidebarComponent],
  templateUrl: './audit-trail.component.html'
})
export class AuditTrailComponent implements OnInit {
  ruleHistory: RuleHistoryEntry[] = [];
  configHistory: ConfigHistoryEntry[] = [];
  userListHistory: UserListHistoryEntry[] = [];
  outcomeHistory: OutcomeHistoryEntry[] = [];
  labelHistory: LabelHistoryEntry[] = [];
  userAccountHistory: UserAccountHistoryEntry[] = [];
  rolePermissionHistory: RolePermissionHistoryEntry[] = [];

  ruleTotal: number = 0;
  configTotal: number = 0;
  userListTotal: number = 0;
  outcomeTotal: number = 0;
  labelTotal: number = 0;
  userAccountTotal: number = 0;
  rolePermissionTotal: number = 0;

  loading: boolean = true;
  error: string | null = null;

  // Accordion state
  sections: Record<string, boolean> = {
    rules: false,
    config: false,
    userLists: false,
    outcomes: false,
    labels: false,
    userAccounts: false,
    rolePermissions: false
  };

  constructor(private auditService: AuditService) {}

  ngOnInit(): void {
    this.loadData();
  }

  toggleSection(section: string): void {
    this.sections[section] = !this.sections[section];
  }

  loadData(): void {
    this.loading = true;
    this.error = null;

    let loadCount = 0;
    const totalLoads = 7;

    const checkDone = () => {
      loadCount++;
      if (loadCount >= totalLoads) {
        this.loading = false;
      }
    };

    this.auditService.getRuleHistory(100, 0).subscribe({
      next: (response) => {
        this.ruleHistory = response.items;
        this.ruleTotal = response.total;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load rule history.';
        this.loading = false;
      }
    });

    this.auditService.getConfigHistory(100, 0).subscribe({
      next: (response) => {
        this.configHistory = response.items;
        this.configTotal = response.total;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load configuration history.';
        this.loading = false;
      }
    });

    this.auditService.getUserListHistory(100, 0).subscribe({
      next: (response) => {
        this.userListHistory = response.items;
        this.userListTotal = response.total;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load user list history.';
        this.loading = false;
      }
    });

    this.auditService.getOutcomeHistory(100, 0).subscribe({
      next: (response) => {
        this.outcomeHistory = response.items;
        this.outcomeTotal = response.total;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load outcome history.';
        this.loading = false;
      }
    });

    this.auditService.getLabelHistory(100, 0).subscribe({
      next: (response) => {
        this.labelHistory = response.items;
        this.labelTotal = response.total;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load label history.';
        this.loading = false;
      }
    });

    this.auditService.getUserAccountHistory(100, 0).subscribe({
      next: (response) => {
        this.userAccountHistory = response.items;
        this.userAccountTotal = response.total;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load user account history.';
        this.loading = false;
      }
    });

    this.auditService.getRolePermissionHistory(100, 0).subscribe({
      next: (response) => {
        this.rolePermissionHistory = response.items;
        this.rolePermissionTotal = response.total;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load role permission history.';
        this.loading = false;
      }
    });
  }

  truncateDescription(description: string, maxLength: number = 100): string {
    if (description.length <= maxLength) {
      return description;
    }
    return description.substring(0, maxLength) + '...';
  }

  formatDate(dateStr: string | null): string {
    if (!dateStr) {
      return '—';
    }
    const date = new Date(dateStr);
    return date.toLocaleString();
  }

  formatAction(action: string): string {
    return action.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }
}
