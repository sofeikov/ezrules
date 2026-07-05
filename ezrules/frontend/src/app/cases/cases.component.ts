import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SidebarComponent } from '../components/sidebar.component';
import { CaseDetail, CaseItem, CaseService, IntegrationEvent } from '../services/case.service';

@Component({
  selector: 'app-cases',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent],
  template: `
    <app-sidebar></app-sidebar>
    <main class="ml-64 min-h-screen bg-gray-50">
      <div class="px-8 py-6">
        <div class="mb-6 flex items-center justify-between gap-4">
          <div>
            <h1 class="text-2xl font-bold text-gray-900">Cases</h1>
            <p class="mt-1 text-sm text-gray-600">Review non-neutral decisions and publish case outcomes.</p>
          </div>
          <select
            data-testid="case-status-filter"
            [(ngModel)]="statusFilter"
            (change)="loadCases()"
            class="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
          >
            <option value="">All statuses</option>
            <option value="open">Open</option>
            <option value="in_review">In review</option>
            <option value="resolved">Resolved</option>
            <option value="closed">Closed</option>
          </select>
        </div>

        <div *ngIf="error" class="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ error }}
        </div>
        <div *ngIf="success" class="mb-4 rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          {{ success }}
        </div>

        <div class="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <section class="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <div class="border-b border-gray-200 px-4 py-3">
              <h2 class="text-sm font-semibold text-gray-900">Case inbox</h2>
            </div>
            <div *ngIf="loading" class="p-6 text-sm text-gray-500">Loading cases...</div>
            <div *ngIf="!loading && cases.length === 0" class="p-6 text-sm text-gray-500" data-testid="cases-empty">
              No cases found.
            </div>
            <table *ngIf="!loading && cases.length > 0" class="min-w-full divide-y divide-gray-200" data-testid="cases-table">
              <thead class="bg-gray-50">
                <tr>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Transaction</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Outcome</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">State</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Updated</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100 bg-white">
                <tr
                  *ngFor="let item of cases"
                  (click)="selectCase(item)"
                  class="cursor-pointer hover:bg-gray-50"
                  [class.bg-blue-50]="selected?.id === item.id"
                  data-testid="case-row"
                >
                  <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ item.transaction_id }}</td>
                  <td class="px-4 py-3 text-sm text-gray-700">{{ item.resolved_outcome || 'None' }}</td>
                  <td class="px-4 py-3 text-sm text-gray-700">
                    <span class="rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700">{{ item.status }}</span>
                    <span *ngIf="item.decision_state !== 'current'" class="ml-2 rounded-full bg-amber-100 px-2 py-1 text-xs font-medium text-amber-800">
                      {{ item.decision_state }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-sm text-gray-500">{{ item.updated_at | date:'short' }}</td>
                </tr>
              </tbody>
            </table>
          </section>

          <aside class="space-y-6">
            <section class="rounded-lg border border-gray-200 bg-white" data-testid="case-detail">
              <div class="border-b border-gray-200 px-4 py-3">
                <h2 class="text-sm font-semibold text-gray-900">Selected case</h2>
              </div>
              <div *ngIf="!selected" class="p-4 text-sm text-gray-500">Select a case to review.</div>
              <div *ngIf="selected" class="space-y-4 p-4">
                <dl class="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt class="text-gray-500">Case ID</dt>
                    <dd class="font-medium text-gray-900">{{ selected.id }}</dd>
                  </div>
                  <div>
                    <dt class="text-gray-500">Evaluation</dt>
                    <dd class="font-medium text-gray-900">{{ selected.current_evaluation_decision_id }}</dd>
                  </div>
                  <div>
                    <dt class="text-gray-500">Outcome</dt>
                    <dd class="font-medium text-gray-900">{{ selected.resolved_outcome || 'None' }}</dd>
                  </div>
                  <div>
                    <dt class="text-gray-500">Status</dt>
                    <dd class="font-medium text-gray-900">{{ selected.status }}</dd>
                  </div>
                </dl>

                <div
                  *ngIf="selected.decision_state !== 'current'"
                  class="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
                  data-testid="case-rescored-banner"
                >
                  Current score no longer matches the original case outcome.
                </div>

                <div *ngIf="selected.status !== 'resolved'" class="space-y-3">
                  <label class="block text-sm font-medium text-gray-700" for="case-resolution-note">Resolution note</label>
                  <textarea
                    id="case-resolution-note"
                    data-testid="case-resolution-note"
                    [(ngModel)]="resolutionNote"
                    rows="4"
                    class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  ></textarea>
                  <button
                    type="button"
                    data-testid="case-resolve-button"
                    (click)="resolveSelectedCase()"
                    [disabled]="saving || !resolutionNote.trim()"
                    class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-300"
                  >
                    Resolve case
                  </button>
                </div>

                <div>
                  <h3 class="mb-2 text-sm font-semibold text-gray-900">Timeline</h3>
                  <ol class="space-y-2" data-testid="case-events">
                    <li *ngFor="let event of detail?.events" class="rounded-md bg-gray-50 px-3 py-2 text-sm">
                      <div class="font-medium text-gray-900">{{ event.event_type }}</div>
                      <div class="text-xs text-gray-500">{{ event.occurred_at | date:'short' }}</div>
                    </li>
                  </ol>
                </div>
              </div>
            </section>

            <section class="rounded-lg border border-gray-200 bg-white">
              <div class="border-b border-gray-200 px-4 py-3">
                <h2 class="text-sm font-semibold text-gray-900">Recent integration events</h2>
              </div>
              <div class="max-h-72 overflow-y-auto p-4">
                <div *ngIf="integrationEvents.length === 0" class="text-sm text-gray-500">No integration events.</div>
                <div *ngFor="let event of integrationEvents" class="border-b border-gray-100 py-2 text-sm last:border-0">
                  <div class="font-medium text-gray-900">{{ event.event_type }}</div>
                  <div class="text-xs text-gray-500">{{ event.external_event_id }}</div>
                </div>
              </div>
            </section>
          </aside>
        </div>
      </div>
    </main>
  `
})
export class CasesComponent implements OnInit {
  cases: CaseItem[] = [];
  selected: CaseItem | null = null;
  detail: CaseDetail | null = null;
  integrationEvents: IntegrationEvent[] = [];
  statusFilter = '';
  resolutionNote = '';
  loading = true;
  saving = false;
  error: string | null = null;
  success: string | null = null;

