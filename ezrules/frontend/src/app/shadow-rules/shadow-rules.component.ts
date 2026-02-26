import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { diffLines, Change } from 'diff';
import { SidebarComponent } from '../components/sidebar.component';
import {
  RuleDetail,
  RuleService,
  ShadowConfigResponse,
  ShadowRuleItem,
  ShadowRuleStatsItem,
  ShadowStatsResponse,
} from '../services/rule.service';

@Component({
  selector: 'app-shadow-rules',
  standalone: true,
  imports: [CommonModule, RouterModule, SidebarComponent],
  templateUrl: './shadow-rules.component.html'
})
export class ShadowRulesComponent implements OnInit {
  shadowConfig: ShadowConfigResponse = { rules: [], version: 0 };
  shadowStats: ShadowStatsResponse = { rules: [] };
  loading: boolean = true;
  error: string | null = null;

  // Promotion dialog state
  showPromoteDialog: boolean = false;
  promoteTarget: ShadowRuleItem | null = null;
  promoting: boolean = false;
  promoteError: string | null = null;
  productionRule: RuleDetail | null = null;
  loadingProductionRule: boolean = false;

  // Action feedback
  actionSuccess: string | null = null;
  actionError: string | null = null;

  constructor(private ruleService: RuleService, private router: Router) {}

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading = true;
    this.error = null;

    this.ruleService.getShadowConfig().subscribe({
      next: (config) => {
        this.shadowConfig = config;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load shadow configuration.';
        this.loading = false;
      }
    });

    this.ruleService.getShadowStats().subscribe({
      next: (stats) => {
        this.shadowStats = stats;
      },
      error: () => {
        // Stats are best-effort; don't block the page
      }
    });
  }

  openPromoteDialog(rule: ShadowRuleItem): void {
    this.promoteTarget = rule;
    this.showPromoteDialog = true;
    this.promoteError = null;
    this.productionRule = null;
    this.loadingProductionRule = true;
    this.ruleService.getRule(rule.r_id).subscribe({
      next: (r) => {
        this.productionRule = r;
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

    this.ruleService.promoteFromShadow(this.promoteTarget.r_id).subscribe({
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
        this.promoteError = err.error?.detail || 'Failed to promote rule.';
      }
    });
  }

  editShadowRule(rule: ShadowRuleItem): void {
    this.router.navigate(['/rules', rule.r_id], {
      state: { shadowEditMode: true, logic: rule.logic, description: rule.description },
    });
  }

  removeFromShadow(rule: ShadowRuleItem): void {
    this.ruleService.removeFromShadow(rule.r_id).subscribe({
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
        this.actionError = err.error?.detail || 'Failed to remove rule from shadow.';
      }
    });
  }

  /** Returns per-rule outcome stats, ordered to match shadowConfig.rules. */
  getRuleStats(): { rule: ShadowRuleItem; stats: ShadowRuleStatsItem | null }[] {
    return this.shadowConfig.rules.map(rule => ({
      rule,
      stats: this.shadowStats.rules.find(s => s.r_id === rule.r_id) ?? null,
    }));
  }
}
