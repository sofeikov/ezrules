import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { AuthService } from '../services/auth.service';
import { ACTION_PERMISSION_REQUIREMENTS, hasPermissionRequirement } from '../auth/permissions';
import { SidebarComponent } from '../components/sidebar.component';
import {
  OutcomeHierarchyItem,
  RuleQualityPair,
  RuntimeSettingsService,
} from '../services/runtime-settings.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent],
  templateUrl: './settings.component.html'
})
export class SettingsComponent implements OnInit {
  loading: boolean = true;
  saving: boolean = false;
  hierarchySaving: boolean = false;
  pairSaving: boolean = false;
  pairBusyIds: Set<number> = new Set<number>();
  error: string | null = null;
  success: string | null = null;

  ruleQualityLookbackDays: number = 30;
  defaultRuleQualityLookbackDays: number = 30;
  availableOutcomes: string[] = [];
  availableLabels: string[] = [];
  hierarchyOutcomes: OutcomeHierarchyItem[] = [];
  pairs: RuleQualityPair[] = [];
  newPairOutcome: string = '';
  newPairLabel: string = '';
  hierarchyDirty: boolean = false;
  canManagePermissions: boolean = false;

  constructor(
    private runtimeSettingsService: RuntimeSettingsService,
    private authService: AuthService,
  ) {}

  ngOnInit(): void {
    this.loadPermissions();
    this.loadSettings();
  }

  loadPermissions(): void {
    this.authService.getCurrentUser().subscribe({
      next: (user) => {
        this.canManagePermissions = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.managePermissions);
      },
      error: () => {
        this.canManagePermissions = false;
      }
    });
  }

  loadSettings(): void {
    this.loading = true;
    this.error = null;
    this.success = null;

    forkJoin({
      settings: this.runtimeSettingsService.getRuntimeSettings(),
      hierarchy: this.runtimeSettingsService.getOutcomeHierarchy(),
      options: this.runtimeSettingsService.getRuleQualityPairOptions(),
      pairs: this.runtimeSettingsService.getRuleQualityPairs(),
    }).subscribe({
      next: ({ settings, hierarchy, options, pairs }) => {
        this.ruleQualityLookbackDays = settings.ruleQualityLookbackDays;
        this.defaultRuleQualityLookbackDays = settings.defaultRuleQualityLookbackDays;
        this.hierarchyOutcomes = hierarchy;
        this.availableOutcomes = options.outcomes;
        this.availableLabels = options.labels;
        this.pairs = pairs;
        this.newPairOutcome = this.availableOutcomes[0] || '';
        this.newPairLabel = this.availableLabels[0] || '';
        this.hierarchyDirty = false;
        this.loading = false;
      },
      error: (err) => {
        if (err?.error?.detail) {
          this.error = String(err.error.detail);
        } else {
          this.error = 'Failed to load settings data.';
        }
        this.loading = false;
      }
    });
  }

  save(): void {
    if (!this.canManagePermissions) {
      return;
    }

    this.error = null;
    this.success = null;

    if (!Number.isFinite(this.ruleQualityLookbackDays) || this.ruleQualityLookbackDays < 1) {
      this.error = 'Lookback days must be at least 1.';
      return;
    }

    this.saving = true;
    this.runtimeSettingsService.updateRuntimeSettings(Math.floor(this.ruleQualityLookbackDays)).subscribe({
      next: (settings) => {
        this.ruleQualityLookbackDays = settings.ruleQualityLookbackDays;
        this.defaultRuleQualityLookbackDays = settings.defaultRuleQualityLookbackDays;
        this.success = 'Settings saved successfully.';
        this.saving = false;
      },
      error: () => {
        this.error = 'Failed to save settings.';
        this.saving = false;
      }
    });
  }

  addPair(): void {
    if (!this.canManagePermissions) {
      return;
    }

    this.error = null;
    this.success = null;
    if (!this.newPairOutcome || !this.newPairLabel) {
      this.error = 'Select both outcome and label before adding a pair.';
      return;
    }

    this.pairSaving = true;
    this.runtimeSettingsService.createRuleQualityPair(this.newPairOutcome, this.newPairLabel).subscribe({
      next: (pair) => {
        this.pairs = [...this.pairs, pair].sort((a, b) =>
          a.outcome.localeCompare(b.outcome) || a.label.localeCompare(b.label)
        );
        this.success = 'Pair added successfully.';
        this.pairSaving = false;
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Failed to add pair.';
        this.pairSaving = false;
      }
    });
  }

  onPairActiveChange(pair: RuleQualityPair, event: Event): void {
    if (!this.canManagePermissions) {
      return;
    }

    const active = (event.target as HTMLInputElement).checked;
    this.error = null;
    this.success = null;
    this.pairBusyIds.add(pair.rqpId);
    this.runtimeSettingsService.updateRuleQualityPair(pair.rqpId, active).subscribe({
      next: (updated) => {
        this.pairs = this.pairs.map(item => item.rqpId === updated.rqpId ? updated : item);
        this.success = 'Pair updated successfully.';
        this.pairBusyIds.delete(pair.rqpId);
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Failed to update pair.';
        this.pairBusyIds.delete(pair.rqpId);
      }
    });
  }

  deletePair(pair: RuleQualityPair): void {
    if (!this.canManagePermissions) {
      return;
    }

    this.error = null;
    this.success = null;
    this.pairBusyIds.add(pair.rqpId);
    this.runtimeSettingsService.deleteRuleQualityPair(pair.rqpId).subscribe({
      next: () => {
        this.pairs = this.pairs.filter(item => item.rqpId !== pair.rqpId);
        this.success = 'Pair deleted successfully.';
        this.pairBusyIds.delete(pair.rqpId);
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Failed to delete pair.';
        this.pairBusyIds.delete(pair.rqpId);
      }
    });
  }

  isPairBusy(pairId: number): boolean {
    return this.pairBusyIds.has(pairId);
  }

  moveOutcome(index: number, direction: -1 | 1): void {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= this.hierarchyOutcomes.length) {
      return;
    }

    const reordered = [...this.hierarchyOutcomes];
    const [item] = reordered.splice(index, 1);
    reordered.splice(nextIndex, 0, item);
    this.hierarchyOutcomes = reordered.map((outcome, position) => ({
      ...outcome,
      severityRank: position + 1,
    }));
    this.hierarchyDirty = true;
  }

  saveOutcomeHierarchy(): void {
    if (!this.canManagePermissions) {
      return;
    }

    this.error = null;
    this.success = null;

    if (this.hierarchyOutcomes.length === 0) {
      this.success = 'No outcomes available to reorder.';
      return;
    }

    this.hierarchySaving = true;
    this.runtimeSettingsService.updateOutcomeHierarchy(this.hierarchyOutcomes.map(outcome => outcome.aoId)).subscribe({
      next: (outcomes) => {
        this.hierarchyOutcomes = outcomes;
        this.availableOutcomes = outcomes.map(outcome => outcome.outcomeName);
        this.hierarchyDirty = false;
        this.success = 'Outcome hierarchy saved successfully.';
        this.hierarchySaving = false;
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Failed to save outcome hierarchy.';
        this.hierarchySaving = false;
      }
    });
  }

  showReadOnlyNotice(): boolean {
    return !this.canManagePermissions;
  }
}
