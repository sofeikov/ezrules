import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { FieldTypeService, FieldTypeConfig, FieldObservation } from '../services/field-type.service';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-field-types',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent],
  templateUrl: './field-types.component.html',
})
export class FieldTypesComponent implements OnInit {
  configs: FieldTypeConfig[] = [];
  observations: FieldObservation[] = [];
  loading = true;
  error: string | null = null;
  createError: string | null = null;
  deleteError: string | null = null;

  // Create / upsert form
  newFieldName = '';
  newConfiguredType = 'string';
  newDatetimeFormat = '';

  readonly fieldTypeOptions = [
    'integer',
    'float',
    'string',
    'boolean',
    'datetime',
    'compare_as_is',
  ];

  // Maps Python JSON type names to the nearest FieldType option
  private readonly jsonTypeToFieldType: Record<string, string> = {
    int: 'integer',
    float: 'float',
    str: 'string',
    bool: 'boolean',
  };

  constructor(private fieldTypeService: FieldTypeService) {}

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading = true;
    this.error = null;

    this.fieldTypeService.getConfigs().subscribe({
      next: configs => {
        this.configs = configs;
        this.fieldTypeService.getObservations().subscribe({
          next: observations => {
            this.observations = observations;
            this.loading = false;
          },
          error: () => {
            this.error = 'Failed to load observations. Please try again.';
            this.loading = false;
          },
        });
      },
      error: () => {
        this.error = 'Failed to load field type configurations. Please try again.';
        this.loading = false;
      },
    });
  }

  createConfig(): void {
    if (!this.newFieldName.trim()) return;

    this.createError = null;
    this.fieldTypeService
      .upsertConfig(
        this.newFieldName.trim(),
        this.newConfiguredType,
        this.newConfiguredType === 'datetime' ? this.newDatetimeFormat.trim() || null : null
      )
      .subscribe({
        next: response => {
          if (response.success) {
            this.newFieldName = '';
            this.newConfiguredType = 'string';
            this.newDatetimeFormat = '';
            this.loadData();
          } else {
            this.createError = response.error || response.message;
          }
        },
        error: () => {
          this.createError = 'Failed to save field type configuration. Please try again.';
        },
      });
  }

  deleteConfig(fieldName: string): void {
    if (!confirm(`Remove type configuration for "${fieldName}"?`)) return;

    this.deleteError = null;
    this.fieldTypeService.deleteConfig(fieldName).subscribe({
      next: () => this.loadData(),
      error: () => {
        this.deleteError = `Failed to delete configuration for "${fieldName}". Please try again.`;
      },
    });
  }

  prefillFromObservation(obs: FieldObservation): void {
    this.newFieldName = obs.field_name;
    this.newConfiguredType = this.jsonTypeToFieldType[obs.observed_json_type] ?? 'compare_as_is';
    this.newDatetimeFormat = '';
    this.createError = null;
    // Scroll to / focus the form
    document.getElementById('field-name-input')?.focus();
  }

  isConfigured(fieldName: string): boolean {
    return this.configs.some(c => c.field_name === fieldName);
  }

  formatLastSeen(dateStr: string | null): string {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleString();
  }
}
