import { AfterViewInit, ChangeDetectorRef, Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Chart, registerables } from 'chart.js';
import { diffLines, Change } from 'diff';
import { of, Subscription } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import {
  RolloutDeployResponse,
  RolloutRuleItem,
  RuleDetail,
  RuleEvaluationLane,
  RuleRevisionDetail,
  RuleService,
  ShadowDeployResponse,
  ShadowRuleItem,
  UpdateRuleRequest
} from '../services/rule.service';
import { ChartDataset, DashboardService } from '../services/dashboard.service';
import {
  BacktestingService,
  BacktestQualityMetric,
  BacktestQualitySummary,
  BacktestResultItem,
  BacktestTaskResult
} from '../services/backtesting.service';
import { AuthService } from '../services/auth.service';
import { ACTION_PERMISSION_REQUIREMENTS, hasPermissionRequirement } from '../auth/permissions';
import { AiRuleAuthoringPanelComponent } from '../components/ai-rule-authoring-panel.component';
import { RuleLogicEditorComponent, RuleEditorDiagnostic } from '../components/rule-logic-editor.component';
import { RuleTestDataService } from '../services/rule-test-data.service';
import {
  RuleEditorAssistService,
  RuleEditorFieldSuggestion,
  RuleEditorListSuggestion,
  RuleEditorOutcomeSuggestion,
} from '../services/rule-editor-assist.service';
import { RuntimeSettingsService } from '../services/runtime-settings.service';
import { SidebarComponent } from '../components/sidebar.component';

Chart.register(...registerables);

@Component({
  selector: 'app-rule-detail',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, SidebarComponent, RuleLogicEditorComponent, AiRuleAuthoringPanelComponent],
  templateUrl: './rule-detail.component.html'
})
export class RuleDetailComponent implements OnInit, AfterViewInit, OnDestroy {
  readonly mainLaneDescription = 'Main rules run during standard evaluation and participate in the normal outcome resolution flow.';
  readonly performanceAggregations = [
    { value: '1h', label: 'Last 1 Hour' },
    { value: '6h', label: 'Last 6 Hours' },
    { value: '12h', label: 'Last 12 Hours' },
    { value: '24h', label: 'Last 24 Hours' },
    { value: '30d', label: 'Last 30 Days' }
  ];
  rule: RuleDetail | null = null;
  loading: boolean = true;
  error: string | null = null;
  neutralOutcomeLabel: string = 'RELEASE';
  testJson: string = '';
  private autoFilledTestJson: string = '';
  testResult: any = null;
  testError: string | null = null;
  verifyErrors: RuleEditorDiagnostic[] = [];
  verifyWarnings: string[] = [];
  verifiedParams: string[] = [];
  referencedLists: string[] = [];
  referencedOutcomes: string[] = [];
  fieldSuggestions: RuleEditorFieldSuggestion[] = [];
  listSuggestions: RuleEditorListSuggestion[] = [];
  outcomeSuggestions: RuleEditorOutcomeSuggestion[] = [];
  testing: boolean = false;
  performanceLoading: boolean = false;
  performanceError: string | null = null;
  selectedPerformanceAggregation: string = '6h';
  performanceOutcomeDatasets: ChartDataset[] = [];
  performanceTimeLabels: string[] = [];

  // Revision view properties
  isRevisionView: boolean = false;
  revisionNumber: number | null = null;

  // Edit mode properties
  isEditMode: boolean = false;
  editedDescription: string = '';
  editedLogic: string = '';
  editedEvaluationLane: RuleEvaluationLane = 'main';
  pendingAIDraft: boolean = false;
  saving: boolean = false;
  saveError: string | null = null;
  saveSuccess: boolean = false;
  saveSuccessMessage: string = 'Rule saved successfully!';

  // Shadow deployment properties
  shadowEntry: ShadowRuleItem | null = null;
  showDeployToShadowDialog: boolean = false;
  deployingToShadow: boolean = false;
  shadowDeploySuccess: boolean = false;
  shadowDeployError: string | null = null;

  rolloutEntry: RolloutRuleItem | null = null;
  showRolloutDialog: boolean = false;
  deployingToRollout: boolean = false;
  rolloutDeploySuccess: boolean = false;
  rolloutDeployError: string | null = null;
  rolloutTrafficPercent: number = 10;
  canModifyRules: boolean = false;
  canPauseRules: boolean = false;
  canPromoteRules: boolean = false;
  lifecycleActionLoading: 'pause' | 'resume' | null = null;

