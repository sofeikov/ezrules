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
  resolved_by_user_id: number | null;
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

export interface CaseDetail {
  case: CaseItem;
  events: CaseEvent[];
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

  getCases(status?: string): Observable<{ cases: CaseItem[]; total: number }> {
    let params = new HttpParams().set('limit', 100);
    if (status) {
      params = params.set('status', status);
    }
    return this.http.get<{ cases: CaseItem[]; total: number }>(`${this.apiUrl}/cases`, { params });
  }

  getCase(caseId: number): Observable<CaseDetail> {
    return this.http.get<CaseDetail>(`${this.apiUrl}/cases/${caseId}`);
  }

  resolveCase(
    caseId: number,
    resolutionNote: string,
    expectedCurrentEvaluationId: number,
  ): Observable<{ success: boolean; message: string; case: CaseItem }> {
    return this.http.post<{ success: boolean; message: string; case: CaseItem }>(`${this.apiUrl}/cases/${caseId}/resolve`, {
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
