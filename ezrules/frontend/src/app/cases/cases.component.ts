import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SidebarComponent } from '../components/sidebar.component';
import { AuthService, AuthUser } from '../services/auth.service';
import { CaseAssignee, CaseDetail, CaseItem, CaseService, IntegrationEvent } from '../services/case.service';

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
          <div class="flex flex-wrap items-center gap-2">
            <input
              data-testid="case-search"
              [(ngModel)]="searchQuery"
              (keyup.enter)="loadCases()"
              placeholder="Search transaction"
              class="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
            />
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
            </select>
            <select
              data-testid="case-assignment-filter"
              [(ngModel)]="assignedToFilter"
              (change)="loadCases()"
              class="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
            >
              <option value="">All assignments</option>
              <option value="me">Assigned to me</option>
              <option value="unassigned">Unassigned</option>
            </select>
            <button
              type="button"
              (click)="loadCases()"
              class="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700"
            >
              Apply
            </button>
          </div>
        </div>

        <div *ngIf="error" class="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ error }}
        </div>
        <div *ngIf="success" class="mb-4 rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          {{ success }}
        </div>

        <div class="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_560px]">
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
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Assignee</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-gray-500">Priority</th>
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
                  <td class="px-4 py-3 text-sm text-gray-700">{{ item.assigned_to_email || 'Unassigned' }}</td>
                  <td class="px-4 py-3 text-sm text-gray-700">{{ item.priority }}</td>
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
                    <dt class="text-gray-500">Transaction</dt>
                    <dd class="break-all font-medium text-gray-900" data-testid="case-detail-transaction">
                      {{ selected.transaction_id }}
                    </dd>
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

                <div *ngIf="selected.status !== 'resolved'" class="space-y-3 rounded-md border border-gray-200 bg-gray-50 p-3">
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <h3 class="text-sm font-semibold text-gray-900">Assignment</h3>
                      <p class="text-sm text-gray-600">{{ selected.assigned_to_email || 'Unassigned' }}</p>
                    </div>
                    <button
                      type="button"
                      data-testid="case-claim-button"
                      (click)="claimSelectedCase()"
                      [disabled]="saving || !currentUser || selected.assigned_to_user_id === currentUser.id"
                      class="rounded-md bg-gray-900 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-300"
                    >
                      Claim
                    </button>
                  </div>
                  <div class="flex gap-2">
                    <select
                      data-testid="case-assignee-select"
                      [(ngModel)]="selectedAssigneeId"
                      class="min-w-0 flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                    >
                      <option [ngValue]="null">Unassigned</option>
                      <option *ngFor="let assignee of assignees" [ngValue]="assignee.id">{{ assignee.email }}</option>
                    </select>
                    <button
                      type="button"
                      data-testid="case-assign-button"
                      (click)="assignSelectedCase(selectedAssigneeId)"
                      [disabled]="saving"
                      class="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700"
                    >
                      Save
                    </button>
                  </div>
                </div>

                <div *ngIf="detail?.evaluation as evaluation" class="space-y-4">
                  <div class="rounded-md border border-gray-200 bg-gray-50 p-3" data-testid="case-evaluation-context">
                    <div class="mb-3 flex items-center justify-between gap-3">
                      <h3 class="text-sm font-semibold text-gray-900">Evaluation context</h3>
                      <span
                        class="rounded-full px-2 py-1 text-xs font-medium"
                        [ngClass]="evaluation.is_current ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'"
                      >
                        {{ evaluation.is_current ? 'Current' : 'Superseded' }}
                      </span>
                    </div>
                    <dl class="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <dt class="text-gray-500">Event version</dt>
                        <dd class="font-medium text-gray-900">{{ evaluation.event_version }}</dd>
                      </div>
                      <div>
                        <dt class="text-gray-500">Event version ID</dt>
                        <dd class="font-medium text-gray-900">{{ evaluation.event_version_id }}</dd>
                      </div>
                      <div>
                        <dt class="text-gray-500">Effective</dt>
                        <dd class="font-medium text-gray-900">{{ evaluation.effective_at | date:'short' }}</dd>
                      </div>
                      <div>
                        <dt class="text-gray-500">Evaluated</dt>
                        <dd class="font-medium text-gray-900">{{ evaluation.evaluated_at | date:'short' }}</dd>
                      </div>
                    </dl>
                    <div *ngIf="outcomeCounterEntries(evaluation.outcome_counters).length > 0" class="mt-3 flex flex-wrap gap-2">
                      <span
                        *ngFor="let counter of outcomeCounterEntries(evaluation.outcome_counters)"
                        class="rounded-full bg-white px-2 py-1 text-xs font-medium text-gray-700 ring-1 ring-gray-200"
                      >
                        {{ counter.key }}: {{ counter.value }}
                      </span>
                    </div>
                  </div>

                  <div class="rounded-md border border-gray-200 bg-white" data-testid="case-triggered-rules">
                    <div class="border-b border-gray-200 px-3 py-2">
                      <h3 class="text-sm font-semibold text-gray-900">Triggered rules</h3>
                    </div>
                    <div *ngIf="evaluation.triggered_rules.length === 0" class="px-3 py-3 text-sm text-gray-500">
                      No triggered rule details were stored for this evaluation.
                    </div>
                    <div *ngFor="let rule of evaluation.triggered_rules" class="border-b border-gray-100 px-3 py-3 last:border-0">
                      <div class="flex items-start justify-between gap-3">
                        <div class="min-w-0">
                          <div class="truncate text-sm font-semibold text-gray-900">{{ rule.rid }}</div>
                          <div class="text-sm text-gray-600">{{ rule.description }}</div>
                        </div>
                        <span class="shrink-0 rounded-full bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-700">
                          {{ rule.outcome }}
                        </span>
                      </div>
                      <div *ngIf="rule.referenced_fields?.length" class="mt-2 flex flex-wrap gap-1">
                        <span
                          *ngFor="let field of rule.referenced_fields"
                          class="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600"
                        >
                          {{ field }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div class="rounded-md border border-gray-200 bg-white" data-testid="case-event-payload">
                    <div class="border-b border-gray-200 px-3 py-2">
                      <h3 class="text-sm font-semibold text-gray-900">Event payload</h3>
                    </div>
                    <pre class="max-h-80 overflow-auto p-3 text-xs leading-5 text-gray-800">{{ formatJson(evaluation.event_data) }}</pre>
                  </div>
                </div>

                <div *ngIf="selected.status !== 'resolved'" class="space-y-3 rounded-md border border-gray-200 p-3">
                  <label class="block text-sm font-medium text-gray-700" for="case-note">Add note</label>
                  <textarea
                    id="case-note"
                    data-testid="case-note"
                    [(ngModel)]="noteText"
                    rows="3"
                    class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  ></textarea>
                  <button
                    type="button"
                    data-testid="case-add-note-button"
                    (click)="addNoteToSelectedCase()"
                    [disabled]="saving || !noteText.trim()"
                    class="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 disabled:cursor-not-allowed disabled:bg-gray-100"
                  >
                    Add note
                  </button>
                </div>

                <div *ngIf="selected.status !== 'resolved'" class="space-y-3">
                  <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <label class="block text-sm font-medium text-gray-700" for="case-resolution-disposition">Disposition</label>
                      <select
                        id="case-resolution-disposition"
                        data-testid="case-resolution-disposition"
                        [(ngModel)]="resolutionDisposition"
                        class="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                      >
                        <option value="">Select</option>
                        <option value="confirmed_fraud">Confirmed fraud</option>
                        <option value="false_positive">False positive</option>
                        <option value="approved">Approved</option>
                        <option value="rejected">Rejected</option>
                        <option value="duplicate">Duplicate</option>
                        <option value="unable_to_verify">Unable to verify</option>
                        <option value="escalated">Escalated</option>
                      </select>
                    </div>
                    <div>
                      <label class="block text-sm font-medium text-gray-700" for="case-resolution-action">Action</label>
                      <select
                        id="case-resolution-action"
                        data-testid="case-resolution-action"
                        [(ngModel)]="resolutionAction"
                        class="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                      >
                        <option value="none">None</option>
                        <option value="release_transaction">Release transaction</option>
                        <option value="cancel_transaction">Cancel transaction</option>
                        <option value="block_customer">Block customer</option>
                        <option value="escalate_external_review">Escalate external review</option>
                      </select>
                    </div>
                  </div>
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
                    [disabled]="saving || !resolutionDisposition || !resolutionNote.trim()"
                    class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-300"
                  >
                    Resolve case
                  </button>
                </div>

                <div *ngIf="selected.status === 'resolved'" class="rounded-md border border-green-200 bg-green-50 p-3 text-sm">
                  <div class="font-semibold text-green-900">Resolution</div>
                  <div class="mt-1 text-green-800">{{ selected.resolution_disposition || 'No disposition' }} / {{ selected.resolution_action || 'none' }}</div>
                  <div *ngIf="selected.resolution_note" class="mt-2 text-green-800">{{ selected.resolution_note }}</div>
                </div>

                <div>
                  <h3 class="mb-2 text-sm font-semibold text-gray-900">Timeline</h3>
                  <ol class="space-y-2" data-testid="case-events">
                    <li *ngFor="let event of detail?.events" class="rounded-md bg-gray-50 px-3 py-2 text-sm">
                      <div class="font-medium text-gray-900">{{ event.event_type }}</div>
                      <div class="text-xs text-gray-500">{{ event.occurred_at | date:'short' }}</div>
                      <div *ngIf="event.details['note']" class="mt-1 text-gray-700">{{ event.details['note'] }}</div>
                      <div *ngIf="event.details['resolution_disposition']" class="mt-1 text-gray-700">
                        {{ event.details['resolution_disposition'] }} / {{ event.details['resolution_action'] || 'none' }}
                      </div>
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
  assignees: CaseAssignee[] = [];
  integrationEvents: IntegrationEvent[] = [];
  currentUser: AuthUser | null = null;
  statusFilter = '';
  assignedToFilter = '';
  searchQuery = '';
  selectedAssigneeId: number | null = null;
  noteText = '';
  resolutionDisposition = '';
  resolutionAction = 'none';
  resolutionNote = '';
  loading = true;
  saving = false;
  error: string | null = null;
  success: string | null = null;

  constructor(private caseService: CaseService, private authService: AuthService) {}

  outcomeCounterEntries(counters: Record<string, number>): Array<{ key: string; value: number }> {
    return Object.entries(counters).map(([key, value]) => ({ key, value }));
  }

  formatJson(value: Record<string, unknown>): string {
    return JSON.stringify(value, null, 2);
  }

  ngOnInit(): void {
    this.authService.getCurrentUser().subscribe({
      next: (user) => {
        this.currentUser = user;
      },
      error: () => {
        this.currentUser = null;
      }
    });
    this.loadAssignees();
    this.loadCases();
    this.loadIntegrationEvents();
  }

  loadCases(): void {
    this.loading = true;
    this.error = null;
    this.caseService.getCases({
      status: this.statusFilter || undefined,
      assignedTo: this.assignedToFilter || undefined,
      query: this.searchQuery.trim() || undefined,
    }).subscribe({
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
    this.selectedAssigneeId = item.assigned_to_user_id;
    this.noteText = '';
    this.resetResolutionForm();
    this.caseService.getCase(item.id).subscribe({
      next: (detail) => {
        this.detail = detail;
        this.selected = detail.case;
        this.selectedAssigneeId = detail.case.assigned_to_user_id;
      },
      error: () => {
        this.error = 'Failed to load case details.';
      }
    });
  }

  resetResolutionForm(): void {
    this.resolutionDisposition = '';
    this.resolutionAction = 'none';
    this.resolutionNote = '';
  }

  loadAssignees(): void {
    this.caseService.getAssignees().subscribe({
      next: (response) => {
        this.assignees = response.users;
      },
      error: () => {
        this.assignees = [];
      }
    });
  }

  claimSelectedCase(): void {
    if (!this.currentUser) {
      return;
    }
    this.assignSelectedCase(this.currentUser.id);
  }

  assignSelectedCase(assignedToUserId: number | null): void {
    if (!this.selected || this.saving) {
      return;
    }
    this.saving = true;
    this.error = null;
    this.success = null;
    this.caseService.assignCase(this.selected.id, assignedToUserId).subscribe({
      next: (response) => {
        this.success = 'Case assignment updated.';
        this.saving = false;
        this.selected = response.case;
        this.selectedAssigneeId = response.case.assigned_to_user_id;
        this.loadCases();
        this.selectCase(response.case);
        this.loadIntegrationEvents();
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Failed to update case assignment.';
        this.saving = false;
      }
    });
  }

  addNoteToSelectedCase(): void {
    if (!this.selected || this.saving || !this.noteText.trim()) {
      return;
    }
    this.saving = true;
    this.error = null;
    this.success = null;
    this.caseService.addNote(this.selected.id, this.noteText).subscribe({
      next: () => {
        this.success = 'Case note added.';
        this.saving = false;
        this.noteText = '';
        if (this.selected) {
          this.selectCase(this.selected);
        }
        this.loadIntegrationEvents();
      },
      error: (err) => {
        this.error = err?.error?.detail || 'Failed to add case note.';
        this.saving = false;
      }
    });
  }

  resolveSelectedCase(): void {
    if (!this.selected || this.saving || !this.resolutionDisposition || !this.resolutionNote.trim()) {
      return;
    }
    this.saving = true;
    this.error = null;
    this.success = null;
    this.caseService.resolveCase(
      this.selected.id,
      this.resolutionDisposition,
      this.resolutionAction,
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
