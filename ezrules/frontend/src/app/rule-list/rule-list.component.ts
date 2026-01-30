import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Rule, RuleService } from '../services/rule.service';

@Component({
  selector: 'app-rule-list',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './rule-list.component.html'
})
export class RuleListComponent implements OnInit {
  rules: Rule[] = [];
  evaluatorEndpoint: string = '';
  loading: boolean = true;
  error: string | null = null;

  constructor(private ruleService: RuleService) { }

  ngOnInit(): void {
    this.loadRules();
  }

  loadRules(): void {
    this.loading = true;
    this.error = null;

    this.ruleService.getRules().subscribe({
      next: (response) => {
        this.rules = response.rules;
        this.evaluatorEndpoint = response.evaluator_endpoint;
        this.loading = false;
      },
      error: (error) => {
        this.error = 'Failed to load rules. Please try again.';
        this.loading = false;
        console.error('Error loading rules:', error);
      }
    });
  }

  formatDate(dateString: string | null): string {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  }
}
