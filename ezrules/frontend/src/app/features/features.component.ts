import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SidebarComponent } from '../components/sidebar.component';
import { ACTION_PERMISSION_REQUIREMENTS, hasPermissionRequirement } from '../auth/permissions';
import { AuthService } from '../services/auth.service';
import { FeatureAggregation, FeatureDefinition, FeatureDefinitionPayload, FeatureService } from '../services/feature.service';

interface WindowOption {
  label: string;
  seconds: number;
}

@Component({
  selector: 'app-features',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent],
  template: `
    <div class="flex min-h-screen bg-gray-50">
      <app-sidebar></app-sidebar>
      <div class="ml-64 flex-1">
        <div class="p-8">
          <div class="mb-8 flex items-start justify-between gap-4">
            <div>
              <h1 class="text-3xl font-bold text-gray-900">Features</h1>
              <p class="mt-1 text-gray-600">Define computed history-aware stats for rule logic using <code>stat[entity.feature]</code>.</p>
            </div>
          </div>

          <div *ngIf="loading" class="flex justify-center py-20">
            <div class="h-12 w-12 animate-spin rounded-full border-b-2 border-blue-600"></div>
          </div>

          <div *ngIf="error && !loading" class="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-800">
            {{ error }}
          </div>

          <div *ngIf="!loading">
            <div *ngIf="canModify" class="mb-6 rounded-lg border border-gray-200 bg-white p-6">
              <h2 class="mb-4 text-lg font-semibold text-gray-900">{{ editing ? 'Edit Feature' : 'Create Feature' }}</h2>
              <div class="grid grid-cols-1 gap-3 md:grid-cols-6">
                <label class="md:col-span-2">
                  <span class="mb-1 block text-xs font-medium text-gray-600">Name</span>
                  <input [(ngModel)]="form.name" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                </label>
                <label>
                  <span class="mb-1 block text-xs font-medium text-gray-600">Entity</span>
                  <input [(ngModel)]="form.entity" placeholder="sender" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                </label>
                <label class="md:col-span-2">
                  <span class="mb-1 block text-xs font-medium text-gray-600">Feature name</span>
                  <input [(ngModel)]="form.feature_name" placeholder="sent_amount_sum_24h" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                </label>
                <label>
                  <span class="mb-1 block text-xs font-medium text-gray-600">Window</span>
                  <select [(ngModel)]="form.window_seconds" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <option *ngFor="let option of windowOptions" [ngValue]="option.seconds">{{ option.label }}</option>
                  </select>
                </label>
                <label class="md:col-span-2">
                  <span class="mb-1 block text-xs font-medium text-gray-600">Entity key field</span>
                  <input [(ngModel)]="form.entity_key" placeholder="sender_id" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                </label>
                <label>
                  <span class="mb-1 block text-xs font-medium text-gray-600">Aggregation</span>
                  <select [(ngModel)]="form.aggregation_type" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <option *ngFor="let aggregation of aggregationOptions" [ngValue]="aggregation">{{ aggregation }}</option>
                  </select>
                </label>
                <label class="md:col-span-2">
                  <span class="mb-1 block text-xs font-medium text-gray-600">Source field</span>
                  <input [(ngModel)]="form.source_field" [disabled]="!needsSourceField()" placeholder="amount" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" />
                </label>
                <label>
                  <span class="mb-1 block text-xs font-medium text-gray-600">Null handling</span>
                  <select [(ngModel)]="form.null_handling" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <option value="exclude">exclude</option>
                    <option value="zero">zero</option>
                  </select>
                </label>
              </div>
              <p class="mt-3 text-sm text-gray-600">Path: <code>{{ previewPath() }}</code></p>
              <div *ngIf="saveError" class="mt-3 text-sm text-red-600">{{ saveError }}</div>
              <div class="mt-4 flex gap-3">
                <button (click)="save()" class="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700">Save</button>
                <button *ngIf="editing" (click)="cancelEdit()" class="rounded-lg border border-gray-300 px-5 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Cancel</button>
              </div>
            </div>

            <div class="overflow-hidden rounded-lg border border-gray-200 bg-white">
              <div class="border-b border-gray-200 bg-gray-50 px-6 py-4">
                <h2 class="text-base font-semibold text-gray-900">Feature Registry <span class="text-sm font-normal text-gray-500">({{ features.length }})</span></h2>
              </div>
              <div *ngIf="features.length === 0" class="py-12 text-center text-sm text-gray-500">No features configured yet.</div>
              <table *ngIf="features.length > 0" class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                  <tr>
                    <th class="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Name</th>
                    <th class="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Path</th>
                    <th class="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Aggregation</th>
                    <th class="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Status</th>
                    <th class="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Used by</th>
                    <th class="px-6 py-3"></th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-200 bg-white">
                  <tr *ngFor="let feature of features">
                    <td class="px-6 py-4 text-sm font-medium text-gray-900">{{ feature.name }}</td>
                    <td class="px-6 py-4 text-sm font-mono text-gray-700">{{ feature.available_as }}</td>
                    <td class="px-6 py-4 text-sm text-gray-700">{{ formatAggregation(feature) }}</td>
                    <td class="px-6 py-4 text-sm">
                      <span class="rounded px-2 py-0.5 text-xs font-medium" [ngClass]="statusClass(feature.status)">{{ feature.status }}</span>
                    </td>
                    <td class="px-6 py-4 text-sm text-gray-600">{{ feature.dependency_count }} rules</td>
                    <td class="px-6 py-4 text-right text-sm" *ngIf="canModify">
                      <button (click)="edit(feature)" class="mr-2 rounded border border-blue-300 px-3 py-1 text-blue-600 hover:bg-blue-50">Edit</button>
                      <button *ngIf="feature.status !== 'active'" (click)="activate(feature)" class="mr-2 rounded border border-green-300 px-3 py-1 text-green-700 hover:bg-green-50">Activate</button>
                      <button *ngIf="feature.status === 'active'" (click)="deprecate(feature)" class="rounded border border-amber-300 px-3 py-1 text-amber-700 hover:bg-amber-50">Deprecate</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  `
})
export class FeaturesComponent implements OnInit {
  features: FeatureDefinition[] = [];
  loading = true;
  error = '';
  saveError = '';
  permissions: string[] = [];
  editing: FeatureDefinition | null = null;
  readonly aggregationOptions: FeatureAggregation[] = ['count', 'count_distinct', 'sum', 'avg', 'min', 'max', 'stddev', 'days_since_first_seen'];
  readonly windowOptions: WindowOption[] = [
    { label: '10m', seconds: 600 },
    { label: '1h', seconds: 3600 },
    { label: '24h', seconds: 86400 },
    { label: '7d', seconds: 604800 },
    { label: '30d', seconds: 2592000 },
    { label: '90d', seconds: 7776000 },
  ];
  form: FeatureDefinitionPayload = this.emptyForm();

