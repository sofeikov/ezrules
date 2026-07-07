import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface CaseItem {
  id: number;
  transaction_id: string;
  current_event_version_id: number;
  current_evaluation_decision_id: number;
  opened_by_evaluation_decision_id: number;
  previous_evaluation_decision_id: number | null;
  resolved_outcome: string | null;
  previous_resolved_outcome: string | null;
  status: string;
  decision_state: string;
  priority: number;
  assigned_to_user_id: number | null;
  assigned_to_email: string | null;
  resolved_by_user_id: number | null;
  resolved_by_email: string | null;
  resolution_disposition: string | null;
  resolution_action: string | null;
  resolution_note: string | null;
  resolution_label_id: number | null;
  reopened_from_case_id: number | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export interface CaseEvent {
  id: number;
  case_id: number;
  event_type: string;
  actor_user_id: number | null;
  source_ed_id: number | null;
  external_event_id: string;
  occurred_at: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface CaseTriggeredRule {
  r_id: number;
  rid: string;
  description: string;
  outcome: string;
  metadata_source: string;
  referenced_fields: string[] | null;
}

export interface CaseEvaluation {
  evaluation_decision_id: number;
  transaction_id: string;
  event_version_id: number;
  event_version: number;
  effective_at: string;
  observed_at: string;
  evaluated_at: string;
  is_current: boolean;
  resolved_outcome: string | null;
  outcome_counters: Record<string, number>;
  event_data: Record<string, unknown>;
  triggered_rules: CaseTriggeredRule[];
}

export interface CaseDetail {
  case: CaseItem;
  events: CaseEvent[];
  evaluation: CaseEvaluation | null;
}

export interface CaseFilters {
  status?: string;
  assignedTo?: string;
  outcome?: string;
  priorityMin?: number | null;
  decisionState?: string;
  transactionId?: string;
  query?: string;
  createdFrom?: string;
  createdTo?: string;
  updatedFrom?: string;
  updatedTo?: string;
}

export interface CaseAssignee {
  id: number;
  email: string;
}

export interface IntegrationEvent {
  id: number;
  external_event_id: string;
  source_type: string;
  source_id: number;
  event_type: string;
  event_version: number;
  occurred_at: string;
  payload: Record<string, unknown>;
  created_at: string;
}

@Injectable({
  providedIn: 'root'
})
export class CaseService {
  private apiUrl = `${environment.apiUrl}/api/v2`;

  constructor(private http: HttpClient) {}

  getCases(filters: CaseFilters = {}): Observable<{ cases: CaseItem[]; total: number }> {
    let params = new HttpParams().set('limit', 100);
    if (filters.status) {
      params = params.set('status', filters.status);
    }
    if (filters.assignedTo) {
      params = params.set('assigned_to', filters.assignedTo);
    }
    if (filters.outcome) {
      params = params.set('outcome', filters.outcome);
    }
    if (filters.priorityMin !== undefined && filters.priorityMin !== null) {
      params = params.set('priority_min', String(filters.priorityMin));
    }
    if (filters.decisionState) {
      params = params.set('decision_state', filters.decisionState);
    }
    if (filters.transactionId) {
      params = params.set('transaction_id', filters.transactionId);
    }
    if (filters.query) {
      params = params.set('q', filters.query);
    }
    if (filters.createdFrom) {
      params = params.set('created_from', filters.createdFrom);
    }
    if (filters.createdTo) {
      params = params.set('created_to', filters.createdTo);
    }
    if (filters.updatedFrom) {
      params = params.set('updated_from', filters.updatedFrom);
    }
    if (filters.updatedTo) {
      params = params.set('updated_to', filters.updatedTo);
    }
    return this.http.get<{ cases: CaseItem[]; total: number }>(`${this.apiUrl}/cases`, { params });
  }

  getAssignees(): Observable<{ users: CaseAssignee[] }> {
    return this.http.get<{ users: CaseAssignee[] }>(`${this.apiUrl}/cases/assignees`);
  }

  getCase(caseId: number): Observable<CaseDetail> {
    return this.http.get<CaseDetail>(`${this.apiUrl}/cases/${caseId}`);
  }

  assignCase(caseId: number, assignedToUserId: number | null): Observable<{ success: boolean; message: string; case: CaseItem }> {
    return this.http.patch<{ success: boolean; message: string; case: CaseItem }>(`${this.apiUrl}/cases/${caseId}`, {
      assigned_to_user_id: assignedToUserId,
    });
  }

  addNote(caseId: number, note: string): Observable<{ success: boolean; message: string; event: CaseEvent }> {
    return this.http.post<{ success: boolean; message: string; event: CaseEvent }>(`${this.apiUrl}/cases/${caseId}/notes`, {
      note,
    });
  }

  resolveCase(
    caseId: number,
    resolutionDisposition: string,
    resolutionAction: string,
    resolutionNote: string,
    expectedCurrentEvaluationId: number,
  ): Observable<{ success: boolean; message: string; case: CaseItem }> {
    return this.http.post<{ success: boolean; message: string; case: CaseItem }>(`${this.apiUrl}/cases/${caseId}/resolve`, {
      resolution_disposition: resolutionDisposition,
      resolution_action: resolutionAction,
      resolution_note: resolutionNote,
      expected_current_ed_id: expectedCurrentEvaluationId,
    });
  }

  getIntegrationEvents(): Observable<{ events: IntegrationEvent[]; next_cursor: number | null }> {
    return this.http.get<{ events: IntegrationEvent[]; next_cursor: number | null }>(`${this.apiUrl}/integration-events`, {
      params: { limit: 25 },
    });
  }
}
