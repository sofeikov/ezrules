import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ACTION_PERMISSION_REQUIREMENTS, hasPermissionRequirement } from '../auth/permissions';
import { SidebarComponent } from '../components/sidebar.component';
import { AlertIncident, AlertRule, AlertService } from '../services/alert.service';
import { AuthService } from '../services/auth.service';
import { OutcomeItem, OutcomeService } from '../services/outcome.service';

@Component({
  selector: 'app-alerts',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent],
  templateUrl: './alerts.component.html'
})
export class AlertsComponent implements OnInit {
  rules: AlertRule[] = [];
  incidents: AlertIncident[] = [];
  outcomes: OutcomeItem[] = [];
  loading = true;
  outcomesLoading = true;
  saving = false;
  error: string | null = null;
  success: string | null = null;
  canManageAlerts = false;

  newRule = {
    name: 'CANCEL spike',
    outcome: 'CANCEL',
    threshold: 50,
    window_seconds: 3600,
    cooldown_seconds: 1800,
    enabled: true,
  };

  constructor(
    private alertService: AlertService,
    private authService: AuthService,
    private outcomeService: OutcomeService,
  ) {}

  ngOnInit(): void {
    this.authService.getCurrentUser().subscribe({
      next: (user) => {
        this.canManageAlerts = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.manageAlerts);
      },
      error: () => {
        this.canManageAlerts = false;
      }
    });
    this.loadOutcomes();
    this.loadAlerts();
  }

  loadOutcomes(): void {
    this.outcomesLoading = true;
    this.outcomeService.getOutcomes().subscribe({
      next: (response) => {
        this.outcomes = response.outcomes;
        if (this.outcomes.length > 0 && !this.outcomes.some(outcome => outcome.outcome_name === this.newRule.outcome)) {
          this.newRule.outcome = this.outcomes[0].outcome_name;
        }
        this.outcomesLoading = false;
      },
      error: () => {
        this.error = 'Failed to load configured outcomes.';
        this.outcomesLoading = false;
      }
    });
  }

  loadAlerts(): void {
    this.loading = true;
    this.error = null;
    this.alertService.getAlertRules().subscribe({
      next: (rulesResponse) => {
        this.rules = rulesResponse.rules;
        this.alertService.getAlertIncidents().subscribe({
          next: (incidentsResponse) => {
            this.incidents = incidentsResponse.incidents;
            this.loading = false;
          },
          error: () => {
            this.error = 'Failed to load alert incidents.';
            this.loading = false;
          }
        });
      },
      error: () => {
        this.error = 'Failed to load alert rules.';
        this.loading = false;
      }
    });
  }

  createRule(): void {
    if (!this.canManageAlerts || this.saving) {
      return;
    }

    this.error = null;
    this.success = null;
    this.saving = true;
    this.alertService.createAlertRule({
      name: this.newRule.name.trim(),
      outcome: this.newRule.outcome,
      threshold: Number(this.newRule.threshold),
      window_seconds: Number(this.newRule.window_seconds),
      cooldown_seconds: Number(this.newRule.cooldown_seconds),
      enabled: this.newRule.enabled,
    }).subscribe({
      next: () => {
        this.success = 'Alert rule created.';
        this.saving = false;
        this.loadAlerts();
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Failed to create alert rule.';
        this.saving = false;
      }
    });
  }

  toggleRule(rule: AlertRule): void {
    if (!this.canManageAlerts) {
      return;
    }
    this.alertService.updateAlertRule(rule.id, { enabled: !rule.enabled }).subscribe({
      next: () => this.loadAlerts(),
      error: () => {
        this.error = 'Failed to update alert rule.';
      }
    });
  }

  acknowledgeIncident(incident: AlertIncident): void {
    this.alertService.acknowledgeIncident(incident.id).subscribe({
      next: () => this.loadAlerts(),
      error: () => {
        this.error = 'Failed to acknowledge alert incident.';
      }
    });
  }
}
