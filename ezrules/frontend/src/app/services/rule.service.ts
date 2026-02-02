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

export interface RuleRevision {
  revision_number: number;
  created_at: string | null;
}

export interface RuleDetail extends Rule {
  revisions: RuleRevision[];
}

export interface RulesResponse {
  rules: Rule[];
  evaluator_endpoint: string;
}

export interface VerifyRuleResponse {
  params: string[];
}

export interface TestRuleResponse {
  rule_outcome: any;
  status: string;
  reason: string;
}

@Injectable({
  providedIn: 'root'
})
export class RuleService {
  private apiUrl = `${environment.apiUrl}/api/rules`;
  private baseUrl = environment.apiUrl;

  constructor(private http: HttpClient) { }

  getRules(): Observable<RulesResponse> {
    return this.http.get<RulesResponse>(this.apiUrl);
  }

  getRule(ruleId: number): Observable<RuleDetail> {
    return this.http.get<RuleDetail>(`${this.apiUrl}/${ruleId}`);
  }

  verifyRule(ruleSource: string): Observable<VerifyRuleResponse> {
    return this.http.post<VerifyRuleResponse>(`${this.baseUrl}/verify_rule`, {
      rule_source: ruleSource
    });
  }

  testRule(ruleSource: string, testJson: string): Observable<TestRuleResponse> {
    return this.http.post<TestRuleResponse>(`${this.baseUrl}/test_rule`, {
      rule_source: ruleSource,
      test_json: testJson
    });
  }
}