  constructor(private featureService: FeatureService, private authService: AuthService) { }

  get canModify(): boolean {
    return hasPermissionRequirement(this.permissions, ACTION_PERMISSION_REQUIREMENTS.modifyFeatures);
  }

  ngOnInit(): void {
    this.authService.getCurrentUser().subscribe({
      next: (user) => {
        this.permissions = user.permissions;
      },
      error: () => {
        this.permissions = [];
      }
    });
    this.load();
  }

  load(): void {
    this.loading = true;
    this.featureService.getFeatures().subscribe({
      next: (features) => {
        this.features = features;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load features.';
        this.loading = false;
      }
    });
  }

  emptyForm(): FeatureDefinitionPayload {
    return {
      name: '',
      entity: 'sender',
      feature_name: '',
      entity_key: 'sender_id',
      aggregation_type: 'sum',
      source_field: 'amount',
      window_seconds: 86400,
      filters: [],
      inclusion_policy: 'previous_events',
      null_handling: 'exclude',
    };
  }

  needsSourceField(): boolean {
    return !['count', 'days_since_first_seen'].includes(this.form.aggregation_type);
  }

  previewPath(): string {
    return `stat[${this.form.entity || 'entity'}.${this.form.feature_name || 'feature_name'}]`;
  }

  save(): void {
    this.saveError = '';
    const payload = { ...this.form, source_field: this.needsSourceField() ? this.form.source_field : null };
    const request = this.editing
      ? this.featureService.updateFeature(this.editing.fd_id, payload)
      : this.featureService.createFeature(payload);
    request.subscribe({
      next: () => {
        this.form = this.emptyForm();
        this.editing = null;
        this.load();
      },
      error: (error) => {
        this.saveError = this.formatSaveError(error);
      }
    });
  }

