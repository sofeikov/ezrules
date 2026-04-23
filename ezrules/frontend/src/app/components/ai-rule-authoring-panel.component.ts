import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnDestroy, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { type Change, diffChars } from 'diff';

import { RuleLogicEditorComponent } from './rule-logic-editor.component';
import {
  RuleEditorFieldSuggestion,
  RuleEditorListSuggestion,
  RuleEditorOutcomeSuggestion,
} from '../services/rule-editor-assist.service';
import {
  RuleAIDraftResponse,
  RuleEvaluationLane,
  RuleService,
} from '../services/rule.service';

@Component({
  selector: 'app-ai-rule-authoring-panel',
  standalone: true,
  imports: [CommonModule, FormsModule, RuleLogicEditorComponent],
  template: `
    <section class="rounded-xl border border-slate-200 bg-slate-50/70 p-4" data-testid="ai-rule-authoring-panel">
      <button
        *ngIf="collapsible"
        type="button"
        class="flex w-full items-start justify-between gap-3 text-left"
        (click)="toggleExpanded()"
        data-testid="ai-rule-authoring-toggle"
      >
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">AI Assistant</p>
          <h3 class="mt-1 text-lg font-semibold text-slate-900">
            Draft {{ mode === 'edit' ? 'an updated rule' : 'a new rule' }} from natural language
          </h3>
          <p class="mt-1 text-sm text-slate-600">
            {{ expanded ? 'Collapse the assistant to get back editor space.' : 'Expand to generate or review an AI draft.' }}
          </p>
        </div>
        <div class="flex items-center gap-3">
          <span
            *ngIf="result && !draftAppliedToEditor"
            class="inline-flex items-center rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-800"
          >
            Preview only
          </span>
          <span
            *ngIf="draftAppliedToEditor"
            class="inline-flex items-center rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-800"
          >
            Draft copied
          </span>
          <span
            class="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium"
            [ngClass]="{
              'bg-sky-100 text-sky-800': evaluationLane === 'main',
              'bg-amber-100 text-amber-800': evaluationLane === 'allowlist'
            }"
            data-testid="ai-rule-authoring-lane-badge"
          >
            {{ evaluationLane === 'allowlist' ? 'Allowlist lane' : 'Main lane' }}
          </span>
          <span class="rounded-full bg-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-700">
            {{ expanded ? 'Hide' : 'Show' }}
          </span>
        </div>
      </button>

      <div *ngIf="!collapsible" class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">AI Assistant</p>
          <h3 class="mt-1 text-lg font-semibold text-slate-900">
            Draft {{ mode === 'edit' ? 'an updated rule' : 'a new rule' }} from natural language
          </h3>
          <p class="mt-1 text-sm text-slate-600">
            Generates a draft only. Nothing is saved or activated until you apply the draft and use the existing save flow.
          </p>
        </div>
        <span
          class="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium"
          [ngClass]="{
            'bg-sky-100 text-sky-800': evaluationLane === 'main',
            'bg-amber-100 text-amber-800': evaluationLane === 'allowlist'
          }"
          data-testid="ai-rule-authoring-lane-badge"
        >
          {{ evaluationLane === 'allowlist' ? 'Allowlist lane' : 'Main lane' }}
        </span>
      </div>

      <div *ngIf="!collapsible || expanded" class="mt-4 grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
        <div>
          <label class="mb-2 block text-sm font-medium text-slate-700" for="ai-rule-authoring-prompt">
            Prompt
          </label>
          <textarea
            id="ai-rule-authoring-prompt"
            [(ngModel)]="prompt"
            rows="4"
            class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            placeholder="Describe the rule you want, for example: Flag high-value transfers from new customers to high-risk jurisdictions."
            data-testid="ai-rule-authoring-prompt"
          ></textarea>

          <div class="mt-3 flex flex-wrap gap-3">
            <button
              type="button"
              (click)="generateDraft()"
              [disabled]="generating || !prompt.trim()"
              class="inline-flex items-center rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
              data-testid="ai-rule-authoring-generate"
            >
              <span *ngIf="!generating">{{ result ? 'Regenerate Draft' : 'Generate Draft' }}</span>
              <span *ngIf="generating">Generating…</span>
            </button>
          </div>

          <div *ngIf="error" class="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" data-testid="ai-rule-authoring-error">
            {{ error }}
          </div>

          <div *ngIf="appliedMessage" class="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800" data-testid="ai-rule-authoring-applied">
            {{ appliedMessage }}
          </div>

          <div
            *ngIf="generating || result || error"
            class="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-3"
            data-testid="ai-rule-authoring-progress"
          >
            <p class="text-sm font-semibold text-slate-900">Generation status</p>
            <div class="mt-3 flex flex-wrap gap-2 text-xs">
              <span class="rounded-full px-2.5 py-1 font-medium" [ngClass]="generationStepClass('preparing')">
                1. Context
              </span>
              <span class="rounded-full px-2.5 py-1 font-medium" [ngClass]="generationStepClass('generating')">
                2. Draft
              </span>
              <span class="rounded-full px-2.5 py-1 font-medium" [ngClass]="generationStepClass('validating')">
                3. Validate
              </span>
            </div>
            <p class="mt-3 text-sm text-slate-700">{{ generationStatusMessage() }}</p>
          </div>
        </div>

        <aside class="rounded-lg border border-slate-200 bg-white p-3">
          <p class="text-sm font-semibold text-slate-900">Authoring context</p>
          <p class="mt-2 text-xs text-slate-600">
            {{ evaluationLane === 'allowlist'
              ? 'Allowlist rules must return only !' + neutralOutcomeLabel + ' and contain at least one matching return.'
              : 'Main rules can return any configured outcome.' }}
          </p>
          <div class="mt-3 space-y-3 text-xs text-slate-600">
            <div>
              <p class="font-semibold uppercase tracking-wide text-slate-500">Observed fields</p>
              <p class="mt-1">{{ fieldSuggestions.length }} loaded</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <span
                  *ngFor="let field of previewFields()"
                  class="rounded-full bg-sky-50 px-2.5 py-1 font-medium text-sky-700"
                >
                  {{ '$' }}{{ field.name }}
                </span>
                <span *ngIf="fieldSuggestions.length > previewFields().length" class="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">
                  +{{ fieldSuggestions.length - previewFields().length }} more
                </span>
              </div>
            </div>
            <div>
              <p class="font-semibold uppercase tracking-wide text-slate-500">User lists</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <span
                  *ngFor="let list of previewLists()"
                  class="rounded-full bg-amber-50 px-2.5 py-1 font-medium text-amber-700"
                >
                  &#64;{{ list.name }}
                </span>
                <span *ngIf="listSuggestions.length > previewLists().length" class="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">
                  +{{ listSuggestions.length - previewLists().length }} more
                </span>
              </div>
            </div>
            <div>
              <p class="font-semibold uppercase tracking-wide text-slate-500">Outcomes</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <span
                  *ngFor="let outcome of previewOutcomes()"
                  class="rounded-full bg-rose-50 px-2.5 py-1 font-medium text-rose-700"
                >
                  !{{ outcome.name }}
                </span>
                <span *ngIf="outcomeSuggestions.length > previewOutcomes().length" class="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">
                  +{{ outcomeSuggestions.length - previewOutcomes().length }} more
                </span>
              </div>
            </div>
            <p *ngIf="mode === 'edit' && currentLogic.trim()" class="rounded-lg bg-slate-50 px-3 py-2 text-slate-600">
              Using the current draft in the editor as edit context.
            </p>
          </div>
        </aside>
      </div>

      <div *ngIf="result && (!collapsible || expanded)" class="mt-4 space-y-4" data-testid="ai-rule-authoring-result">
        <div
          class="rounded-lg border px-3 py-3"
          [ngClass]="draftAppliedToEditor ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'"
          data-testid="ai-rule-authoring-editor-sync"
        >
          <p class="text-sm font-semibold" [ngClass]="draftAppliedToEditor ? 'text-emerald-900' : 'text-amber-900'">
            {{ draftAppliedToEditor ? 'Main editor updated' : 'Preview only' }}
          </p>
          <p class="mt-1 text-sm" [ngClass]="draftAppliedToEditor ? 'text-emerald-800' : 'text-amber-800'">
            {{ draftAppliedToEditor
              ? 'The generated rule has been copied into the real editor below. Save/Create will now use that code.'
              : 'Save/Create still uses the main editor below, not this preview. Copy the draft into the main editor first if you want to save it.' }}
          </p>
          <div class="mt-3">
            <button
              type="button"
              (click)="applyDraft()"
              [disabled]="applying || !result.applyable"
              class="inline-flex items-center rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-400"
              data-testid="ai-rule-authoring-apply"
            >
              <span *ngIf="!applying">{{ draftAppliedToEditor ? 'Copy Draft Again' : 'Use Draft In Main Editor' }}</span>
              <span *ngIf="applying">Copying…</span>
            </button>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2 text-xs">
          <span
            class="inline-flex items-center rounded-full px-2.5 py-1 font-medium"
            [ngClass]="result.applyable ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'"
            data-testid="ai-rule-authoring-status"
          >
            {{ result.applyable ? 'Validated draft' : 'Review required' }}
          </span>
          <span class="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-700">
            Provider: {{ result.provider }}
          </span>
          <span
            *ngIf="result.repair_attempted"
            class="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-1 font-medium text-blue-800"
          >
            Auto-repair attempted
          </span>
        </div>

        <div>
          <p class="mb-2 text-sm font-semibold text-slate-900">Generated draft</p>
          <app-rule-logic-editor
            [value]="result.draft_logic"
            [readOnly]="true"
          ></app-rule-logic-editor>
        </div>

        <div *ngIf="hasDiffPreview()" class="rounded-lg border border-slate-200 bg-white">
          <button
            type="button"
            class="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
            (click)="toggleDiffExpanded()"
            data-testid="ai-rule-authoring-diff-toggle"
          >
            <div>
              <p class="text-sm font-semibold text-slate-900">Diff vs current editor</p>
              <p class="mt-1 text-sm text-slate-600">Green text is added. Red text is removed.</p>
            </div>
            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">
              {{ diffExpanded ? 'Hide' : 'Show' }}
            </span>
          </button>
          <div *ngIf="diffExpanded" class="border-t border-slate-200 px-4 py-4">
            <div class="overflow-hidden rounded-lg border border-slate-200 bg-slate-950">
              <pre class="overflow-x-auto whitespace-pre-wrap break-words px-4 py-4 text-sm leading-6 text-slate-100"><span
                *ngFor="let part of draftDiffParts()"
                [ngClass]="{
                  'bg-emerald-600/25 text-emerald-200': part.added,
                  'bg-rose-600/25 text-rose-200 line-through': part.removed,
                  'text-slate-100': !part.added && !part.removed
                }"
              >{{ part.value }}</span></pre>
            </div>
          </div>
        </div>

        <div *ngIf="result.validation.warnings.length > 0" class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900">
          <p class="font-medium">Validation warnings</p>
          <ul class="mt-2 list-disc space-y-1 pl-5">
            <li *ngFor="let warning of result.validation.warnings">{{ warning }}</li>
          </ul>
        </div>

        <div *ngIf="result.validation.errors.length > 0" class="rounded-lg border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-900">
          <p class="font-medium">Validation errors</p>
          <ul class="mt-2 list-disc space-y-1 pl-5">
            <li *ngFor="let validationError of result.validation.errors">
              {{ validationError.message }}
            </li>
          </ul>
        </div>

        <div *ngIf="hasLineExplanations()" class="rounded-lg border border-slate-200 bg-white">
          <button
            type="button"
            class="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
            (click)="toggleExplanationsExpanded()"
            data-testid="ai-rule-authoring-explanations-toggle"
          >
            <div>
              <p class="text-sm font-semibold text-slate-900">Line-by-line explanation</p>
              <p class="mt-1 text-sm text-slate-600">
                {{ result.line_explanations.length }} explained line{{ result.line_explanations.length === 1 ? '' : 's' }}.
              </p>
            </div>
            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">
              {{ explanationsExpanded ? 'Hide' : 'Show' }}
            </span>
          </button>
          <div *ngIf="explanationsExpanded" class="border-t border-slate-200 px-4 py-4">
            <div class="space-y-3">
              <div
                *ngFor="let line of result.line_explanations"
                class="rounded-lg border border-slate-200 bg-white px-3 py-3"
                data-testid="ai-rule-authoring-explanation"
              >
                <div class="flex items-start justify-between gap-3">
                  <code class="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700">Line {{ line.line_number }}</code>
                  <code class="flex-1 whitespace-pre-wrap break-words text-xs text-slate-700">{{ line.source }}</code>
                </div>
                <p class="mt-2 text-sm text-slate-700">{{ line.explanation }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  `,
})
export class AiRuleAuthoringPanelComponent {
  @Input() collapsible = false;
  @Input() mode: 'create' | 'edit' = 'create';
  @Input() evaluationLane: RuleEvaluationLane = 'main';
  @Input() currentLogic = '';
  @Input() currentDescription = '';
  @Input() ruleId: number | null = null;
  @Input() neutralOutcomeLabel = 'RELEASE';
  @Input() fieldSuggestions: RuleEditorFieldSuggestion[] = [];
  @Input() listSuggestions: RuleEditorListSuggestion[] = [];
  @Input() outcomeSuggestions: RuleEditorOutcomeSuggestion[] = [];
  @Output() draftApplied = new EventEmitter<string>();
  @Output() pendingDraftChange = new EventEmitter<boolean>();

