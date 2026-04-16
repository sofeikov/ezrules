import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  SimpleChanges,
  ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import type { Completion, CompletionContext } from '@codemirror/autocomplete';
import type { Diagnostic as CodeMirrorDiagnostic } from '@codemirror/lint';
import {
  RuleEditorFieldSuggestion,
  RuleEditorListSuggestion,
  RuleEditorOutcomeSuggestion,
} from '../services/rule-editor-assist.service';

export interface RuleEditorDiagnostic {
  message: string;
  line: number | null;
  column: number | null;
  endLine: number | null;
  endColumn: number | null;
}

const RULE_KEYWORD_COMPLETIONS: Completion[] = [
  { label: 'return', type: 'keyword', detail: 'Return the rule outcome' },
  { label: 'if', type: 'keyword', detail: 'Conditional branch' },
  { label: 'elif', type: 'keyword', detail: 'Secondary conditional branch' },
  { label: 'else', type: 'keyword', detail: 'Fallback branch' },
  { label: 'and', type: 'keyword', detail: 'Boolean conjunction' },
  { label: 'or', type: 'keyword', detail: 'Boolean disjunction' },
  { label: 'not', type: 'keyword', detail: 'Boolean negation' },
  { label: 'in', type: 'keyword', detail: 'Membership check' },
  { label: 'True', type: 'constant', detail: 'Boolean true literal' },
  { label: 'False', type: 'constant', detail: 'Boolean false literal' },
  { label: 'None', type: 'constant', detail: 'Null literal' },
];

