import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SidebarComponent } from '../components/sidebar.component';
import { AuditService, RuleHistoryEntry, ConfigHistoryEntry } from '../services/audit.service';

@Component({
  selector: 'app-audit-trail',
  standalone: true,
  imports: [CommonModule, SidebarComponent],
  templateUrl: './audit-trail.component.html'
})
export class AuditTrailComponent implements OnInit {
  ruleHistory: RuleHistoryEntry[] = [];
  configHistory: ConfigHistoryEntry[] = [];
  ruleTotal: number = 0;
  configTotal: number = 0;

  loading: boolean = true;
  error: string | null = null;

  constructor(private auditService: AuditService) {}

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading = true;
    this.error = null;

    let rulesLoaded = false;
    let configLoaded = false;

    const checkDone = () => {
      if (rulesLoaded && configLoaded) {
        this.loading = false;
      }
    };

    this.auditService.getRuleHistory(100, 0).subscribe({
      next: (response) => {
        this.ruleHistory = response.items;
        this.ruleTotal = response.total;
        rulesLoaded = true;
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
        configLoaded = true;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load configuration history.';
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
}
