import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface TriggeredRule {
  r_id: number;
  rid: string;
  description: string;
  outcome: string;
  metadata_source: string;
  referenced_fields: string[];
}

export interface TestedEvent {
  evaluation_decision_id: number;
  transaction_id: string;
  effective_at: string;
  observed_at: string;
  first_effective_at: string;
  first_observed_at: string;
  event_version: number;
  is_current: boolean;
  resolved_outcome: string | null;
  label_name: string | null;
  outcome_counters: Record<string, number>;
  event_data: Record<string, unknown>;
  triggered_rules: TriggeredRule[];
}

export interface TestedEventsResponse {
  events: TestedEvent[];
  total: number;
  limit: number;
}

export interface TestedEventGraphNode {
  id: string;
  kind: 'event' | 'entity';
  label: string;
  entity_type: string | null;
  entity_value: string | null;
  entity_value_hash: string | null;
  transaction_id: string | null;
  event_version: number | null;
  effective_at: string | null;
  root: boolean;
  expandable: boolean;
}

export interface TestedEventGraphEdge {
  id: string;
  source: string;
  target: string;
  label: string | null;
  field_path: string | null;
}

export interface TestedEventGraphResponse {
  nodes: TestedEventGraphNode[];
  edges: TestedEventGraphEdge[];
  root_event_node_id: string;
  max_events: number;
  max_hops: number;
  event_count: number;
  truncated: boolean;
}

export interface TestedEventGraphOptions {
  maxEvents?: number;
  maxHops?: number;
  expandEntityType?: string;
  expandEntityValueHash?: string;
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

  getTestedEventGraph(evaluationDecisionId: number, options: TestedEventGraphOptions = {}): Observable<TestedEventGraphResponse> {
    let params = new HttpParams();
    if (options.maxEvents !== undefined) {
      params = params.set('max_events', String(options.maxEvents));
    }
    if (options.maxHops !== undefined) {
      params = params.set('max_hops', String(options.maxHops));
    }
    if (options.expandEntityType && options.expandEntityValueHash) {
      params = params
        .set('expand_entity_type', options.expandEntityType)
        .set('expand_entity_value_hash', options.expandEntityValueHash);
    }
    return this.http.get<TestedEventGraphResponse>(`${this.apiUrl}/${evaluationDecisionId}/graph`, { params });
  }
}
