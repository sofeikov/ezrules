import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export type FeatureStatus = 'draft' | 'active' | 'deprecated';
export type FeatureAggregation = 'count' | 'count_distinct' | 'sum' | 'avg' | 'min' | 'max' | 'stddev' | 'days_since_first_seen';

export interface FeatureFilter {
  field: string;
  operator: 'eq' | 'in';
  value: unknown;
}

export interface FeatureDefinition {
  fd_id: number;
  name: string;
  description: string | null;
  entity: string;
  feature_name: string;
  available_as: string;
  entity_key: string;
  event_time_field: string | null;
  aggregation_type: FeatureAggregation;
  source_field: string | null;
  window_seconds: number;
  window_label: string;
  filters: FeatureFilter[];
  inclusion_policy: string;
  null_handling: string;
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
  event_time_field?: string | null;
  aggregation_type: FeatureAggregation;
  source_field?: string | null;
  window_seconds: number;
  filters?: FeatureFilter[];
  inclusion_policy?: string;
  null_handling?: string;
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
