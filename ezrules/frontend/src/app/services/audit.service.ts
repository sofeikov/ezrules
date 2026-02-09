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
}

export interface ConfigHistoryEntry {
  re_id: number;
  label: string;
  version: number;
  config: unknown;
  changed: string | null;
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
}
