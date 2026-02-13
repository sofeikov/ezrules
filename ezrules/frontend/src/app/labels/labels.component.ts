import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LabelService } from '../services/label.service';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-labels',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent],
  templateUrl: './labels.component.html'
})
export class LabelsComponent implements OnInit {
  labels: string[] = [];
  newLabel: string = '';
  loading: boolean = true;
  error: string | null = null;
  deleteError: string | null = null;
  createError: string | null = null;

  constructor(private labelService: LabelService) { }

  ngOnInit(): void {
    this.loadLabels();
  }

  loadLabels(): void {
    this.loading = true;
    this.error = null;

    this.labelService.getLabels().subscribe({
      next: (labels) => {
        this.labels = labels;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load labels. Please try again.';
        this.loading = false;
      }
    });
  }

  createLabel(): void {
    if (!this.newLabel.trim()) return;

    this.createError = null;
    this.labelService.addLabel(this.newLabel.trim()).subscribe({
      next: (response) => {
        if (response.failed_to_add && response.failed_to_add.length > 0) {
          this.createError = `Label "${response.failed_to_add[0]}" already exists.`;
        } else {
          this.newLabel = '';
          this.loadLabels();
        }
      },
      error: () => {
        this.createError = 'Failed to create label. Please try again.';
      }
    });
  }

  deleteLabel(labelName: string): void {
    if (!confirm(`Are you sure you want to delete "${labelName}"?`)) return;

    this.deleteError = null;
    this.labelService.deleteLabel(labelName).subscribe({
      next: () => {
        this.loadLabels();
      },
      error: () => {
        this.deleteError = `Failed to delete label "${labelName}". Please try again.`;
      }
    });
  }
}
