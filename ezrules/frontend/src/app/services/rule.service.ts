import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface Rule {
  r_id: number;
  rid: string;
  description: string;
  logic: string;
  created_at: string | null;
}

export interface RulesResponse {
  rules: Rule[];
  evaluator_endpoint: string;
}

@Injectable({
  providedIn: 'root'
})
export class RuleService {
  private apiUrl = `${environment.apiUrl}/api/rules`;

  constructor(private http: HttpClient) { }

  getRules(): Observable<RulesResponse> {
    return this.http.get<RulesResponse>(this.apiUrl);
  }
}
