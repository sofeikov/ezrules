import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { of, Subscription } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { CreateRuleRequest, RuleService } from '../services/rule.service';
import { RuleLogicEditorComponent, RuleEditorDiagnostic } from '../components/rule-logic-editor.component';
import { RuleTestDataService } from '../services/rule-test-data.service';
import {
  RuleEditorAssistService,
  RuleEditorFieldSuggestion,
  RuleEditorListSuggestion,
} from '../services/rule-editor-assist.service';
import { RuntimeSettingsService } from '../services/runtime-settings.service';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-rule-create',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, SidebarComponent, RuleLogicEditorComponent],
  templateUrl: './rule-create.component.html'
})
export class RuleCreateComponent implements OnInit, OnDestroy {
  readonly laneOptions = [
    { value: 'main', label: 'Main rules' },
    { value: 'allowlist', label: 'Allowlist rules' },
  ] as const;
  readonly mainLaneDescription = 'Main rules run during standard evaluation and participate in the normal outcome resolution flow.';
  rid: string = '';
  description: string = '';
  logic: string = '';
  evaluationLane: 'main' | 'allowlist' = 'main';
  neutralOutcomeLabel: string = 'RELEASE';
  testJson: string = '';
  testResult: any = null;
  testError: string | null = null;
  verifyErrors: RuleEditorDiagnostic[] = [];
  verifyWarnings: string[] = [];
  verifiedParams: string[] = [];
  referencedLists: string[] = [];
  fieldSuggestions: RuleEditorFieldSuggestion[] = [];
  listSuggestions: RuleEditorListSuggestion[] = [];
  testing: boolean = false;
  saving: boolean = false;
  saveError: string | null = null;
  private assistSubscription: Subscription | null = null;
  private verifyDebounceHandle: ReturnType<typeof setTimeout> | null = null;
  private verifyRequestSequence: number = 0;
  private verifySubscription: Subscription | null = null;

  constructor(
    private router: Router,
    private ruleService: RuleService,
    private ruleTestDataService: RuleTestDataService,
    private ruleEditorAssistService: RuleEditorAssistService,
    private runtimeSettingsService: RuntimeSettingsService,
  ) { }

  ngOnInit(): void {
    this.assistSubscription = this.ruleEditorAssistService.getAssistData().subscribe((assistData) => {
      this.fieldSuggestions = assistData.fields;
      this.listSuggestions = assistData.lists;
    });
    this.runtimeSettingsService.getRuntimeSettings().subscribe({
      next: (settings) => {
        this.neutralOutcomeLabel = settings.neutralOutcome || settings.defaultNeutralOutcome || 'RELEASE';
      },
      error: () => {
        this.neutralOutcomeLabel = 'RELEASE';
      }
    });
  }

  ngOnDestroy(): void {
    this.assistSubscription?.unsubscribe();
    this.cancelPendingVerify();
  }

  handleTextareaTab(event: KeyboardEvent): void {
    if (event.key === 'Tab') {
      event.preventDefault();
      const textarea = event.target as HTMLTextAreaElement;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const value = textarea.value;

      const nextValue = value.substring(0, start) + '\t' + value.substring(end);
      textarea.value = nextValue;
      textarea.selectionStart = textarea.selectionEnd = start + 1;

      if (textarea.placeholder === 'Enter rule logic') {
        this.logic = nextValue;
        this.handleLogicChange();
      }
    }
  }

  handleLogicChange(): void {
    this.queueFillInExampleParams(this.logic);
  }

  handleLogicEditorChange(value: string): void {
    this.logic = value;
    this.handleLogicChange();
  }

  handleLogicProxyInput(event: Event): void {
    this.logic = (event.target as HTMLTextAreaElement).value;
    this.handleLogicChange();
  }

  fillInExampleParams(): void {
    const requestId = this.cancelPendingVerify();
    this.runFillInExampleParams(this.logic, requestId);
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
        this.testJson = '';
        this.verifyErrors = [];
        this.verifyWarnings = [];
        this.verifiedParams = [];
        this.referencedLists = [];
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

        if (response !== null) {
          this.testJson = response;
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
        console.error('Error verifying rule:', error);
      }
    });
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
    this.testing = true;
    this.testError = null;
    this.testResult = null;

    this.ruleService.testRule(this.logic, this.testJson).subscribe({
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

  submitRule(): void {
    this.saving = true;
    this.saveError = null;

    const createData: CreateRuleRequest = {
      rid: this.rid,
      description: this.description,
      logic: this.logic,
      evaluation_lane: this.evaluationLane,
    };

    this.ruleService.createRule(createData).subscribe({
      next: (response) => {
        this.saving = false;
        if (response.success && response.rule) {
          this.router.navigate(['/rules', response.rule.r_id]);
        } else {
          this.saveError = response.error || 'Failed to create rule';
        }
      },
      error: (error) => {
        this.saving = false;
        this.saveError = error.error?.error || 'Failed to create rule. Please try again.';
        console.error('Error creating rule:', error);
      }
    });
  }

  goBack(): void {
    this.router.navigate(['/rules']);
  }

  selectedLaneDescription(): string {
    if (this.evaluationLane === 'allowlist') {
      return `Allowlist rules short-circuit evaluation when they match. They must return ${this.neutralOutcomeLabel}.`;
    }
    return this.mainLaneDescription;
  }
}
