import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface OperationsMetrics {
  active_cases: number;
  unassigned_cases: number;
  resolved_cases: number;
  dispositioned_cases: number;
  false_positive_cases: number;
  false_positive_rate: number | null;
}

export interface OperationsCaseFlowPoint {
  date: string;
  opened: number;
  resolved: number;
}

export interface OperationsAttentionCase {
  case_id: number;
  outcome: string | null;
  assigned_to_email: string | null;
  age_seconds: number;
}

export interface OperationsNoisyRule {
  rid: string;
  description: string;
  case_count: number;
  resolved_count: number;
  false_positive_count: number;
  false_positive_rate: number | null;
}

export interface OperationsSummaryResponse {
  days: number;
  period_start: string;
  period_end: string;
  generated_at: string;
  summary: OperationsMetrics;
  case_flow: OperationsCaseFlowPoint[];
  attention_cases: OperationsAttentionCase[];
  noisy_rules: OperationsNoisyRule[];
}

@Injectable({ providedIn: 'root' })
export class OperationsDashboardService {
  private readonly summaryUrl = `${environment.apiUrl}/api/v2/operations/summary`;

  constructor(private readonly http: HttpClient) {}

  getSummary(days: number): Observable<OperationsSummaryResponse> {
    return this.http.get<OperationsSummaryResponse>(this.summaryUrl, {
      params: new HttpParams().set('days', String(days))
    });
  }
}