  prompt = '';
  generating = false;
  applying = false;
  expanded = false;
  diffExpanded = true;
  draftAppliedToEditor = false;
  explanationsExpanded = false;
  generationPhase: 'idle' | 'preparing' | 'generating' | 'validating' | 'done' | 'error' = 'idle';
  error: string | null = null;
  appliedMessage: string | null = null;
  result: RuleAIDraftResponse | null = null;
  private generationTimeoutHandles: number[] = [];

  constructor(private ruleService: RuleService) {}

  ngOnDestroy(): void {
    this.clearGenerationProgress();
  }

  previewFields(): RuleEditorFieldSuggestion[] {
    return this.fieldSuggestions.slice(0, 6);
  }

  previewLists(): RuleEditorListSuggestion[] {
    return this.listSuggestions.slice(0, 4);
  }

  previewOutcomes(): RuleEditorOutcomeSuggestion[] {
    return this.outcomeSuggestions.slice(0, 6);
  }

  hasDiffPreview(): boolean {
    return !!this.result && !!this.currentLogic.trim();
  }

  hasLineExplanations(): boolean {
    return !!this.result?.line_explanations.length;
  }

  draftDiffParts(): Change[] {
    if (!this.result) {
      return [];
    }
    return diffChars(this.currentLogic || '', this.result.draft_logic);
  }

