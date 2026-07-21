import { Component, DestroyRef, inject, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { Change, diffLines } from 'diff';
import { catchError, exhaustMap, map, merge, Observable, of, Subject, tap, timer } from 'rxjs';
import { SidebarComponent } from '../components/sidebar.component';
import { AuthService } from '../services/auth.service';
import { ACTION_PERMISSION_REQUIREMENTS, hasPermissionRequirement } from '../auth/permissions';
import {
  RolloutConfigResponse,
  RolloutRuleItem,
  RolloutRuleStatsItem,
  RolloutStatsResponse,
  RuleDetail,
  RuleService,
} from '../services/rule.service';

const ROLLOUT_REFRESH_INTERVAL_MS = 5_000;

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
  promoteDiff: Change[] = [];

  showRemoveDialog: boolean = false;
  removeTarget: RolloutRuleItem | null = null;
  removing: boolean = false;
  removeError: string | null = null;

  actionSuccess: string | null = null;
  actionError: string | null = null;
  configRefreshError: string | null = null;
  statsRefreshError: string | null = null;
  canModifyRules: boolean = false;
  canPromoteRules: boolean = false;
  private readonly destroyRef = inject(DestroyRef);
  private readonly manualRefresh$ = new Subject<boolean>();
  private hasLoadedConfig = false;

  constructor(
    private ruleService: RuleService,
    private router: Router,
    private authService: AuthService
  ) {}

  ngOnInit(): void {
    this.loadPermissions();
    this.startDataRefresh();
  }

  loadPermissions(): void {
    this.authService.getCurrentUser().subscribe({
      next: (user) => {
        this.canModifyRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.modifyRule);
        this.canPromoteRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.promoteRules);
      },
      error: () => {
        this.canModifyRules = false;
        this.canPromoteRules = false;
      }
    });
  }

  loadData(): void {
    this.manualRefresh$.next(true);
  }

  private startDataRefresh(): void {
    this.refreshEvents().pipe(
      tap(showLoading => {
        if (showLoading) {
          this.loading = true;
        }
      }),
      exhaustMap(() => this.ruleService.getRolloutConfig().pipe(
        map(config => ({ config, failed: false })),
        catchError(() => of({ config: null, failed: true }))
      )),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(({ config, failed }) => {
      if (config !== null) {
        this.rolloutConfig = config;
        this.hasLoadedConfig = true;
        this.error = null;
        this.configRefreshError = null;
      } else if (failed && this.hasLoadedConfig) {
        this.configRefreshError = 'Rollout configuration could not be refreshed. Showing the last known data.';
      } else if (failed) {
        this.error = 'Failed to load rollout configuration.';
      }
      this.loading = false;
    });

    this.refreshEvents().pipe(
      exhaustMap(() => this.ruleService.getRolloutStats().pipe(
        map(stats => ({ stats, failed: false })),
        catchError(() => of({ stats: null, failed: true }))
      )),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe(({ stats, failed }) => {
      if (stats !== null) {
        this.rolloutStats = stats;
        this.statsRefreshError = null;
      } else if (failed) {
        this.statsRefreshError = 'Rollout statistics could not be refreshed. Showing the last known data.';
      }
    });
  }

  private refreshEvents(): Observable<boolean> {
    return merge(
      timer(0, ROLLOUT_REFRESH_INTERVAL_MS).pipe(map(index => index === 0)),
      this.manualRefresh$
    );
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
    this.promoteDiff = [];
    this.ruleService.getRule(rule.r_id).subscribe({
      next: (response) => {
        this.productionRule = response;
        this.loadingProductionRule = false;
        this.promoteDiff = diffLines(response.logic, rule.logic);
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
    this.promoteDiff = [];
    this.promoting = false;
  }

  get promoteDiffIsIdentical(): boolean {
    return this.promoteDiff.length === 1 && !this.promoteDiff[0].added && !this.promoteDiff[0].removed;
  }

  get promoteDiffHasChanges(): boolean {
    return this.promoteDiff.length > 1 || !!this.promoteDiff[0]?.added || !!this.promoteDiff[0]?.removed;
  }

  openRemoveDialog(rule: RolloutRuleItem): void {
    this.showRemoveDialog = true;
    this.removeTarget = rule;
    this.removeError = null;
    this.removing = false;
  }

  closeRemoveDialog(): void {
    this.showRemoveDialog = false;
    this.removeTarget = null;
    this.removeError = null;
    this.removing = false;
  }

  confirmRemove(): void {
    if (!this.removeTarget) {
      return;
    }

    this.removing = true;
    this.removeError = null;

    this.ruleService.removeFromRollout(this.removeTarget.r_id).subscribe({
      next: (res) => {
        this.removing = false;
        if (res.success) {
          this.closeRemoveDialog();
          this.actionSuccess = res.message;
          this.actionError = null;
          this.loadData();
        } else {
          this.removeError = res.error || 'Remove failed';
        }
      },
      error: (err) => {
        this.removing = false;
        this.removeError = err.error?.detail || 'Failed to remove rollout.';
      }
    });
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
    if (!this.canModifyRules) {
      return;
    }

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
    if (!this.canPromoteRules) {
      return;
    }

    this.openRemoveDialog(rule);
  }

  getRuleStats(): { rule: RolloutRuleItem; stats: RolloutRuleStatsItem | null }[] {
    return this.rolloutConfig.rules.map(rule => ({
      rule,
      stats: this.rolloutStats.rules.find(s => s.r_id === rule.r_id) ?? null,
    }));
  }

  showReadOnlyNotice(): boolean {
    return !this.canModifyRules && !this.canPromoteRules;
  }
}
