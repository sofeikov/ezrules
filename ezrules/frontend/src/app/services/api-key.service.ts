import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface ApiKeyItem {
  gid: string;
  label: string;
  created_at: string;
  revoked_at: string | null;
}

export interface CreateApiKeyResponse extends ApiKeyItem {
  raw_key: string;
}

@Injectable({
  providedIn: 'root'
})
export class ApiKeyService {
  private apiUrl = `${environment.apiUrl}/api/v2/api-keys`;

  constructor(private http: HttpClient) {}

  list(): Observable<ApiKeyItem[]> {
    return this.http.get<ApiKeyItem[]>(this.apiUrl);
  }

  create(label: string): Observable<CreateApiKeyResponse> {
    return this.http.post<CreateApiKeyResponse>(this.apiUrl, { label });
  }

  revoke(gid: string): Observable<void> {
    return this.http.delete<void>(`${this.apiUrl}/${gid}`);
  }
}