  toggleDiffExpanded(): void {
    this.diffExpanded = !this.diffExpanded;
  }

  toggleExplanationsExpanded(): void {
    this.explanationsExpanded = !this.explanationsExpanded;
  }

  toggleExpanded(): void {
    if (!this.collapsible) {
      return;
    }
    this.expanded = !this.expanded;
  }

  generationStepClass(step: 'preparing' | 'generating' | 'validating'): string {
    const order = ['preparing', 'generating', 'validating'];
    const currentIndex = order.indexOf(this.generationPhase);
    const stepIndex = order.indexOf(step);

    if (this.generationPhase === 'error') {
      return 'bg-red-100 text-red-800';
    }
    if (this.generationPhase === 'done' || (currentIndex !== -1 && stepIndex < currentIndex)) {
      return 'bg-emerald-100 text-emerald-800';
    }
    if (this.generationPhase === step) {
      return 'bg-blue-100 text-blue-800';
    }
    return 'bg-slate-100 text-slate-600';
  }

  generationStatusMessage(): string {
    if (this.generating) {
      if (this.generationPhase === 'preparing') {
        return 'Preparing rule context from fields, lists, outcomes, and lane constraints.';
      }
      if (this.generationPhase === 'generating') {
        return 'Requesting a draft from the model.';
      }
      if (this.generationPhase === 'validating') {
        return 'Validating and repairing the generated draft before review.';
      }
    }
    if (this.error) {
      return this.error;
    }
    if (this.result?.applyable && this.draftAppliedToEditor) {
      return 'Draft copied into the main editor. You can now use the normal save flow.';
    }
    if (this.result?.applyable) {
      return 'Preview is ready. The main editor below is still unchanged until you copy this draft into it.';
    }
    if (this.result) {
      return 'Preview is ready for review, but it still needs manual fixes before it can be copied into the main editor.';
    }
    return 'Ready to generate a draft.';
  }

