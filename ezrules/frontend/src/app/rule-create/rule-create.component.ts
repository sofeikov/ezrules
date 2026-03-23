import { Component, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { of, Subscription } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { CreateRuleRequest, RuleService } from '../services/rule.service';
import { RuleTestDataService } from '../services/rule-test-data.service';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-rule-create',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, SidebarComponent],
  templateUrl: './rule-create.component.html'
})
export class RuleCreateComponent implements OnDestroy {
  rid: string = '';
  description: string = '';
  logic: string = '';
  testJson: string = '';
  testResult: any = null;
  testError: string | null = null;
  verifyWarnings: string[] = [];
  testing: boolean = false;
  saving: boolean = false;
  saveError: string | null = null;
  private verifyDebounceHandle: ReturnType<typeof setTimeout> | null = null;
  private verifyRequestSequence: number = 0;
  private verifySubscription: Subscription | null = null;

  constructor(
    private router: Router,
    private ruleService: RuleService,
    private ruleTestDataService: RuleTestDataService
  ) { }

  ngOnDestroy(): void {
    this.cancelPendingVerify();
  }

  handleTextareaTab(event: KeyboardEvent): void {
    if (event.key === 'Tab') {
      event.preventDefault();
      const textarea = event.target as HTMLTextAreaElement;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const value = textarea.value;

      textarea.value = value.substring(0, start) + '\t' + value.substring(end);
      textarea.selectionStart = textarea.selectionEnd = start + 1;
    }
  }

  handleLogicChange(): void {
    this.queueFillInExampleParams(this.logic);
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
        this.verifyWarnings = [];
      }
      return;
    }

    this.verifySubscription = this.ruleService.verifyRule(ruleSource).pipe(
      switchMap((response) => {
        if (requestId !== this.verifyRequestSequence) {
          return of<string | null>(null);
        }

        this.verifyWarnings = response.warnings ?? [];
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

        this.verifyWarnings = [];
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
      logic: this.logic
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
}
