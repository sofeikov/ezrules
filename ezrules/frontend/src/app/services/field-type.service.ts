import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface FieldTypeConfig {
  field_name: string;
  configured_type: string;
  datetime_format: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface FieldObservation {
  field_name: string;
  observed_json_type: string;
  occurrence_count: number;
  last_seen: string | null;
}

interface FieldTypeConfigListResponse {
  configs: FieldTypeConfig[];
}

interface FieldObservationListResponse {
  observations: FieldObservation[];
}

interface FieldTypeMutationResponse {
  success: boolean;
  message: string;
  error?: string;
  config?: FieldTypeConfig;
}

@Injectable({ providedIn: 'root' })
export class FieldTypeService {
  private apiUrl = `${environment.apiUrl}/api/v2/field-types`;

  constructor(private http: HttpClient) {}

  getConfigs(): Observable<FieldTypeConfig[]> {
    return this.http
      .get<FieldTypeConfigListResponse>(this.apiUrl)
      .pipe(map(r => r.configs));
  }

  getObservations(): Observable<FieldObservation[]> {
    return this.http
      .get<FieldObservationListResponse>(`${this.apiUrl}/observations`)
      .pipe(map(r => r.observations));
  }

  upsertConfig(
    field_name: string,
    configured_type: string,
    datetime_format: string | null
  ): Observable<FieldTypeMutationResponse> {
    return this.http.post<FieldTypeMutationResponse>(this.apiUrl, {
      field_name,
      configured_type,
      datetime_format: datetime_format || null,
    });
  }

  deleteConfig(field_name: string): Observable<FieldTypeMutationResponse> {
    return this.http.delete<FieldTypeMutationResponse>(`${this.apiUrl}/${field_name}`);
  }
}
