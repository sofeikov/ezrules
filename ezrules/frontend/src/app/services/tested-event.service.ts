import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface TriggeredRule {
  r_id: number;
  rid: string;
  description: string;
  outcome: string;
  referenced_fields: string[];
}

export interface TestedEvent {
  tl_id: number;
  event_id: string;
  event_timestamp: number;
  resolved_outcome: string | null;
  outcome_counters: Record<string, number>;
  event_data: Record<string, unknown>;
  triggered_rules: TriggeredRule[];
}

export interface TestedEventsResponse {
  events: TestedEvent[];
  total: number;
  limit: number;
}

@Injectable({
  providedIn: 'root'
})
export class TestedEventService {
  private apiUrl = `${environment.apiUrl}/api/v2/tested-events`;

  constructor(private http: HttpClient) {}

  getTestedEvents(limit: number = 50): Observable<TestedEventsResponse> {
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('include_referenced_fields', 'true');
    return this.http.get<TestedEventsResponse>(this.apiUrl, { params });
  }
}