@Component({
  selector: 'app-rule-logic-editor',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="overflow-hidden rounded-lg border border-slate-200 shadow-sm">
      <div class="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
        <span>{{ readOnly ? 'Read-only rule source' : 'Rule editor' }}</span>
        <span *ngIf="!readOnly">Type <code>$</code> for fields, <code>&#64;</code> for user lists, and <code>!</code> for outcomes</span>
      </div>
      <div #editorHost class="rule-editor-host"></div>
    </div>

    <div *ngIf="!readOnly" class="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
      <span class="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">
        Ctrl-Space reopens autocomplete
      </span>
      <span *ngIf="fieldSuggestions.length > 0" class="rounded-full bg-sky-50 px-2.5 py-1 font-medium text-sky-700">
        Observed fields loaded
      </span>
      <span *ngIf="listSuggestions.length > 0" class="rounded-full bg-amber-50 px-2.5 py-1 font-medium text-amber-700">
        User lists loaded
      </span>
      <span *ngIf="outcomeSuggestions.length > 0" class="rounded-full bg-rose-50 px-2.5 py-1 font-medium text-rose-700">
        Outcomes loaded
      </span>
    </div>
  `,
  styles: [`
    :host {
      display: block;
    }

    .rule-editor-host {
      min-height: 18rem;
      background: #ffffff;
    }

    :host ::ng-deep .cm-editor {
      height: 100%;
      min-height: 18rem;
      background: transparent;
      color: #0f172a;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
      font-size: 0.95rem;
    }

    :host ::ng-deep .cm-focused {
      outline: none;
    }

    :host ::ng-deep .cm-scroller {
      min-height: 18rem;
      line-height: 1.6;
    }

    :host ::ng-deep .cm-content,
    :host ::ng-deep .cm-gutter {
      padding-top: 0.75rem;
      padding-bottom: 0.75rem;
    }

    :host ::ng-deep .cm-gutters {
      border-right: 1px solid #e2e8f0;
      background: #f8fafc;
      color: #94a3b8;
    }

    :host ::ng-deep .cm-activeLine,
    :host ::ng-deep .cm-activeLineGutter {
      background: #f8fafc;
    }

    :host ::ng-deep .cm-cursor {
      border-left-color: #0f172a;
    }

    :host ::ng-deep .cm-selectionBackground,
    :host ::ng-deep .cm-focused .cm-selectionBackground,
    :host ::ng-deep .cm-content ::selection {
      background: rgba(59, 130, 246, 0.18);
    }

    :host ::ng-deep .cm-tooltip-autocomplete {
      border: 1px solid #cbd5e1;
      border-radius: 0.75rem;
      background: #ffffff;
      color: #0f172a;
      box-shadow: 0 18px 40px rgba(15, 23, 42, 0.14);
      overflow: hidden;
    }

    :host ::ng-deep .cm-tooltip-autocomplete > ul > li[aria-selected] {
      background: #eff6ff;
      color: #0f172a;
    }

    :host ::ng-deep .cm-placeholder {
      color: #94a3b8;
      font-style: italic;
    }

    :host ::ng-deep .cm-lint-marker-error {
      color: #dc2626;
    }

    :host ::ng-deep .cm-diagnosticText {
      color: #991b1b;
    }

    :host ::ng-deep .cm-rule-field-token {
      color: #0369a1;
      font-weight: 600;
    }

    :host ::ng-deep .cm-rule-list-token {
      color: #b45309;
      font-weight: 600;
    }

    :host ::ng-deep .cm-rule-outcome-token {
      color: #be123c;
      font-weight: 700;
    }

    :host ::ng-deep .cm-keyword {
      color: #7c3aed;
    }

    :host ::ng-deep .cm-string {
      color: #15803d;
    }

    :host ::ng-deep .cm-number {
      color: #b91c1c;
    }

    :host ::ng-deep .cm-operator,
    :host ::ng-deep .cm-punctuation {
      color: #475569;
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RuleLogicEditorComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() value = '';
  @Input() readOnly = false;
  @Input() placeholderText = 'Enter rule logic';
  @Input() diagnostics: RuleEditorDiagnostic[] = [];
  @Input() fieldSuggestions: RuleEditorFieldSuggestion[] = [];
  @Input() listSuggestions: RuleEditorListSuggestion[] = [];
  @Input() outcomeSuggestions: RuleEditorOutcomeSuggestion[] = [];
  @Output() valueChange = new EventEmitter<string>();

  @ViewChild('editorHost', { static: true }) private editorHost!: ElementRef<HTMLDivElement>;

  private editorView: any = null;
  private setDiagnosticsFn: ((state: any, diagnostics: readonly CodeMirrorDiagnostic[]) => any) | null = null;

  ngAfterViewInit(): void {
    void this.initializeEditor();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (!this.editorView) {
      return;
    }

    if (changes['value']) {
      const currentValue = this.editorView.state.doc.toString();
      if (this.value !== currentValue) {
        this.editorView.dispatch({
          changes: { from: 0, to: currentValue.length, insert: this.value },
        });
      }
    }

    if (changes['diagnostics']) {
      this.applyDiagnostics();
    }
  }

  ngOnDestroy(): void {
    this.editorView?.destroy();
    this.editorView = null;
  }

  private async initializeEditor(): Promise<void> {
    const [
      { autocompletion },
      { indentWithTab },
      { python },
      { lintGutter, setDiagnostics },
      { EditorState },
      viewModule,
      { basicSetup },
    ] = await Promise.all([
      import('@codemirror/autocomplete'),
      import('@codemirror/commands'),
      import('@codemirror/lang-python'),
      import('@codemirror/lint'),
      import('@codemirror/state'),
      import('@codemirror/view'),
      import('codemirror'),
    ]);

    const { Decoration, EditorView, keymap, MatchDecorator, placeholder, ViewPlugin } = viewModule;
    const notationTokenDecorator = new MatchDecorator({
      regexp: /[$@!][A-Za-z_][A-Za-z0-9_]*/g,
      decoration: (match: RegExpExecArray) => Decoration.mark({
        class: match[0].startsWith('$')
          ? 'cm-rule-field-token'
          : match[0].startsWith('@')
            ? 'cm-rule-list-token'
            : 'cm-rule-outcome-token',
      }),
    });
    const notationTokenPlugin = ViewPlugin.fromClass(class {
      decorations: ReturnType<typeof notationTokenDecorator.createDeco>;

      constructor(view: InstanceType<typeof EditorView>) {
        this.decorations = notationTokenDecorator.createDeco(view);
      }

      update(update: Parameters<typeof notationTokenDecorator.updateDeco>[0]): void {
        this.decorations = notationTokenDecorator.updateDeco(update, this.decorations);
      }
    }, {
      decorations: (value) => value.decorations,
    });

    const extensions = [
      basicSetup,
      python(),
      EditorState.readOnly.of(this.readOnly),
      EditorView.editable.of(!this.readOnly),
      EditorView.lineWrapping,
      notationTokenPlugin,
    ];

    if (!this.readOnly) {
      extensions.push(
        keymap.of([indentWithTab]),
        placeholder(this.placeholderText),
        lintGutter(),
        autocompletion({
          override: [this.completeRuleTokens],
          maxRenderedOptions: 12,
        }),
        EditorView.updateListener.of((update) => {
          if (!update.docChanged) {
            return;
          }
          const nextValue = update.state.doc.toString();
          if (nextValue !== this.value) {
            this.valueChange.emit(nextValue);
          }
        })
      );
    }

    this.setDiagnosticsFn = setDiagnostics;
    this.editorView = new EditorView({
      state: EditorState.create({
        doc: this.value,
        extensions,
      }),
      parent: this.editorHost.nativeElement,
    });

    this.applyDiagnostics();
  }

  private readonly completeRuleTokens = (context: CompletionContext) => {
    const triggeredToken = context.matchBefore(/[$@!][A-Za-z0-9_]*/);
    if (triggeredToken) {
      if (triggeredToken.from === triggeredToken.to && !context.explicit) {
        return null;
      }

      if (triggeredToken.text.startsWith('$')) {
        const fieldQuery = triggeredToken.text.slice(1).toLowerCase();
        const options = this.fieldSuggestions
          .filter((field) => field.name.toLowerCase().includes(fieldQuery))
          .map((field) => ({
            label: `$${field.name}`,
            type: 'variable',
            detail: `field • ${field.observedJsonType}`,
          }));

        return {
          from: triggeredToken.from,
          options,
          validFor: /^\$[A-Za-z0-9_]*$/,
        };
      }

      if (triggeredToken.text.startsWith('!')) {
        const outcomeQuery = triggeredToken.text.slice(1).toLowerCase();
        const options = this.outcomeSuggestions
          .filter((outcome) => outcome.name.toLowerCase().includes(outcomeQuery))
          .map((outcome) => ({
            label: `!${outcome.name}`,
            type: 'constant',
            detail: `allowed outcome • severity ${outcome.severityRank}`,
          }));

        return {
          from: triggeredToken.from,
          options,
          validFor: /^![A-Za-z0-9_]*$/,
        };
      }

      const listQuery = triggeredToken.text.slice(1).toLowerCase();
      const options = this.listSuggestions
        .filter((list) => list.name.toLowerCase().includes(listQuery))
        .map((list) => ({
          label: `@${list.name}`,
          type: 'constant',
          detail: 'user list',
        }));

      return {
        from: triggeredToken.from,
        options,
        validFor: /^@[A-Za-z0-9_]*$/,
      };
    }

    const keywordToken = context.matchBefore(/[A-Za-z_][A-Za-z0-9_]*/);
    if (!keywordToken && !context.explicit) {
      return null;
    }

    const query = keywordToken?.text.toLowerCase() ?? '';
    return {
      from: keywordToken?.from ?? context.pos,
      options: RULE_KEYWORD_COMPLETIONS.filter((option) => option.label.toLowerCase().startsWith(query)),
      validFor: /^[A-Za-z_][A-Za-z0-9_]*$/,
    };
  };

  private applyDiagnostics(): void {
    if (!this.editorView || !this.setDiagnosticsFn) {
      return;
    }

    const setDiagnosticsFn = this.setDiagnosticsFn;
    this.editorView.dispatch(
      setDiagnosticsFn(
        this.editorView.state,
        this.diagnostics.map((diagnostic) => this.toCodeMirrorDiagnostic(diagnostic))
      )
    );
  }

  private toCodeMirrorDiagnostic(diagnostic: RuleEditorDiagnostic): CodeMirrorDiagnostic {
    const from = this.positionFromLineColumn(diagnostic.line, diagnostic.column);
    const endPosition = this.positionFromLineColumn(diagnostic.endLine, diagnostic.endColumn);
    const to = Math.max(from + 1, endPosition);

    return {
      from,
      to,
      severity: 'error',
      message: diagnostic.message,
    };
  }

  private positionFromLineColumn(line: number | null, column: number | null): number {
    if (!this.editorView || line === null || column === null || line < 1 || column < 1) {
      return 0;
    }

    const documentLineCount = this.editorView.state.doc.lines;
    const safeLineNumber = Math.min(line, documentLineCount);
    const lineInfo = this.editorView.state.doc.line(safeLineNumber);
    const maxColumn = lineInfo.length + 1;
    return lineInfo.from + Math.min(column, maxColumn) - 1;
  }
}
