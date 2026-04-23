import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { SidebarComponent } from '../components/sidebar.component';
import {
  AuditService,
  RuleHistoryEntry,
  ConfigHistoryEntry,
  StrictModeHistoryEntry,
  UserListHistoryEntry,
  OutcomeHistoryEntry,
  LabelHistoryEntry,
  UserAccountHistoryEntry,
  RolePermissionHistoryEntry,
  FieldTypeHistoryEntry,
  ApiKeyHistoryEntry
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
  strictModeHistory: StrictModeHistoryEntry[] = [];
  userListHistory: UserListHistoryEntry[] = [];
  outcomeHistory: OutcomeHistoryEntry[] = [];
  labelHistory: LabelHistoryEntry[] = [];
  userAccountHistory: UserAccountHistoryEntry[] = [];
  rolePermissionHistory: RolePermissionHistoryEntry[] = [];
  fieldTypeHistory: FieldTypeHistoryEntry[] = [];
  apiKeyHistory: ApiKeyHistoryEntry[] = [];

  ruleTotal: number = 0;
  configTotal: number = 0;
  strictModeTotal: number = 0;
  userListTotal: number = 0;
  outcomeTotal: number = 0;
  labelTotal: number = 0;
  userAccountTotal: number = 0;
  rolePermissionTotal: number = 0;
  fieldTypeTotal: number = 0;
  apiKeyTotal: number = 0;

  loading: boolean = true;
  error: string | null = null;

  // Accordion state
  sections: Record<string, boolean> = {
    rules: false,
    config: false,
    strictMode: false,
    userLists: false,
    outcomes: false,
    labels: false,
    userAccounts: false,
    rolePermissions: false,
    fieldTypes: false,
    apiKeys: false
  };

  constructor(private auditService: AuditService) {}

  ngOnInit(): void {
    if (typeof window !== 'undefined' && window.location.hash === '#strict-mode') {
      this.sections['strictMode'] = true;
    }
    this.loadData();
  }

  toggleSection(section: string): void {
    this.sections[section] = !this.sections[section];
  }

  loadData(): void {
    this.loading = true;
    this.error = null;

    let loadCount = 0;
    const totalLoads = 10;

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

    this.auditService.getStrictModeHistory(100, 0).subscribe({
      next: (response) => {
        this.strictModeHistory = response.items;
        this.strictModeTotal = response.total;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load strict mode history.';
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

    this.auditService.getFieldTypeHistory(100, 0).subscribe({
      next: (response) => {
        this.fieldTypeHistory = response.items;
        this.fieldTypeTotal = response.total;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load field type history.';
        this.loading = false;
      }
    });

    this.auditService.getApiKeyHistory(100, 0).subscribe({
      next: (response) => {
        this.apiKeyHistory = response.items;
        this.apiKeyTotal = response.total;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load API key history.';
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

  formatStatus(status: string | null): string {
    if (!status) {
      return '—';
    }
    return status.replace(/\b\w/g, c => c.toUpperCase());
  }

  ruleActionClass(action: string): string {
    if (action === 'promoted') return 'bg-green-100 text-green-800';
    if (action === 'deactivated') return 'bg-amber-100 text-amber-800';
    if (action === 'rolled_back') return 'bg-amber-100 text-amber-800';
    if (action === 'deleted') return 'bg-red-100 text-red-800';
    return 'bg-blue-100 text-blue-800';
  }

  labelActionClass(action: string): string {
    if (action === 'created') return 'bg-green-100 text-green-800';
    if (action === 'deleted') return 'bg-red-100 text-red-800';
    if (action === 'assigned' || action === 'assigned_via_csv') return 'bg-blue-100 text-blue-800';
    return 'bg-gray-100 text-gray-800';
  }

  strictModeActionClass(action: string): string {
    if (action === 'enabled') return 'bg-green-100 text-green-800';
    if (action === 'disabled') return 'bg-red-100 text-red-800';
    return 'bg-gray-100 text-gray-800';
  }
}