  constructor(private caseService: CaseService) {}

  ngOnInit(): void {
    this.loadCases();
    this.loadIntegrationEvents();
  }

  loadCases(): void {
    this.loading = true;
    this.error = null;
    this.caseService.getCases(this.statusFilter || undefined).subscribe({
      next: (response) => {
        this.cases = response.cases;
        this.loading = false;
        if (!this.selected && this.cases.length > 0) {
          this.selectCase(this.cases[0]);
        }
      },
      error: () => {
        this.error = 'Failed to load cases.';
        this.loading = false;
      }
    });
  }

  selectCase(item: CaseItem): void {
    this.selected = item;
    this.resolutionNote = '';
    this.caseService.getCase(item.id).subscribe({
      next: (detail) => {
        this.detail = detail;
        this.selected = detail.case;
      },
      error: () => {
        this.error = 'Failed to load case details.';
      }
    });
  }

  resolveSelectedCase(): void {
    if (!this.selected || this.saving || !this.resolutionNote.trim()) {
      return;
    }
    this.saving = true;
    this.error = null;
    this.success = null;
    this.caseService.resolveCase(
      this.selected.id,
      this.resolutionNote,
      this.selected.current_evaluation_decision_id,
    ).subscribe({
      next: (response) => {
        this.success = 'Case resolved.';
        this.saving = false;
        this.selected = response.case;
        this.loadCases();
        this.selectCase(response.case);
        this.loadIntegrationEvents();
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Failed to resolve case.';
        this.saving = false;
      }
    });
  }

  loadIntegrationEvents(): void {
    this.caseService.getIntegrationEvents().subscribe({
      next: (response) => {
        this.integrationEvents = response.events;
      },
      error: () => {
        this.integrationEvents = [];
      }
    });
  }
}
