import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { diffLines, Change } from 'diff';
import { RuleDetail, RuleRevisionDetail, RuleService, ShadowDeployResponse, ShadowRuleItem, UpdateRuleRequest } from '../services/rule.service';
import { BacktestingService, BacktestResultItem, BacktestTaskResult } from '../services/backtesting.service';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-rule-detail',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, SidebarComponent],
  templateUrl: './rule-detail.component.html'
})
export class RuleDetailComponent implements OnInit, OnDestroy {
  rule: RuleDetail | null = null;
  loading: boolean = true;
  error: string | null = null;
  testJson: string = '';
  testResult: any = null;
  testError: string | null = null;
  testing: boolean = false;

  // Revision view properties
  isRevisionView: boolean = false;
  revisionNumber: number | null = null;

  // Edit mode properties
  isEditMode: boolean = false;
  editedDescription: string = '';
  editedLogic: string = '';
  saving: boolean = false;
  saveError: string | null = null;
  saveSuccess: boolean = false;

  // Shadow deployment properties
  shadowEntry: ShadowRuleItem | null = null;
  showDeployToShadowDialog: boolean = false;
  deployingToShadow: boolean = false;
  shadowDeploySuccess: boolean = false;
  shadowDeployError: string | null = null;

  // Backtesting properties
  backtestResults: BacktestResultItem[] = [];
  backtestTaskResults: Map<string, BacktestTaskResult> = new Map();
  expandedBacktests: Set<string> = new Set();
  backtesting: boolean = false;
  backtestError: string | null = null;
  backtestDiffs: Map<string, Change[]> = new Map();
  private pollingIntervals: Map<string, ReturnType<typeof setInterval>> = new Map();

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private ruleService: RuleService,
    private backtestingService: BacktestingService
  ) { }

  ngOnInit(): void {
    const ruleId = this.route.snapshot.paramMap.get('id');
    const revision = this.route.snapshot.paramMap.get('revision');
    if (ruleId && revision) {
      this.isRevisionView = true;
      this.revisionNumber = parseInt(revision, 10);
      this.loadRevision(parseInt(ruleId, 10), this.revisionNumber);
    } else if (ruleId) {
      this.loadRule(parseInt(ruleId, 10));
      this.loadBacktestResults(parseInt(ruleId, 10));

      // If navigated from the shadow page, enter edit mode pre-seeded with shadow logic
      const nav = history.state;
      if (nav?.shadowEditMode) {
        this.isEditMode = true;
        this.editedLogic = nav.logic;
        this.editedDescription = nav.description;
      }
    }
  }

  ngOnDestroy(): void {
    this.pollingIntervals.forEach(interval => clearInterval(interval));
    this.pollingIntervals.clear();
  }

  loadRule(ruleId: number): void {
    this.loading = true;
    this.error = null;

    this.ruleService.getRule(ruleId).subscribe({
      next: (rule) => {
        this.rule = rule;
        this.loading = false;
        this.fillInExampleParams();
        this.loadShadowEntry(rule.r_id);
      },
      error: (error) => {
        this.error = 'Failed to load rule. Please try again.';
        this.loading = false;
        console.error('Error loading rule:', error);
      }
    });
  }

  loadRevision(ruleId: number, revisionNumber: number): void {
    this.loading = true;
    this.error = null;

    this.ruleService.getRuleRevision(ruleId, revisionNumber).subscribe({
      next: (revision: RuleRevisionDetail) => {
        this.rule = revision;
        this.loading = false;
        this.fillInExampleParams();
      },
      error: (error) => {
        this.error = 'Failed to load rule revision. Please try again.';
        this.loading = false;
        console.error('Error loading rule revision:', error);
      }
    });
  }

  fillInExampleParams(): void {
    if (!this.rule) return;

    this.ruleService.verifyRule(this.rule.logic).subscribe({
      next: (response) => {
        if (response.params && response.params.length > 0) {
          const exampleJson: any = {};
          response.params.forEach((param: string) => {
            exampleJson[param] = '';
          });
          this.testJson = JSON.stringify(exampleJson, null, 2);
        }
      },
      error: (error) => {
        console.error('Error verifying rule:', error);
      }
    });
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
      textarea.value = value.substring(0, start) + '\t' + value.substring(end);

      // Move cursor after the tab
      textarea.selectionStart = textarea.selectionEnd = start + 1;
    }
  }

  goBack(): void {
    this.router.navigate(['/rules']);
  }

  toggleEditMode(): void {
    if (!this.isEditMode && this.rule) {
      // Entering edit mode - copy current values
      this.editedDescription = this.rule.description;
      this.editedLogic = this.rule.logic;
      this.saveError = null;
      this.saveSuccess = false;
    }
    this.isEditMode = !this.isEditMode;
  }

  cancelEdit(): void {
    this.isEditMode = false;
    this.saveError = null;
    this.saveSuccess = false;
    if (this.rule) {
      this.editedDescription = this.rule.description;
      this.editedLogic = this.rule.logic;
    }
  }

  saveRule(): void {
    if (!this.rule) return;

    this.saving = true;
    this.saveError = null;
    this.saveSuccess = false;

    const updateData: UpdateRuleRequest = {
      description: this.editedDescription,
      logic: this.editedLogic
    };

    this.ruleService.updateRule(this.rule.r_id, updateData).subscribe({
      next: (response) => {
        this.saving = false;
        if (response.success && response.rule) {
          this.rule = response.rule;
          this.saveSuccess = true;
          this.isEditMode = false;
          // Update test JSON with new parameters
          this.fillInExampleParams();
        } else {
          this.saveError = response.error || 'Failed to save rule';
        }
      },
      error: (error) => {
        this.saving = false;
        this.saveError = error.error?.error || 'Failed to save rule. Please try again.';
        console.error('Error saving rule:', error);
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

  // Backtesting methods

  triggerBacktest(): void {
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
      },
      error: (error) => {
        console.error('Error loading backtest results:', error);
      }
    });
  }

  loadTaskResult(taskId: string): void {
    this.backtestingService.getTaskResult(taskId).subscribe({
      next: (result) => {
        this.backtestTaskResults.set(taskId, result);
        if (result.status === 'PENDING') {
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
      this.stopPolling(taskId);
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

  computeBacktestDiff(stored: string | null, proposed: string | null): Change[] {
    const key = `${stored}|||${proposed}`;
    if (!this.backtestDiffs.has(key)) {
      this.backtestDiffs.set(key, diffLines(stored || '', proposed || ''));
    }
    return this.backtestDiffs.get(key)!;
  }

  getBacktestStatus(taskId: string): string {
    const result = this.backtestTaskResults.get(taskId);
    if (!result) return 'PENDING';
    return result.status;
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

  private startPolling(taskId: string): void {
    if (this.pollingIntervals.has(taskId)) return;
    const interval = setInterval(() => {
      this.backtestingService.getTaskResult(taskId).subscribe({
        next: (result) => {
          this.backtestTaskResults.set(taskId, result);
          if (result.status !== 'PENDING') {
            this.stopPolling(taskId);
          }
        },
        error: () => {
          this.stopPolling(taskId);
        }
      });
    }, 3000);
    this.pollingIntervals.set(taskId, interval);
  }

  private stopPolling(taskId: string): void {
    const interval = this.pollingIntervals.get(taskId);
    if (interval) {
      clearInterval(interval);
      this.pollingIntervals.delete(taskId);
    }
  }
}
