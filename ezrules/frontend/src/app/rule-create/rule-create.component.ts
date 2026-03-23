import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { of } from 'rxjs';
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
export class RuleCreateComponent {
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

  constructor(
    private router: Router,
    private ruleService: RuleService,
    private ruleTestDataService: RuleTestDataService
  ) { }

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

  fillInExampleParams(): void {
    if (!this.logic.trim()) {
      this.testJson = '';
      this.verifyWarnings = [];
      return;
    }

    this.ruleService.verifyRule(this.logic).pipe(
      switchMap((response) => {
        this.verifyWarnings = response.warnings ?? [];
        if (!response.params.length && /\$[A-Za-z_]/.test(this.logic)) {
          return of<string | null>(null);
        }

        return this.ruleTestDataService.buildExampleJson(response.params ?? []);
      })
    ).subscribe({
      next: (response) => {
        if (response !== null) {
          this.testJson = response;
        }
      },
      error: (error) => {
        this.verifyWarnings = [];
        console.error('Error verifying rule:', error);
      }
    });
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
