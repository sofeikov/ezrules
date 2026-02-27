import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface RuleHistoryEntry {
  r_id: number;
  rid: string;
  version: number;
  logic: string;
  description: string;
  changed: string | null;
  changed_by: string | null;
}

export interface ConfigHistoryEntry {
  re_id: number;
  label: string;
  version: number;
  config: unknown;
  changed: string | null;
  changed_by: string | null;
}

export interface UserListHistoryEntry {
  id: number;
  ul_id: number;
  list_name: string;
  action: string;
  details: string | null;
  changed: string | null;
  changed_by: string | null;
}

export interface OutcomeHistoryEntry {
  id: number;
  ao_id: number;
  outcome_name: string;
  action: string;
  changed: string | null;
  changed_by: string | null;
}

export interface LabelHistoryEntry {
  id: number;
  el_id: number;
  label: string;
  action: string;
  changed: string | null;
  changed_by: string | null;
}

export interface RulesAuditListResponse {
  total: number;
  items: RuleHistoryEntry[];
  limit: number;
  offset: number;
}

export interface ConfigAuditListResponse {
  total: number;
  items: ConfigHistoryEntry[];
  limit: number;
  offset: number;
}

export interface UserListAuditListResponse {
  total: number;
  items: UserListHistoryEntry[];
  limit: number;
  offset: number;
}

export interface OutcomeAuditListResponse {
  total: number;
  items: OutcomeHistoryEntry[];
  limit: number;
  offset: number;
}

export interface LabelAuditListResponse {
  total: number;
  items: LabelHistoryEntry[];
  limit: number;
  offset: number;
}

export interface UserAccountHistoryEntry {
  id: number;
  user_id: number;
  user_email: string;
  action: string;
  details: string | null;
  changed: string | null;
  changed_by: string | null;
}

export interface UserAccountAuditListResponse {
  total: number;
  items: UserAccountHistoryEntry[];
  limit: number;
  offset: number;
}

export interface RolePermissionHistoryEntry {
  id: number;
  role_id: number;
  role_name: string;
  action: string;
  details: string | null;
  changed: string | null;
  changed_by: string | null;
}

export interface RolePermissionAuditListResponse {
  total: number;
  items: RolePermissionHistoryEntry[];
  limit: number;
  offset: number;
}

export interface FieldTypeHistoryEntry {
  id: number;
  field_name: string;
  configured_type: string;
  datetime_format: string | null;
  action: string;
  details: string | null;
  changed: string | null;
  changed_by: string | null;
}

export interface FieldTypeAuditListResponse {
  total: number;
  items: FieldTypeHistoryEntry[];
  limit: number;
  offset: number;
}

export interface ApiKeyHistoryEntry {
  id: number;
  api_key_gid: string;
  label: string;
  action: string;
  changed: string | null;
  changed_by: string | null;
}

export interface ApiKeyAuditListResponse {
  total: number;
  items: ApiKeyHistoryEntry[];
  limit: number;
  offset: number;
}

@Injectable({ providedIn: 'root' })
export class AuditService {
  private auditUrl = `${environment.apiUrl}/api/v2/audit`;

  constructor(private http: HttpClient) {}

  getRuleHistory(limit: number = 100, offset: number = 0): Observable<RulesAuditListResponse> {
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString());
    return this.http.get<RulesAuditListResponse>(`${this.auditUrl}/rules`, { params });
  }

  getConfigHistory(limit: number = 100, offset: number = 0): Observable<ConfigAuditListResponse> {
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString());
    return this.http.get<ConfigAuditListResponse>(`${this.auditUrl}/config`, { params });
  }

  getUserListHistory(limit: number = 100, offset: number = 0): Observable<UserListAuditListResponse> {
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString());
    return this.http.get<UserListAuditListResponse>(`${this.auditUrl}/user-lists`, { params });
  }

  getOutcomeHistory(limit: number = 100, offset: number = 0): Observable<OutcomeAuditListResponse> {
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString());
    return this.http.get<OutcomeAuditListResponse>(`${this.auditUrl}/outcomes`, { params });
  }

  getLabelHistory(limit: number = 100, offset: number = 0): Observable<LabelAuditListResponse> {
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString());
    return this.http.get<LabelAuditListResponse>(`${this.auditUrl}/labels`, { params });
  }

  getUserAccountHistory(limit: number = 100, offset: number = 0): Observable<UserAccountAuditListResponse> {
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString());
    return this.http.get<UserAccountAuditListResponse>(`${this.auditUrl}/users`, { params });
  }

  getRolePermissionHistory(limit: number = 100, offset: number = 0): Observable<RolePermissionAuditListResponse> {
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString());
    return this.http.get<RolePermissionAuditListResponse>(`${this.auditUrl}/roles`, { params });
  }

  getFieldTypeHistory(limit: number = 100, offset: number = 0): Observable<FieldTypeAuditListResponse> {
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString());
    return this.http.get<FieldTypeAuditListResponse>(`${this.auditUrl}/field-types`, { params });
  }

  getApiKeyHistory(limit: number = 100, offset: number = 0): Observable<ApiKeyAuditListResponse> {
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString());
    return this.http.get<ApiKeyAuditListResponse>(`${this.auditUrl}/api-keys`, { params });
  }
}
