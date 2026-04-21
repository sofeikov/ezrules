import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { AuthService } from '../services/auth.service';
import { ACTION_PERMISSION_REQUIREMENTS, hasPermissionRequirement } from '../auth/permissions';
import { SidebarComponent } from '../components/sidebar.component';
import {
  AIAuthoringSettings,
  InvalidAllowlistRule,
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
  readonly mainRuleExecutionModeOptions = [
    { value: 'all_matches', label: 'Collect all matches' },
    { value: 'first_match', label: 'Stop on first match' },
  ] as const;
  readonly aiAuthoringModelOptions = [
    { value: 'gpt-4.1-mini', label: 'Default' },
    { value: 'gpt-4.1', label: 'Higher quality' },
    { value: 'gpt-4o-mini', label: 'Lower cost' },
  ] as const;
  autoPromoteActiveRuleUpdates: boolean = false;
  defaultAutoPromoteActiveRuleUpdates: boolean = false;
  mainRuleExecutionMode: string = 'all_matches';
  defaultMainRuleExecutionMode: string = 'all_matches';
  loading: boolean = true;
  saving: boolean = false;
  hierarchySaving: boolean = false;
  pairSaving: boolean = false;
  pairBusyIds: Set<number> = new Set<number>();
  error: string | null = null;
  success: string | null = null;

  ruleQualityLookbackDays: number = 30;
  defaultRuleQualityLookbackDays: number = 30;
  neutralOutcome: string = '';
  defaultNeutralOutcome: string = '';
  invalidAllowlistRules: InvalidAllowlistRule[] = [];
  aiAuthoringSettings: AIAuthoringSettings | null = null;
  aiAuthoringProvider: string = 'openai';
  aiAuthoringEnabled: boolean = false;
  aiAuthoringModel: string = '';
  aiAuthoringApiKey: string = '';
  aiAuthoringSaving: boolean = false;
  availableOutcomes: string[] = [];
  availableLabels: string[] = [];
  hierarchyOutcomes: OutcomeHierarchyItem[] = [];
  pairs: RuleQualityPair[] = [];
  newPairOutcome: string = '';
  newPairLabel: string = '';
  hierarchyDirty: boolean = false;
  canManagePermissions: boolean = false;
  canManageNeutralOutcome: boolean = false;

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
        this.canManageNeutralOutcome = hasPermissionRequirement(
          user.permissions,
          ACTION_PERMISSION_REQUIREMENTS.manageNeutralOutcome,
        );
      },
      error: () => {
        this.canManagePermissions = false;
        this.canManageNeutralOutcome = false;
      }
    });
  }

  loadSettings(): void {
    this.loading = true;
    this.error = null;
    this.success = null;

    forkJoin({
      settings: this.runtimeSettingsService.getRuntimeSettings(),
      aiAuthoring: this.runtimeSettingsService.getAIAuthoringSettings(),
      hierarchy: this.runtimeSettingsService.getOutcomeHierarchy(),
      options: this.runtimeSettingsService.getRuleQualityPairOptions(),
      pairs: this.runtimeSettingsService.getRuleQualityPairs(),
    }).subscribe({
      next: ({ settings, aiAuthoring, hierarchy, options, pairs }) => {
        this.autoPromoteActiveRuleUpdates = settings.autoPromoteActiveRuleUpdates;
        this.defaultAutoPromoteActiveRuleUpdates = settings.defaultAutoPromoteActiveRuleUpdates;
        this.mainRuleExecutionMode = settings.mainRuleExecutionMode;
        this.defaultMainRuleExecutionMode = settings.defaultMainRuleExecutionMode;
        this.ruleQualityLookbackDays = settings.ruleQualityLookbackDays;
        this.defaultRuleQualityLookbackDays = settings.defaultRuleQualityLookbackDays;
        this.neutralOutcome = settings.neutralOutcome;
        this.defaultNeutralOutcome = settings.defaultNeutralOutcome;
        this.invalidAllowlistRules = settings.invalidAllowlistRules;
        this.aiAuthoringSettings = aiAuthoring;
        this.aiAuthoringProvider = aiAuthoring.provider;
        this.aiAuthoringEnabled = aiAuthoring.enabled;
        this.aiAuthoringModel = aiAuthoring.model || this.aiAuthoringModelOptions[0].value;
        this.aiAuthoringApiKey = '';
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

  saveAIAuthoringSettings(): void {
    if (!this.canManagePermissions) {
      return;
    }

    this.error = null;
    this.success = null;

    if (!this.aiAuthoringProvider) {
      this.error = 'Select an AI provider before saving.';
      return;
    }
    if (!this.aiAuthoringModel.trim()) {
      this.aiAuthoringModel = this.aiAuthoringModelOptions[0].value;
    }
    if (this.aiAuthoringEnabled && !this.aiAuthoringModel.trim()) {
      this.error = 'Enter an OpenAI model before enabling AI authoring.';
      return;
    }
    if (
      this.aiAuthoringEnabled
      && !this.aiAuthoringApiKey.trim()
      && !this.aiAuthoringSettings?.apiKeyConfigured
    ) {
      this.error = 'Add an OpenAI API key before enabling AI authoring.';
      return;
    }

    this.aiAuthoringSaving = true;
    const trimmedApiKey = this.aiAuthoringApiKey.trim();
    this.runtimeSettingsService.updateAIAuthoringSettings({
      provider: this.aiAuthoringProvider,
      enabled: this.aiAuthoringEnabled,
      model: this.aiAuthoringModel.trim(),
      apiKey: trimmedApiKey ? trimmedApiKey : undefined,
    }).subscribe({
      next: (settings) => {
        this.aiAuthoringSettings = settings;
        this.aiAuthoringProvider = settings.provider;
        this.aiAuthoringEnabled = settings.enabled;
        this.aiAuthoringModel = settings.model;
        this.aiAuthoringApiKey = '';
        this.success = 'AI authoring settings saved successfully.';
        this.aiAuthoringSaving = false;
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Failed to save AI authoring settings.';
        this.aiAuthoringSaving = false;
      }
    });
  }

  useAiAuthoringModelOption(model: string): void {
    this.aiAuthoringModel = model;
  }

  clearStoredAiAuthoringApiKey(): void {
    if (!this.canManagePermissions || !this.aiAuthoringSettings?.apiKeyConfigured || this.aiAuthoringSaving) {
      return;
    }

    const willDisableAiAuthoring = this.aiAuthoringEnabled && !this.aiAuthoringApiKey.trim();
    const confirmed = window.confirm(
      willDisableAiAuthoring
        ? 'Clear the stored OpenAI API key? AI authoring will also be disabled until you save a new key.'
        : 'Clear the stored OpenAI API key?'
    );
    if (!confirmed) {
      return;
    }

    this.error = null;
    this.success = null;
    this.aiAuthoringSaving = true;

    this.runtimeSettingsService.updateAIAuthoringSettings({
      clearApiKey: true,
      enabled: willDisableAiAuthoring ? false : undefined,
    }).subscribe({
      next: (settings) => {
        this.aiAuthoringSettings = settings;
        this.aiAuthoringProvider = settings.provider;
        this.aiAuthoringEnabled = settings.enabled;
        this.aiAuthoringModel = settings.model || this.aiAuthoringModelOptions[0].value;
        this.aiAuthoringApiKey = '';
        this.success = 'Stored API key cleared successfully.';
        this.aiAuthoringSaving = false;
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Failed to clear the stored API key.';
        this.aiAuthoringSaving = false;
      }
    });
  }

  save(): void {
    if (!this.canManagePermissions && !this.canManageNeutralOutcome) {
      return;
    }

    this.error = null;
    this.success = null;

    if (this.canManagePermissions && (!Number.isFinite(this.ruleQualityLookbackDays) || this.ruleQualityLookbackDays < 1)) {
      this.error = 'Lookback days must be at least 1.';
      return;
    }
    if (this.canManageNeutralOutcome && this.availableOutcomes.length > 0 && !this.neutralOutcome) {
      this.error = 'Select a neutral outcome before saving settings.';
      return;
    }

    this.saving = true;
    const updateRequest = {
      autoPromoteActiveRuleUpdates: this.canManagePermissions ? this.autoPromoteActiveRuleUpdates : undefined,
      mainRuleExecutionMode: this.canManagePermissions ? this.mainRuleExecutionMode : undefined,
      ruleQualityLookbackDays: this.canManagePermissions ? Math.floor(this.ruleQualityLookbackDays) : undefined,
      neutralOutcome: this.canManageNeutralOutcome ? this.neutralOutcome : undefined,
    };
    this.runtimeSettingsService.updateRuntimeSettings(updateRequest).subscribe({
      next: (settings) => {
        this.autoPromoteActiveRuleUpdates = settings.autoPromoteActiveRuleUpdates;
        this.defaultAutoPromoteActiveRuleUpdates = settings.defaultAutoPromoteActiveRuleUpdates;
        this.mainRuleExecutionMode = settings.mainRuleExecutionMode;
        this.defaultMainRuleExecutionMode = settings.defaultMainRuleExecutionMode;
        this.ruleQualityLookbackDays = settings.ruleQualityLookbackDays;
        this.defaultRuleQualityLookbackDays = settings.defaultRuleQualityLookbackDays;
        this.neutralOutcome = settings.neutralOutcome;
        this.defaultNeutralOutcome = settings.defaultNeutralOutcome;
        this.invalidAllowlistRules = settings.invalidAllowlistRules;
        this.success = 'Settings saved successfully.';
        this.saving = false;
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Failed to save settings.';
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
    return !this.canManagePermissions && !this.canManageNeutralOutcome;
  }

  showNeutralOutcomeSelector(): boolean {
    return this.availableOutcomes.length > 0;
  }

  neutralOutcomeLabel(): string {
    return this.neutralOutcome || this.defaultNeutralOutcome || 'RELEASE';
  }

  neutralOutcomeMissingFromCatalog(): boolean {
    return !!this.neutralOutcome && !this.availableOutcomes.includes(this.neutralOutcome);
  }

  canSaveNeutralOutcome(): boolean {
    return this.canManageNeutralOutcome;
  }
}
