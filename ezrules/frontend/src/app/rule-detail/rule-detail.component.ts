import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { RuleDetail, RuleService } from '../services/rule.service';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-rule-detail',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, SidebarComponent],
  templateUrl: './rule-detail.component.html'
})
export class RuleDetailComponent implements OnInit {
  rule: RuleDetail | null = null;
  loading: boolean = true;
  error: string | null = null;
  testJson: string = '';
  testResult: any = null;
  testError: string | null = null;
  testing: boolean = false;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private ruleService: RuleService
  ) { }

  ngOnInit(): void {
    const ruleId = this.route.snapshot.paramMap.get('id');
    if (ruleId) {
      this.loadRule(parseInt(ruleId, 10));
    }
  }

  loadRule(ruleId: number): void {
    this.loading = true;
    this.error = null;

    this.ruleService.getRule(ruleId).subscribe({
      next: (rule) => {
        this.rule = rule;
        this.loading = false;
        this.fillInExampleParams();
      },
      error: (error) => {
        this.error = 'Failed to load rule. Please try again.';
        this.loading = false;
        console.error('Error loading rule:', error);
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
}
