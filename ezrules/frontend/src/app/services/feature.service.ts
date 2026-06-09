import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export type FeatureStatus = 'draft' | 'active' | 'deprecated';
export type FeatureKind = 'aggregate' | 'graph';
export type FeatureAggregation = 'count' | 'count_distinct' | 'sum' | 'avg' | 'min' | 'max' | 'stddev' | 'days_since_first_seen' | 'graph_distinct_count';

export interface FeatureFilter {
  field: string;
  operator: 'eq' | 'in';
  value: unknown;
}

export interface GraphFeatureConfig {
  target_entity: string;
  allowed_entity_types: string[];
  max_depth: number;
  max_expanded_nodes: number;
}

export interface FeatureDefinition {
  fd_id: number;
  name: string;
  description: string | null;
  entity: string;
  feature_name: string;
  available_as: string;
  feature_kind: FeatureKind;
  entity_key: string;
  aggregation_type: FeatureAggregation;
  source_field: string | null;
  window_seconds: number;
  window_label: string;
  filters: FeatureFilter[];
  inclusion_policy: string;
  null_handling: string;
  graph_config: GraphFeatureConfig | null;
  status: FeatureStatus;
  version: number;
  dependency_count: number;
  created_at: string;
  updated_at: string;
}

export interface FeatureDefinitionPayload {
  name: string;
  description?: string | null;
  entity: string;
  feature_name: string;
  entity_key: string;
  feature_kind?: FeatureKind;
  aggregation_type: FeatureAggregation;
  source_field?: string | null;
  window_seconds: number;
  filters?: FeatureFilter[];
  inclusion_policy?: string;
  null_handling?: string;
  graph_config?: GraphFeatureConfig | null;
}

interface FeatureListResponse {
  features: FeatureDefinition[];
}

interface FeatureMutationResponse {
  success: boolean;
  message: string;
  feature: FeatureDefinition | null;
}

@Injectable({ providedIn: 'root' })
export class FeatureService {
  private apiUrl = `${environment.apiUrl}/api/v2/features`;

  constructor(private http: HttpClient) { }

  getFeatures(): Observable<FeatureDefinition[]> {
    return this.http.get<FeatureListResponse>(this.apiUrl).pipe(map((response) => response.features));
  }

  createFeature(payload: FeatureDefinitionPayload): Observable<FeatureDefinition | null> {
    return this.http.post<FeatureMutationResponse>(this.apiUrl, payload).pipe(map((response) => response.feature));
  }

  updateFeature(featureId: number, payload: FeatureDefinitionPayload): Observable<FeatureDefinition | null> {
    return this.http.put<FeatureMutationResponse>(`${this.apiUrl}/${featureId}`, payload).pipe(map((response) => response.feature));
  }

  activateFeature(featureId: number): Observable<FeatureDefinition | null> {
    return this.http.post<FeatureMutationResponse>(`${this.apiUrl}/${featureId}/activate`, {}).pipe(map((response) => response.feature));
  }

  deprecateFeature(featureId: number): Observable<FeatureDefinition | null> {
    return this.http.post<FeatureMutationResponse>(`${this.apiUrl}/${featureId}/deprecate`, {}).pipe(map((response) => response.feature));
  }

  deleteFeature(featureId: number): Observable<FeatureDefinition | null> {
    return this.http.delete<FeatureMutationResponse>(`${this.apiUrl}/${featureId}`).pipe(map((response) => response.feature));
  }
}
