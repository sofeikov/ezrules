import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { Change, diffLines } from 'diff';
import { SidebarComponent } from '../components/sidebar.component';
import { AuthService } from '../services/auth.service';
import {
  RolloutConfigResponse,
  RolloutRuleItem,
  RolloutRuleStatsItem,
  RolloutStatsResponse,
  RuleDetail,
  RuleService,
} from '../services/rule.service';

@Component({
  selector: 'app-rollouts',
  standalone: true,
  imports: [CommonModule, RouterModule, SidebarComponent],
  templateUrl: './rollouts.component.html'
})
export class RolloutsComponent implements OnInit {
  rolloutConfig: RolloutConfigResponse = { rules: [], version: 0 };
  rolloutStats: RolloutStatsResponse = { rules: [] };
  loading: boolean = true;
  error: string | null = null;

  showPromoteDialog: boolean = false;
  promoteTarget: RolloutRuleItem | null = null;
  promoting: boolean = false;
  promoteError: string | null = null;
  productionRule: RuleDetail | null = null;
  loadingProductionRule: boolean = false;

  actionSuccess: string | null = null;
  actionError: string | null = null;
  canPromoteRules: boolean = false;

  constructor(
    private ruleService: RuleService,
    private router: Router,
    private authService: AuthService
  ) {}

  ngOnInit(): void {
    this.loadPermissions();
    this.loadData();
  }

  loadPermissions(): void {
    this.authService.hasPermission('promote_rules').subscribe({
      next: (hasPermission) => {
        this.canPromoteRules = hasPermission;
      },
      error: () => {
        this.canPromoteRules = false;
      }
    });
  }

  loadData(): void {
    this.loading = true;
    this.error = null;

    this.ruleService.getRolloutConfig().subscribe({
      next: (config) => {
        this.rolloutConfig = config;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load rollout configuration.';
        this.loading = false;
      }
    });

    this.ruleService.getRolloutStats().subscribe({
      next: (stats) => {
        this.rolloutStats = stats;
      },
      error: () => {
        // Stats are best-effort; don't block the page.
      }
    });
  }

  openPromoteDialog(rule: RolloutRuleItem): void {
    if (!this.canPromoteRules) {
      return;
    }

    this.promoteTarget = rule;
    this.showPromoteDialog = true;
    this.promoteError = null;
    this.productionRule = null;
    this.loadingProductionRule = true;
    this.ruleService.getRule(rule.r_id).subscribe({
      next: (response) => {
        this.productionRule = response;
        this.loadingProductionRule = false;
      },
      error: () => {
        this.loadingProductionRule = false;
      }
    });
  }

  closePromoteDialog(): void {
    this.showPromoteDialog = false;
    this.promoteTarget = null;
    this.promoteError = null;
    this.productionRule = null;
  }

  computePromoteDiff(): Change[] {
    if (!this.productionRule || !this.promoteTarget) return [];
    return diffLines(this.productionRule.logic, this.promoteTarget.logic);
  }

  confirmPromote(): void {
    if (!this.promoteTarget) return;

    this.promoting = true;
    this.promoteError = null;
    this.ruleService.promoteRollout(this.promoteTarget.r_id).subscribe({
      next: (res) => {
        this.promoting = false;
        this.closePromoteDialog();
        if (res.success) {
          this.actionSuccess = res.message;
          this.actionError = null;
          this.loadData();
        } else {
          this.actionError = res.error || 'Promotion failed';
        }
      },
      error: (err) => {
        this.promoting = false;
        this.promoteError = err.error?.detail || 'Failed to promote rollout.';
      }
    });
  }

  editRollout(rule: RolloutRuleItem): void {
    this.router.navigate(['/rules', rule.r_id], {
      state: {
        rolloutEditMode: true,
        logic: rule.logic,
        description: rule.description,
        trafficPercent: rule.traffic_percent,
      },
    });
  }

  removeFromRollout(rule: RolloutRuleItem): void {
    this.ruleService.removeFromRollout(rule.r_id).subscribe({
      next: (res) => {
        if (res.success) {
          this.actionSuccess = res.message;
          this.actionError = null;
          this.loadData();
        } else {
          this.actionError = res.error || 'Remove failed';
        }
      },
      error: (err) => {
        this.actionError = err.error?.detail || 'Failed to remove rollout.';
      }
    });
  }

  getRuleStats(): { rule: RolloutRuleItem; stats: RolloutRuleStatsItem | null }[] {
    return this.rolloutConfig.rules.map(rule => ({
      rule,
      stats: this.rolloutStats.rules.find(s => s.r_id === rule.r_id) ?? null,
    }));
  }
}
