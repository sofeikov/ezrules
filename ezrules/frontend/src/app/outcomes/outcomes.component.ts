import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { OutcomeService } from '../services/outcome.service';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-outcomes',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent],
  templateUrl: './outcomes.component.html'
})
export class OutcomesComponent implements OnInit {
  outcomes: string[] = [];
  newOutcome: string = '';
  loading: boolean = true;
  error: string | null = null;
  deleteError: string | null = null;
  createError: string | null = null;

  constructor(private outcomeService: OutcomeService) { }

  ngOnInit(): void {
    this.loadOutcomes();
  }

  loadOutcomes(): void {
    this.loading = true;
    this.error = null;

    this.outcomeService.getOutcomes().subscribe({
      next: (response) => {
        this.outcomes = response.outcomes;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load outcomes. Please try again.';
        this.loading = false;
      }
    });
  }

  createOutcome(): void {
    if (!this.newOutcome.trim()) return;

    this.createError = null;
    this.outcomeService.createOutcome(this.newOutcome.trim()).subscribe({
      next: (response) => {
        if (response.success) {
          this.newOutcome = '';
          this.loadOutcomes();
        } else {
          this.createError = response.error ?? 'Failed to create outcome.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.createError = err.error?.error ?? 'Failed to create outcome. Please try again.';
      }
    });
  }

  deleteOutcome(outcome: string): void {
    if (!confirm(`Are you sure you want to delete "${outcome}"?`)) return;

    this.deleteError = null;
    this.outcomeService.deleteOutcome(outcome).subscribe({
      next: () => {
        this.loadOutcomes();
      },
      error: () => {
        this.deleteError = `Failed to delete outcome "${outcome}". Please try again.`;
      }
    });
  }
}