  private formatSaveError(error: unknown): string {
    const detail = (error as { error?: { detail?: unknown; error?: unknown } })?.error?.detail
      ?? (error as { error?: { detail?: unknown; error?: unknown } })?.error?.error;
    if (typeof detail === 'string') {
      return detail;
    }
    if (Array.isArray(detail)) {
      const messages = detail.map((item) => this.formatValidationIssue(item)).filter(Boolean);
      if (messages.length > 0) {
        return messages.join(' ');
      }
    }
    return 'Failed to save feature.';
  }

  private formatValidationIssue(issue: unknown): string {
    if (!issue || typeof issue !== 'object') {
      return '';
    }
    const rawIssue = issue as { loc?: unknown; msg?: unknown };
    const field = this.formatValidationField(rawIssue.loc);
    const message = this.formatValidationMessage(String(rawIssue.msg || 'Invalid value'));
    return field ? `${field}: ${message}` : message;
  }

  private formatValidationField(loc: unknown): string {
    if (!Array.isArray(loc)) {
      return '';
    }
    const field = loc.filter((part) => part !== 'body').pop();
    if (typeof field !== 'string') {
      return '';
    }
    return field
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (character) => character.toUpperCase());
  }

  private formatValidationMessage(message: string): string {
    if (message.includes('String should match pattern')) {
      return 'use letters, numbers, and underscores; start with a letter or underscore.';
    }
    if (message.includes('Field required')) {
      return 'is required.';
    }
    return `${message}.`;
  }

  edit(feature: FeatureDefinition): void {
    this.editing = feature;
    this.form = {
      name: feature.name,
      description: feature.description,
      entity: feature.entity,
      feature_name: feature.feature_name,
      entity_key: feature.entity_key,
      aggregation_type: feature.aggregation_type,
      source_field: feature.source_field,
      window_seconds: feature.window_seconds,
      filters: feature.filters,
      inclusion_policy: feature.inclusion_policy,
      null_handling: feature.null_handling,
    };
  }

  cancelEdit(): void {
    this.editing = null;
    this.form = this.emptyForm();
  }

  activate(feature: FeatureDefinition): void {
    this.featureService.activateFeature(feature.fd_id).subscribe({ next: () => this.load(), error: () => this.error = 'Failed to activate feature.' });
  }

  deprecate(feature: FeatureDefinition): void {
    this.featureService.deprecateFeature(feature.fd_id).subscribe({ next: () => this.load(), error: () => this.error = 'Failed to deprecate feature.' });
  }

  formatAggregation(feature: FeatureDefinition): string {
    const source = feature.source_field ? `(${feature.source_field})` : '';
    return `${feature.aggregation_type}${source} / ${feature.window_label}`;
  }

  statusClass(status: string): string {
    if (status === 'active') {
      return 'bg-green-100 text-green-700';
    }
    if (status === 'deprecated') {
      return 'bg-amber-100 text-amber-700';
    }
    return 'bg-gray-100 text-gray-700';
  }
}
