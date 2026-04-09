import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { environment } from '../../environments/environment';
import { AuthService } from '../services/auth.service';
import { ACTION_PERMISSION_REQUIREMENTS, hasPermissionRequirement } from '../auth/permissions';
import { Rule, RuleService, RuleStatus } from '../services/rule.service';
import { RuntimeSettingsService } from '../services/runtime-settings.service';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-rule-list',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, SidebarComponent],
  templateUrl: './rule-list.component.html'
})
export class RuleListComponent implements OnInit {
  rules: Rule[] = [];
  originalRules: Rule[] = [];
  evaluateEndpoint: string = `${environment.apiUrl}/api/v2/evaluate`;
  loading: boolean = true;
  error: string | null = null;
  showHowToRun: boolean = false;
  actionError: string | null = null;
  actionLoading: Record<number, 'promote' | 'pause' | 'resume' | 'archive'> = {};
  orderSaving: boolean = false;
  orderDirty: boolean = false;
  reorderMode: boolean = false;
  directPositionRuleId: number | null = null;
  directPositionValue: number | null = null;
  canCreateRules: boolean = false;
  canModifyRules: boolean = false;
  canReorderRules: boolean = false;
  canPauseRules: boolean = false;
  canPromoteRules: boolean = false;
  mainRuleExecutionMode: string = 'all_matches';

  constructor(
    private ruleService: RuleService,
    private authService: AuthService,
    private runtimeSettingsService: RuntimeSettingsService,
  ) { }

  ngOnInit(): void {
    this.loadPermissions();
    this.loadRuntimeSettings();
    this.loadRules();
  }