  private startGenerationProgress(): void {
    this.clearGenerationProgress();
    this.generationPhase = 'preparing';
    this.generationTimeoutHandles.push(
      window.setTimeout(() => {
        if (this.generating) {
          this.generationPhase = 'generating';
        }
      }, 300),
      window.setTimeout(() => {
        if (this.generating) {
          this.generationPhase = 'validating';
        }
      }, 1600),
    );
  }

  private clearGenerationProgress(): void {
    for (const handle of this.generationTimeoutHandles) {
      window.clearTimeout(handle);
    }
    this.generationTimeoutHandles = [];
  }

  private scrollToMainEditor(): void {
    const target = document.querySelector('[data-testid="rule-main-logic-editor"]');
    if (target instanceof HTMLElement) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  private emitPendingDraftState(): void {
    this.pendingDraftChange.emit(!!this.result?.applyable && !this.draftAppliedToEditor);
  }

  generateDraft(): void {
    if (!this.prompt.trim()) {
      return;
    }

    this.expanded = true;
    this.generating = true;
    this.draftAppliedToEditor = false;
    this.startGenerationProgress();
    this.emitPendingDraftState();
    this.error = null;
    this.appliedMessage = null;
    this.result = null;

    this.ruleService.generateAIDraft({
      prompt: this.prompt.trim(),
      evaluation_lane: this.evaluationLane,
      mode: this.mode,
      current_logic: this.currentLogic || null,
      current_description: this.currentDescription || null,
      rule_id: this.ruleId,
    }).subscribe({
      next: (response) => {
        this.result = response;
        this.generating = false;
        this.clearGenerationProgress();
        this.generationPhase = 'done';
        this.diffExpanded = false;
        this.explanationsExpanded = false;
        this.emitPendingDraftState();
      },
      error: (error) => {
        this.error = error.error?.detail || 'Failed to generate an AI draft right now.';
        this.generating = false;
        this.clearGenerationProgress();
        this.generationPhase = 'error';
        this.emitPendingDraftState();
      },
    });
  }

  applyDraft(): void {
    if (!this.result?.applyable) {
      return;
    }

    this.expanded = true;
    this.applying = true;
    this.error = null;
    this.appliedMessage = null;

    this.ruleService.applyAIDraft(this.result.generation_id, this.ruleId).subscribe({
      next: () => {
        this.applying = false;
        this.draftAppliedToEditor = true;
        this.appliedMessage = 'Draft copied into the main editor. Review it there, then use the normal save flow.';
        this.draftApplied.emit(this.result!.draft_logic);
        this.emitPendingDraftState();
        window.setTimeout(() => this.scrollToMainEditor(), 0);
      },
      error: (error) => {
        this.error = error.error?.detail || 'Failed to record the draft application.';
        this.applying = false;
      },
    });
  }
}
