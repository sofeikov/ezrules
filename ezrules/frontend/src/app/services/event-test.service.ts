import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface EventTestRequest {
  event_id: string;
  event_timestamp: number;
  event_data: Record<string, unknown>;
}

export interface EventTestRuleResult {
  r_id: number;
  rid: string;
  description: string;
  evaluation_lane: string;
  outcome: string | null;
  matched: boolean;
}

export interface EventTestResponse {
  dry_run: boolean;
  skipped_main_rules: boolean;
  outcome_counters: Record<string, number>;
  outcome_set: string[];
  resolved_outcome: string | null;
  rule_results: Record<string, string>;
  event_version: number | null;
  evaluation_decision_id: number | null;
  all_rule_results: Record<string, string | null>;
  evaluated_rules: EventTestRuleResult[];
}

@Injectable({
  providedIn: 'root'
})
export class EventTestService {
  private apiUrl = `${environment.apiUrl}/api/v2/event-tests`;

  constructor(private http: HttpClient) {}

  runTest(request: EventTestRequest): Observable<EventTestResponse> {
    return this.http.post<EventTestResponse>(this.apiUrl, request);
  }
}