  loadPermissions(): void {
    this.authService.getCurrentUser().subscribe({
      next: (user) => {
        this.canCreateRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.createRule);
        this.canModifyRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.modifyRule);
        this.canReorderRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.reorderRules);
        this.canPauseRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.pauseRules);
        this.canPromoteRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.promoteRules);
      },
      error: () => {
        this.canCreateRules = false;
        this.canModifyRules = false;
        this.canReorderRules = false;
        this.canPauseRules = false;
        this.canPromoteRules = false;
      }
    });
  }

  loadRuntimeSettings(): void {
    this.runtimeSettingsService.getRuntimeSettings().subscribe({
      next: (settings) => {
        this.mainRuleExecutionMode = settings.mainRuleExecutionMode;
      },
      error: () => {
        this.mainRuleExecutionMode = 'all_matches';
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
        this.originalRules = response.rules.map((rule) => ({ ...rule }));
        this.orderDirty = false;
        this.reorderMode = false;
        this.directPositionRuleId = null;
        this.directPositionValue = null;
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

  pauseRule(rule: Rule): void {
    if (rule.status !== 'active') {
      return;
    }
    const confirmed = window.confirm(`Pause rule ${rule.rid}?`);
    if (!confirmed) {
      return;
    }
    this.actionError = null;
    this.actionLoading[rule.r_id] = 'pause';
    this.ruleService.pauseRule(rule.r_id).subscribe({
      next: (response) => {
        delete this.actionLoading[rule.r_id];
        if (response.success) {
          this.loadRules();
          return;
        }
        this.actionError = response.error || 'Failed to pause rule.';
      },
      error: (error) => {
        delete this.actionLoading[rule.r_id];
        this.actionError = error.error?.detail || error.error?.error || 'Failed to pause rule.';
      }
    });
  }

  resumeRule(rule: Rule): void {
    if (rule.status !== 'paused') {
      return;
    }
    this.actionError = null;
    this.actionLoading[rule.r_id] = 'resume';
    this.ruleService.resumeRule(rule.r_id).subscribe({
      next: (response) => {
        delete this.actionLoading[rule.r_id];
        if (response.success) {
          this.loadRules();
          return;
        }
        this.actionError = response.error || 'Failed to resume rule.';
      },
      error: (error) => {
        delete this.actionLoading[rule.r_id];
        this.actionError = error.error?.detail || error.error?.error || 'Failed to resume rule.';
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

  isActionLoading(ruleId: number, action: 'promote' | 'pause' | 'resume' | 'archive'): boolean {
    return this.actionLoading[ruleId] === action;
  }

  canPromote(rule: Rule): boolean {
    return this.canPromoteRules && rule.status === 'draft';
  }

  canPause(rule: Rule): boolean {
    return this.canPauseRules && rule.status === 'active';
  }

  canResume(rule: Rule): boolean {
    return this.canPromoteRules && rule.status === 'paused';
  }

  canArchive(rule: Rule): boolean {
    return this.canModifyRules && rule.status !== 'archived';
  }

  statusLabel(status: RuleStatus): string {
    if (status === 'active') return 'ACTIVE';
    if (status === 'paused') return 'PAUSED';
    if (status === 'archived') return 'ARCHIVED';
    return 'DRAFT';
  }

  statusClass(status: RuleStatus): string {
    if (status === 'active') return 'bg-green-100 text-green-800';
    if (status === 'paused') return 'bg-yellow-100 text-yellow-800';
    if (status === 'archived') return 'bg-gray-200 text-gray-700';
    return 'bg-amber-100 text-amber-800';
  }

  toggleHowToRun(): void {
    this.showHowToRun = !this.showHowToRun;
  }

  showExecutionOrderUi(): boolean {
    return this.mainRuleExecutionMode === 'first_match';
  }

  canReorder(rule: Rule): boolean {
    return (
      this.showExecutionOrderUi() &&
      this.reorderMode &&
      this.canReorderRules &&
      rule.evaluation_lane === 'main' &&
      rule.status !== 'archived'
    );
  }

  toggleReorderMode(): void {
    if (!this.showExecutionOrderUi() || !this.canReorderRules || this.orderSaving) {
      return;
    }
    if (this.reorderMode && this.orderDirty) {
      return;
    }
    this.reorderMode = !this.reorderMode;
    if (!this.reorderMode) {
      this.directPositionRuleId = null;
      this.directPositionValue = null;
    }
  }

  cancelRuleOrderChanges(): void {
    this.rules = this.originalRules.map((rule) => ({ ...rule }));
    this.orderDirty = false;
    this.reorderMode = false;
    this.directPositionRuleId = null;
    this.directPositionValue = null;
    this.actionError = null;
  }

  moveRule(index: number, direction: -1 | 1): void {
    const rule = this.rules[index];
    if (!rule || !this.canReorder(rule)) {
      return;
    }

    let targetIndex = index + direction;
    while (targetIndex >= 0 && targetIndex < this.rules.length) {
      if (this.rules[targetIndex].evaluation_lane === 'main' && this.rules[targetIndex].status !== 'archived') {
        break;
      }
      targetIndex += direction;
    }

    if (targetIndex < 0 || targetIndex >= this.rules.length) {
      return;
    }

    const reordered = [...this.rules];
    const [item] = reordered.splice(index, 1);
    reordered.splice(targetIndex, 0, item);

    const reorderedMainRules = reordered.filter(
      (currentRule) => currentRule.evaluation_lane === 'main' && currentRule.status !== 'archived'
    );
    this.rules = this.rebuildRulesWithMainOrder(reorderedMainRules);
    this.orderDirty = true;
  }

  canMoveRule(index: number, direction: -1 | 1): boolean {
    const rule = this.rules[index];
    if (!rule || !this.canReorder(rule)) {
      return false;
    }

    let targetIndex = index + direction;
    while (targetIndex >= 0 && targetIndex < this.rules.length) {
      if (this.rules[targetIndex].evaluation_lane === 'main' && this.rules[targetIndex].status !== 'archived') {
        return true;
      }
      targetIndex += direction;
    }

    return false;
  }

  saveRuleOrder(): void {
    this.actionError = null;
    this.orderSaving = true;
    const orderedMainRuleIds = this.mainRules().map((rule) => rule.r_id);

    this.ruleService.updateMainRuleOrder({ ordered_r_ids: orderedMainRuleIds }).subscribe({
      next: (response) => {
        this.orderSaving = false;
        if (response.success) {
          this.loadRules();
          return;
        }
        this.actionError = response.message || 'Failed to save rule order.';
      },
      error: (error) => {
        this.orderSaving = false;
        this.actionError = error.error?.detail || error.error?.error || 'Failed to save rule order.';
      }
    });
  }

  mainRules(): Rule[] {
    return this.rules.filter((rule) => rule.evaluation_lane === 'main' && rule.status !== 'archived');
  }

  openDirectPositionEditor(rule: Rule): void {
    if (!this.canReorder(rule) || this.orderSaving) {
      return;
    }
    if (this.directPositionRuleId === rule.r_id) {
      this.directPositionRuleId = null;
      this.directPositionValue = null;
      return;
    }
    this.directPositionRuleId = rule.r_id;
    this.directPositionValue = rule.execution_order;
  }

  applyDirectPosition(rule: Rule): void {
    if (!this.reorderMode || this.directPositionRuleId !== rule.r_id || this.directPositionValue === null) {
      return;
    }

    const mainRules = this.mainRules();
    const currentIndex = mainRules.findIndex((mainRule) => mainRule.r_id === rule.r_id);
    const requestedIndex = Math.max(0, Math.min(mainRules.length - 1, Math.floor(this.directPositionValue) - 1));
    if (currentIndex === -1 || currentIndex === requestedIndex) {
      this.directPositionRuleId = null;
      this.directPositionValue = null;
      return;
    }

    const reorderedMainRules = [...mainRules];
    const [selectedRule] = reorderedMainRules.splice(currentIndex, 1);
    reorderedMainRules.splice(requestedIndex, 0, selectedRule);

    const reorderedIds = reorderedMainRules.map((rule) => rule.r_id);
    const nextOrderByRuleId = new Map<number, number>();
    reorderedMainRules.forEach((rule, index) => {
      nextOrderByRuleId.set(rule.r_id, index + 1);
    });

    this.rules = this.rebuildRulesWithMainOrder(
      reorderedMainRules.map((currentRule) => ({
        ...currentRule,
        execution_order: nextOrderByRuleId.get(currentRule.r_id) ?? currentRule.execution_order,
      }))
    );

    this.orderDirty = true;
    this.directPositionRuleId = null;
    this.directPositionValue = null;
  }

  private rebuildRulesWithMainOrder(reorderedMainRules: Rule[]): Rule[] {
    const nextMainRuleById = new Map(
      reorderedMainRules.map((rule, index) => [
        rule.r_id,
        { ...rule, execution_order: index + 1 },
      ])
    );
    let nextMainIndex = 0;

    return this.rules.map((currentRule) => {
      if (currentRule.evaluation_lane !== 'main' || currentRule.status === 'archived') {
        return currentRule;
      }
      const replacement = nextMainRuleById.get(reorderedMainRules[nextMainIndex]?.r_id);
      nextMainIndex += 1;
      return replacement ?? nextMainRuleById.get(currentRule.r_id) ?? currentRule;
    });
  }

  formatDate(dateString: string | null): string {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  }

  showReadOnlyNotice(): boolean {
    return !this.canCreateRules && !this.canModifyRules && !this.canReorderRules && !this.canPauseRules && !this.canPromoteRules;
  }
}