  // Backtesting properties
  backtestResults: BacktestResultItem[] = [];
  backtestTaskResults: Map<string, BacktestTaskResult> = new Map();
  private backtestActionStates: Map<string, 'cancel' | 'retry'> = new Map();
  expandedBacktests: Set<string> = new Set();
  backtesting: boolean = false;
  backtestError: string | null = null;
  backtestDiffs: Map<string, Change[]> = new Map();
  private pollingIntervals: Map<string, ReturnType<typeof setInterval>> = new Map();
  private assistSubscription: Subscription | null = null;
  private verifyDebounceHandle: ReturnType<typeof setTimeout> | null = null;
  private verifyRequestSequence: number = 0;
  private verifySubscription: Subscription | null = null;
  private performanceChart: Chart | null = null;
  private performanceCanvasReady: boolean = false;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private ruleService: RuleService,
    private dashboardService: DashboardService,
    private backtestingService: BacktestingService,
    private ruleTestDataService: RuleTestDataService,
    private ruleEditorAssistService: RuleEditorAssistService,
    private authService: AuthService,
    private runtimeSettingsService: RuntimeSettingsService,
    private cdr: ChangeDetectorRef,
  ) { }

  ngOnInit(): void {
    this.assistSubscription = this.ruleEditorAssistService.getAssistData().subscribe((assistData) => {
      this.fieldSuggestions = assistData.fields;
      this.listSuggestions = assistData.lists;
      this.outcomeSuggestions = assistData.outcomes;
    });
    this.runtimeSettingsService.getRuntimeSettings().subscribe({
      next: (settings) => {
        this.neutralOutcomeLabel = settings.neutralOutcome || settings.defaultNeutralOutcome || 'RELEASE';
      },
      error: () => {
        this.neutralOutcomeLabel = 'RELEASE';
      }
    });
    this.loadPermissions();
    const ruleId = this.route.snapshot.paramMap.get('id');
    const revision = this.route.snapshot.paramMap.get('revision');
    if (ruleId && revision) {
      this.isRevisionView = true;
      this.revisionNumber = parseInt(revision, 10);
      this.loadRevision(parseInt(ruleId, 10), this.revisionNumber);
    } else if (ruleId) {
      this.loadRule(parseInt(ruleId, 10));

      // If navigated from the shadow page, enter edit mode pre-seeded with shadow logic
      const nav = history.state;
      if (nav?.shadowEditMode) {
        this.isEditMode = true;
        this.editedLogic = nav.logic;
        this.editedDescription = nav.description;
        this.editedEvaluationLane = 'main';
      } else if (nav?.rolloutEditMode) {
        this.isEditMode = true;
        this.editedLogic = nav.logic;
        this.editedDescription = nav.description;
        this.editedEvaluationLane = 'main';
        this.rolloutTrafficPercent = nav.trafficPercent ?? 10;
      }
    }
  }

  ngAfterViewInit(): void {
    this.performanceCanvasReady = true;
    if (!this.performanceLoading && this.performanceOutcomeDatasets.length > 0) {
      this.cdr.detectChanges();
      setTimeout(() => this.renderPerformanceChart(), 0);
    }
  }

  ngOnDestroy(): void {
    this.assistSubscription?.unsubscribe();
    this.cancelPendingVerify();
    this.pollingIntervals.forEach(interval => clearInterval(interval));
    this.pollingIntervals.clear();
    this.destroyPerformanceChart();
  }

  loadPermissions(): void {
    this.authService.getCurrentUser().subscribe({
      next: (user) => {
        this.canModifyRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.modifyRule);
        this.canPauseRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.pauseRules);
        this.canPromoteRules = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.promoteRules);
        if (!this.canModifyRules) {
          this.isEditMode = false;
        }
      },
      error: () => {
        this.canModifyRules = false;
        this.canPauseRules = false;
        this.canPromoteRules = false;
        this.isEditMode = false;
      }
    });
  }

  loadRule(ruleId: number): void {
    this.loading = true;
    this.error = null;
    this.resetRulePerformance();

    this.ruleService.getRule(ruleId).subscribe({
      next: (rule) => {
        this.rule = rule;
        this.backtestResults = [];
        this.loading = false;
        this.fillInExampleParams();
        this.loadShadowEntry(rule.r_id);
        this.loadRolloutEntry(rule.r_id);
        this.loadBacktestResults(rule.r_id);
        this.loadRulePerformance(rule.r_id);
      },
      error: (error) => {
        this.rule = null;
        this.backtestResults = [];
        this.error = 'Failed to load rule. Please try again.';
        this.loading = false;
        console.error('Error loading rule:', error);
      }
    });
  }

  loadRevision(ruleId: number, revisionNumber: number): void {
    this.loading = true;
    this.error = null;
    this.resetRulePerformance();

    this.ruleService.getRuleRevision(ruleId, revisionNumber).subscribe({
      next: (revision: RuleRevisionDetail) => {
        this.rule = revision;
        this.backtestResults = [];
        this.loading = false;
        this.fillInExampleParams();
      },
      error: (error) => {
        this.rule = null;
        this.backtestResults = [];
        this.error = 'Failed to load rule revision. Please try again.';
        this.loading = false;
        console.error('Error loading rule revision:', error);
      }
    });
  }

  onPerformanceAggregationChange(): void {
    if (!this.rule || this.isRevisionView) {
      return;
    }
    this.loadRulePerformance(this.rule.r_id);
  }

  getPerformanceHitCount(): number {
    return this.performanceOutcomeDatasets.reduce(
      (total, dataset) => total + dataset.data.reduce((sum, count) => sum + count, 0),
      0,
    );
  }

  private loadRulePerformance(ruleId: number): void {
    if (this.isRevisionView) {
      return;
    }

    this.performanceLoading = true;
    this.performanceError = null;
    this.performanceOutcomeDatasets = [];
    this.performanceTimeLabels = [];
    this.destroyPerformanceChart();

    this.dashboardService.getRuleOutcomesDistribution(ruleId, this.selectedPerformanceAggregation).subscribe({
      next: (response) => {
        this.performanceTimeLabels = response.labels;
        this.performanceOutcomeDatasets = response.datasets;
        this.performanceLoading = false;

        if (this.performanceCanvasReady && this.performanceOutcomeDatasets.length > 0) {
          this.cdr.detectChanges();
          setTimeout(() => this.renderPerformanceChart(), 0);
        }
      },
      error: (error) => {
        this.performanceLoading = false;
        this.performanceError = 'Failed to load rule performance data.';
        this.destroyPerformanceChart();
        console.error('Error loading rule performance:', error);
      }
    });
  }

  private renderPerformanceChart(): void {
    this.destroyPerformanceChart();
    if (!this.performanceOutcomeDatasets.length) {
      return;
    }

    const canvas = document.getElementById('rulePerformanceChart') as HTMLCanvasElement | null;
    const context = canvas?.getContext('2d');
    if (!context) {
      return;
    }

    this.performanceChart = new Chart(context, {
      type: 'line',
      data: {
        labels: this.performanceTimeLabels,
        datasets: this.performanceOutcomeDatasets.map((dataset) => ({
          label: dataset.label,
          data: dataset.data,
          borderColor: dataset.borderColor,
          backgroundColor: dataset.backgroundColor,
          tension: 0.3,
          fill: false,
        }))
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: {
            display: true,
            position: 'bottom',
          },
          title: { display: false }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { precision: 0 }
          },
          x: {
            ticks: { maxRotation: 45, minRotation: 45 }
          }
        }
      }
    });
  }

  private destroyPerformanceChart(): void {
    this.performanceChart?.destroy();
    this.performanceChart = null;
  }

  private resetRulePerformance(): void {
    this.performanceLoading = false;
    this.performanceError = null;
    this.performanceOutcomeDatasets = [];
    this.performanceTimeLabels = [];
    this.destroyPerformanceChart();
  }

  fillInExampleParams(ruleSource?: string): void {
    const requestId = this.cancelPendingVerify();
    this.runFillInExampleParams(ruleSource ?? this.rule?.logic ?? '', requestId);
  }

  private queueFillInExampleParams(ruleSource: string): void {
    const requestId = this.cancelPendingVerify();
    this.verifyDebounceHandle = setTimeout(() => {
      this.verifyDebounceHandle = null;
      this.runFillInExampleParams(ruleSource, requestId);
    }, 250);
  }

  private runFillInExampleParams(ruleSource: string, requestId: number): void {
    if (!ruleSource.trim()) {
      if (requestId === this.verifyRequestSequence) {
        this.verifyErrors = [];
        this.verifyWarnings = [];
        this.verifiedParams = [];
        this.referencedLists = [];
        this.referencedOutcomes = [];
      }
      return;
    }

    this.verifySubscription = this.ruleService.verifyRule(ruleSource).pipe(
      switchMap((response) => {
        if (requestId !== this.verifyRequestSequence) {
          return of<string | null>(null);
        }

        this.verifyErrors = (response.errors ?? []).map((error) => ({
          message: error.message,
          line: error.line,
          column: error.column,
          endLine: error.end_line,
          endColumn: error.end_column,
        }));
        this.verifyWarnings = response.warnings ?? [];
        this.verifiedParams = response.params ?? [];
        this.referencedLists = response.referenced_lists ?? [];
        this.referencedOutcomes = response.referenced_outcomes ?? [];
        if (!response.valid || this.verifyErrors.length > 0) {
          return of<string | null>(null);
        }
        if (!response.params.length && /\$[A-Za-z_]/.test(ruleSource)) {
          return of<string | null>(null);
        }

        return this.ruleTestDataService.buildExampleJson(response.params ?? []);
      })
    ).subscribe({
      next: (response) => {
        if (requestId !== this.verifyRequestSequence) {
          return;
        }

        const canApplyAutoFill = this.testJson === '' || this.testJson === this.autoFilledTestJson;
        if (response !== null && canApplyAutoFill) {
          this.testJson = response;
          this.autoFilledTestJson = response;
        }
      },
      error: (error) => {
        if (requestId !== this.verifyRequestSequence) {
          return;
        }

        this.verifyErrors = [{ message: 'Failed to validate rule right now.', line: null, column: null, endLine: null, endColumn: null }];
        this.verifyWarnings = [];
        this.verifiedParams = [];
        this.referencedLists = [];
        this.referencedOutcomes = [];
        console.error('Error verifying rule:', error);
      }
    });
  }

  handleEditedLogicChange(): void {
    if (!this.isEditMode) {
      return;
    }
    this.queueFillInExampleParams(this.editedLogic);
  }

  handleEditedLogicEditorChange(value: string): void {
    this.editedLogic = value;
    this.handleEditedLogicChange();
  }

  handleEditedLogicProxyInput(event: Event): void {
    this.editedLogic = (event.target as HTMLTextAreaElement).value;
    this.handleEditedLogicChange();
  }

  handleAIDraftApplied(draftLogic: string): void {
    this.editedLogic = draftLogic;
    this.handleEditedLogicChange();
  }

  handlePendingAIDraftChange(pending: boolean): void {
    this.pendingAIDraft = pending;
  }

  private cancelPendingVerify(): number {
    if (this.verifyDebounceHandle) {
      clearTimeout(this.verifyDebounceHandle);
      this.verifyDebounceHandle = null;
    }
    this.verifySubscription?.unsubscribe();
    this.verifySubscription = null;
    this.verifyRequestSequence += 1;
    return this.verifyRequestSequence;
  }

  testRule(): void {
    if (!this.rule) return;

    this.testing = true;
    this.testError = null;
    this.testResult = null;

    this.ruleService.testRule(this.rule.logic, this.testJson).subscribe({
      next: (response) => {
        this.testResult = response;
        this.testing = false;
      },
      error: (error) => {
        this.testError = 'Failed to test rule. Please check your JSON.';
        this.testing = false;
        console.error('Error testing rule:', error);
      }
    });
  }

  formatDate(dateString: string | null): string {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  }

  handleTextareaTab(event: KeyboardEvent): void {
    if (event.key === 'Tab') {
      event.preventDefault();
      const textarea = event.target as HTMLTextAreaElement;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const value = textarea.value;

      // Insert tab character
      const nextValue = value.substring(0, start) + '\t' + value.substring(end);
      textarea.value = nextValue;

      // Move cursor after the tab
      textarea.selectionStart = textarea.selectionEnd = start + 1;

      if (!textarea.readOnly && textarea.placeholder === 'Enter rule logic') {
        this.editedLogic = nextValue;
        this.handleEditedLogicChange();
      }
    }
  }

  goBack(): void {
    this.router.navigate(['/rules']);
  }

  toggleEditMode(): void {
    if (!this.canModifyRules) {
      return;
    }

    if (!this.isEditMode && this.rule) {
      // Entering edit mode - copy current values
      this.editedDescription = this.rule.description;
      this.editedLogic = this.rule.logic;
      this.editedEvaluationLane = this.rule.evaluation_lane;
      this.rolloutTrafficPercent = this.rolloutEntry?.traffic_percent ?? 10;
      this.saveError = null;
      this.saveSuccess = false;
      this.pendingAIDraft = false;
      this.saveSuccessMessage = 'Rule saved successfully!';
      this.rolloutDeployError = null;
      this.rolloutDeploySuccess = false;
      this.fillInExampleParams(this.editedLogic);
    }
    this.isEditMode = !this.isEditMode;
  }

  cancelEdit(): void {
    this.isEditMode = false;
    this.saveError = null;
    this.saveSuccess = false;
    this.pendingAIDraft = false;
    this.saveSuccessMessage = 'Rule saved successfully!';
    if (this.rule) {
      this.editedDescription = this.rule.description;
      this.editedLogic = this.rule.logic;
      this.editedEvaluationLane = this.rule.evaluation_lane;
      this.rolloutTrafficPercent = this.rolloutEntry?.traffic_percent ?? 10;
      this.fillInExampleParams();
    }
  }

  saveRule(): void {
    if (!this.canModifyRules) return;
    if (!this.rule) return;

    this.saving = true;
    this.saveError = null;
    this.saveSuccess = false;
    this.saveSuccessMessage = 'Rule saved successfully!';

    const updateData: UpdateRuleRequest = {
      description: this.editedDescription,
      logic: this.editedLogic,
      evaluation_lane: this.editedEvaluationLane,
    };

    this.ruleService.updateRule(this.rule.r_id, updateData).subscribe({
      next: (response) => {
        this.saving = false;
        if (response.success && response.rule) {
          this.rule = response.rule;
          this.saveSuccess = true;
          this.saveSuccessMessage = response.message || 'Rule saved successfully!';
          this.isEditMode = false;
          // Update test JSON with new parameters
          this.fillInExampleParams();
        } else {
          this.saveError = response.error || 'Failed to save rule';
        }
      },
      error: (error) => {
        this.saving = false;
        this.saveError = error.error?.detail || error.error?.error || 'Failed to save rule. Please try again.';
        console.error('Error saving rule:', error);
      }
    });
  }

  pauseRule(): void {
    if (!this.rule || !this.canPauseRules || this.rule.status !== 'active' || this.lifecycleActionLoading) {
      return;
    }
    const confirmed = window.confirm(`Pause rule ${this.rule.rid}?`);
    if (!confirmed) {
      return;
    }

    this.lifecycleActionLoading = 'pause';
    this.saveError = null;
    this.saveSuccess = false;
    this.ruleService.pauseRule(this.rule.r_id).subscribe({
      next: (response) => {
        this.lifecycleActionLoading = null;
        if (response.success && response.rule) {
          this.rule = response.rule;
          this.saveSuccess = true;
          this.saveSuccessMessage = response.message || 'Rule paused.';
          this.isEditMode = false;
          this.loadShadowEntry(this.rule.r_id);
          this.loadRolloutEntry(this.rule.r_id);
          return;
        }
        this.saveError = response.error || 'Failed to pause rule.';
      },
      error: (error) => {
        this.lifecycleActionLoading = null;
        this.saveError = error.error?.detail || error.error?.error || 'Failed to pause rule. Please try again.';
      }
    });
  }

  resumeRule(): void {
    if (!this.rule || !this.canPromoteRules || this.rule.status !== 'paused' || this.lifecycleActionLoading) {
      return;
    }

    this.lifecycleActionLoading = 'resume';
    this.saveError = null;
    this.saveSuccess = false;
    this.ruleService.resumeRule(this.rule.r_id).subscribe({
      next: (response) => {
        this.lifecycleActionLoading = null;
        if (response.success && response.rule) {
          this.rule = response.rule;
          this.saveSuccess = true;
          this.saveSuccessMessage = response.message || 'Rule resumed.';
          this.loadShadowEntry(this.rule.r_id);
          this.loadRolloutEntry(this.rule.r_id);
          return;
        }
        this.saveError = response.error || 'Failed to resume rule.';
      },
      error: (error) => {
        this.lifecycleActionLoading = null;
        this.saveError = error.error?.detail || error.error?.error || 'Failed to resume rule. Please try again.';
      }
    });
  }

  // Shadow deployment methods

  loadShadowEntry(ruleId: number): void {
    this.ruleService.getShadowConfig().subscribe({
      next: (config) => {
        this.shadowEntry = config.rules.find(r => r.r_id === ruleId) || null;
      },
      error: () => {
        this.shadowEntry = null;
      }
    });
  }

  openDeployToShadowDialog(): void {
    if (!this.canModifyRules) {
      return;
    }
    if (this.isAllowlistRule()) {
      return;
    }

    this.showDeployToShadowDialog = true;
  }

  closeDeployToShadowDialog(): void {
    this.showDeployToShadowDialog = false;
  }

  computeDeployDiff(): Change[] {
    return diffLines(this.shadowEntry?.logic || '', this.editedLogic);
  }

  confirmDeployToShadow(): void {
    if (!this.rule) return;

    this.deployingToShadow = true;
    this.shadowDeploySuccess = false;
    this.shadowDeployError = null;

    this.ruleService.deployToShadow(this.rule.r_id, this.editedLogic, this.editedDescription).subscribe({
      next: (response: ShadowDeployResponse) => {
        this.deployingToShadow = false;
        this.closeDeployToShadowDialog();
        if (response.success) {
          this.shadowDeploySuccess = true;
          this.loadRule(this.rule!.r_id);
        } else {
          this.shadowDeployError = response.error || 'Failed to deploy to shadow';
        }
      },
      error: (error) => {
        this.deployingToShadow = false;
        this.closeDeployToShadowDialog();
        this.shadowDeployError = error.error?.detail || 'Failed to deploy to shadow. Please try again.';
      }
    });
  }

  loadRolloutEntry(ruleId: number): void {
    this.ruleService.getRolloutConfig().subscribe({
      next: (config) => {
        this.rolloutEntry = config.rules.find(r => r.r_id === ruleId) || null;
      },
      error: () => {
        this.rolloutEntry = null;
      }
    });
  }

  openRolloutDialog(): void {
    if (this.isAllowlistRule()) {
      return;
    }
    this.showRolloutDialog = true;
  }

  closeRolloutDialog(): void {
    this.showRolloutDialog = false;
  }

  computeRolloutDiff(): Change[] {
    return diffLines(this.rule?.logic || '', this.editedLogic);
  }

  confirmDeployToRollout(): void {
    if (!this.rule) return;

    this.deployingToRollout = true;
    this.rolloutDeploySuccess = false;
    this.rolloutDeployError = null;

    this.ruleService
      .deployToRollout(this.rule.r_id, this.editedLogic, this.editedDescription, this.rolloutTrafficPercent)
      .subscribe({
        next: (response: RolloutDeployResponse) => {
          this.deployingToRollout = false;
          this.closeRolloutDialog();
          if (response.success) {
            this.rolloutDeploySuccess = true;
            this.loadRule(this.rule!.r_id);
          } else {
            this.rolloutDeployError = response.error || 'Failed to start rollout';
          }
        },
        error: (error) => {
          this.deployingToRollout = false;
          this.closeRolloutDialog();
          this.rolloutDeployError = error.error?.detail || 'Failed to start rollout. Please try again.';
        }
      });
  }

  // Backtesting methods

  triggerBacktest(): void {
    if (!this.canModifyRules) return;
    if (!this.rule || !this.editedLogic) return;

    this.backtesting = true;
    this.backtestError = null;

    this.backtestingService.triggerBacktest(this.rule.r_id, this.editedLogic).subscribe({
      next: (response) => {
        this.backtesting = false;
        if (response.success) {
          this.loadBacktestResults(this.rule!.r_id);
        } else {
          this.backtestError = response.error || 'Failed to start backtest';
        }
      },
      error: (error) => {
        this.backtesting = false;
        this.backtestError = error.error?.detail || 'Failed to start backtest. Please try again.';
        console.error('Error triggering backtest:', error);
      }
    });
  }

  loadBacktestResults(ruleId: number): void {
    this.backtestingService.getBacktestResults(ruleId).subscribe({
      next: (response) => {
        this.backtestResults = response.results;
        const currentTaskIds = new Set(response.results.map((result) => result.task_id));

        for (const taskId of Array.from(this.backtestTaskResults.keys())) {
          if (!currentTaskIds.has(taskId)) {
            this.removeBacktestTaskResult(taskId);
            this.stopPolling(taskId);
          }
        }

        for (const result of response.results) {
          this.loadTaskResult(result.task_id);
        }
      },
      error: (error) => {
        console.error('Error loading backtest results:', error);
      }
    });
  }

  loadTaskResult(taskId: string): void {
    this.backtestingService.getTaskResult(taskId).subscribe({
      next: (result) => {
        this.setBacktestTaskResult(taskId, result);
        if (this.isBacktestActive(taskId)) {
          this.startPolling(taskId);
        } else {
          this.stopPolling(taskId);
        }
      },
      error: (error) => {
        console.error('Error loading task result:', error);
        this.stopPolling(taskId);
      }
    });
  }

  toggleBacktestResult(taskId: string): void {
    if (this.expandedBacktests.has(taskId)) {
      this.expandedBacktests.delete(taskId);
    } else {
      this.expandedBacktests.add(taskId);
      if (!this.backtestTaskResults.has(taskId)) {
        this.loadTaskResult(taskId);
      }
    }
  }

  isBacktestExpanded(taskId: string): boolean {
    return this.expandedBacktests.has(taskId);
  }

  getTaskResult(taskId: string): BacktestTaskResult | undefined {
    return this.backtestTaskResults.get(taskId);
  }

  getBacktestQueueStatus(taskId: string, item?: BacktestResultItem): string {
    const result = this.backtestTaskResults.get(taskId);
    const queueStatus = result?.queue_status || item?.queue_status;
    if (queueStatus) {
      return queueStatus;
    }

    const legacyStatus = result?.status || item?.status;
    switch (legacyStatus) {
      case 'SUCCESS':
        return 'done';
      case 'FAILURE':
        return 'failed';
      case 'CANCELLED':
        return 'cancelled';
      default:
        return 'pending';
    }
  }

  computeBacktestDiff(stored: string | null, proposed: string | null): Change[] {
    const key = `${stored}|||${proposed}`;
    if (!this.backtestDiffs.has(key)) {
      this.backtestDiffs.set(key, diffLines(stored || '', proposed || ''));
    }
    return this.backtestDiffs.get(key)!;
  }

  getBacktestStatus(taskId: string, item?: BacktestResultItem): string {
    const result = this.backtestTaskResults.get(taskId);
    if (result?.status) {
      return result.status;
    }
    return item?.status || 'PENDING';
  }

  getBacktestStatusLabel(taskId: string, item?: BacktestResultItem): string {
    switch (this.getBacktestQueueStatus(taskId, item)) {
      case 'pending':
        return 'Queued';
      case 'running':
        return 'Running';
      case 'done':
        return 'Completed';
      case 'cancelled':
        return 'Cancelled';
      default:
        return 'Failed';
    }
  }

  canCancelBacktest(taskId: string, item?: BacktestResultItem): boolean {
    const queueStatus = this.getBacktestQueueStatus(taskId, item);
    return queueStatus === 'pending' || queueStatus === 'running';
  }

  canRetryBacktest(taskId: string, item?: BacktestResultItem): boolean {
    const queueStatus = this.getBacktestQueueStatus(taskId, item);
    return queueStatus === 'failed' || queueStatus === 'cancelled';
  }

  isBacktestActionPending(taskId: string, action: 'cancel' | 'retry'): boolean {
    return this.backtestActionStates.get(taskId) === action;
  }

  getOutcomeKeys(taskResult: BacktestTaskResult): string[] {
    const keys = new Set<string>();
    if (taskResult.stored_result) {
      Object.keys(taskResult.stored_result).forEach(k => keys.add(k));
    }
    if (taskResult.proposed_result) {
      Object.keys(taskResult.proposed_result).forEach(k => keys.add(k));
    }
    return Array.from(keys).sort();
  }

  getLabelKeys(taskResult: BacktestTaskResult): string[] {
    return Object.keys(taskResult.label_counts || {}).sort();
  }

  getLabeledShare(taskResult: BacktestTaskResult): number {
    const totalRecords = taskResult.total_records || 0;
    const labeledRecords = taskResult.labeled_records || 0;
    if (totalRecords === 0) {
      return 0;
    }
    return 100 * labeledRecords / totalRecords;
  }

  formatQualityMetric(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }
    return `${new Intl.NumberFormat(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value * 100)}%`;
  }

  getQualitySummary(taskResult: BacktestTaskResult, variant: 'stored' | 'proposed'): BacktestQualitySummary | null {
    return variant === 'stored'
      ? taskResult.stored_quality_summary || null
      : taskResult.proposed_quality_summary || null;
  }

  getQualityMetricPairs(taskResult: BacktestTaskResult): Array<{ outcome: string; label: string }> {
    const pairs = new Map<string, { outcome: string; label: string }>();

    for (const metric of taskResult.stored_quality_metrics || []) {
      pairs.set(`${metric.outcome}|||${metric.label}`, { outcome: metric.outcome, label: metric.label });
    }
    for (const metric of taskResult.proposed_quality_metrics || []) {
      pairs.set(`${metric.outcome}|||${metric.label}`, { outcome: metric.outcome, label: metric.label });
    }

    return Array.from(pairs.values()).sort(
      (left, right) => left.outcome.localeCompare(right.outcome) || left.label.localeCompare(right.label)
    );
  }

  getQualityMetric(
    taskResult: BacktestTaskResult,
    variant: 'stored' | 'proposed',
    outcome: string,
    label: string
  ): BacktestQualityMetric | undefined {
    const metrics = variant === 'stored'
      ? taskResult.stored_quality_metrics || []
      : taskResult.proposed_quality_metrics || [];

    return metrics.find(metric => metric.outcome === outcome && metric.label === label);
  }

  cancelBacktest(taskId: string, event?: Event): void {
    event?.stopPropagation();
    if (!this.rule || this.isBacktestActionPending(taskId, 'cancel')) {
      return;
    }

    this.backtestError = null;
    this.setBacktestActionState(taskId, 'cancel');
    this.backtestingService.cancelBacktest(taskId).subscribe({
      next: () => {
        this.setBacktestActionState(taskId, null);
        this.stopPolling(taskId);
        this.loadBacktestResults(this.rule!.r_id);
      },
      error: (error) => {
        this.setBacktestActionState(taskId, null);
        this.backtestError = error.error?.detail || 'Failed to cancel backtest. Please try again.';
        console.error('Error cancelling backtest:', error);
      }
    });
  }

  retryBacktest(taskId: string, event?: Event): void {
    event?.stopPropagation();
    if (!this.rule || this.isBacktestActionPending(taskId, 'retry')) {
      return;
    }

    this.backtestError = null;
    this.setBacktestActionState(taskId, 'retry');
    this.backtestingService.retryBacktest(taskId).subscribe({
      next: () => {
        this.setBacktestActionState(taskId, null);
        this.loadBacktestResults(this.rule!.r_id);
      },
      error: (error) => {
        this.setBacktestActionState(taskId, null);
        this.backtestError = error.error?.detail || 'Failed to retry backtest. Please try again.';
        console.error('Error retrying backtest:', error);
      }
    });
  }

  private startPolling(taskId: string): void {
    if (this.pollingIntervals.has(taskId)) return;
    const interval = setInterval(() => {
      this.backtestingService.getTaskResult(taskId).subscribe({
        next: (result) => {
          this.setBacktestTaskResult(taskId, result);
          if (!this.isBacktestActive(taskId)) {
            this.stopPolling(taskId);
          }
        },
        error: () => {
          this.stopPolling(taskId);
        }
      });
    }, 1000);
    this.pollingIntervals.set(taskId, interval);
  }

  private stopPolling(taskId: string): void {
    const interval = this.pollingIntervals.get(taskId);
    if (interval) {
      clearInterval(interval);
      this.pollingIntervals.delete(taskId);
    }
  }

  private setBacktestTaskResult(taskId: string, result: BacktestTaskResult): void {
    const nextResults = new Map(this.backtestTaskResults);
    nextResults.set(taskId, result);
    this.backtestTaskResults = nextResults;
  }

  private removeBacktestTaskResult(taskId: string): void {
    const nextResults = new Map(this.backtestTaskResults);
    nextResults.delete(taskId);
    this.backtestTaskResults = nextResults;
  }

  private isBacktestActive(taskId: string): boolean {
    const queueStatus = this.getBacktestQueueStatus(taskId);
    return queueStatus === 'pending' || queueStatus === 'running';
  }

  private setBacktestActionState(taskId: string, action: 'cancel' | 'retry' | null): void {
    const nextStates = new Map(this.backtestActionStates);
    if (action) {
      nextStates.set(taskId, action);
    } else {
      nextStates.delete(taskId);
    }
    this.backtestActionStates = nextStates;
  }

  showReadOnlyNotice(): boolean {
    return !this.isRevisionView && !this.canModifyRules && !this.canPauseRules && !this.canPromoteRules;
  }

  isLifecycleActionLoading(action: 'pause' | 'resume'): boolean {
    return this.lifecycleActionLoading === action;
  }

  isAllowlistRule(): boolean {
    return (this.isEditMode ? this.editedEvaluationLane : this.rule?.evaluation_lane) === 'allowlist';
  }

  selectedLaneDescription(): string {
    if (this.editedEvaluationLane === 'allowlist') {
      return `Allowlist rules short-circuit evaluation when they match. They must return !${this.neutralOutcomeLabel}.`;
    }
    return this.mainLaneDescription;
  }

}
