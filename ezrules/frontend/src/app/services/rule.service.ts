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
  in_shadow?: boolean;
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

export interface RuleRevisionDetail extends RuleDetail {
  revision_number: number;
}

export interface RuleHistoryEntry {
  revision_number: number;
  logic: string;
  description: string;
  created_at: string | null;
  is_current?: boolean;
}

export interface RuleHistoryResponse {
  r_id: number;
  rid: string;
  history: RuleHistoryEntry[];
}

export interface UpdateRuleRequest {
  description: string;
  logic: string;
}

export interface UpdateRuleResponse {
  success: boolean;
  message?: string;
  error?: string;
  rule?: RuleDetail;
}

export interface CreateRuleRequest {
  rid: string;
  description: string;
  logic: string;
}

export interface CreateRuleResponse {
  success: boolean;
  message?: string;
  error?: string;
  rule?: RuleDetail;
}

export interface ShadowDeployResponse {
  success: boolean;
  message: string;
  error?: string | null;
}

export interface ShadowRuleItem {
  r_id: number;
  rid: string;
  description: string;
  logic: string;
}

export interface ShadowConfigResponse {
  rules: ShadowRuleItem[];
  version: number;
}

export interface ShadowResultItem {
  sr_id: number;
  tl_id: number;
  r_id: number;
  rule_result: string;
  event_id: string;
  event_timestamp: number;
  created_at: string | null;
}

export interface ShadowResultsResponse {
  results: ShadowResultItem[];
  total: number;
}

export interface ShadowOutcomeCount {
  outcome: string;
  count: number;
}

export interface ShadowRuleStatsItem {
  r_id: number;
  total: number;
  shadow_outcomes: ShadowOutcomeCount[];
  prod_outcomes: ShadowOutcomeCount[];
}

export interface ShadowStatsResponse {
  rules: ShadowRuleStatsItem[];
}

@Injectable({
  providedIn: 'root'
})
export class RuleService {
  private apiUrl = `${environment.apiUrl}/api/v2/rules`;

  constructor(private http: HttpClient) { }

  getRules(): Observable<RulesResponse> {
    return this.http.get<RulesResponse>(this.apiUrl);
  }

  getRule(ruleId: number): Observable<RuleDetail> {
    return this.http.get<RuleDetail>(`${this.apiUrl}/${ruleId}`);
  }

  verifyRule(ruleSource: string): Observable<VerifyRuleResponse> {
    return this.http.post<VerifyRuleResponse>(`${this.apiUrl}/verify`, {
      rule_source: ruleSource
    });
  }

  testRule(ruleSource: string, testJson: string): Observable<TestRuleResponse> {
    return this.http.post<TestRuleResponse>(`${this.apiUrl}/test`, {
      rule_source: ruleSource,
      test_json: testJson
    });
  }

  getRuleRevision(ruleId: number, revisionNumber: number): Observable<RuleRevisionDetail> {
    return this.http.get<RuleRevisionDetail>(`${this.apiUrl}/${ruleId}/revisions/${revisionNumber}`);
  }

  getRuleHistory(ruleId: number, limit: number = 10): Observable<RuleHistoryResponse> {
    return this.http.get<RuleHistoryResponse>(`${this.apiUrl}/${ruleId}/history`, { params: { limit: limit.toString() } });
  }

  updateRule(ruleId: number, data: UpdateRuleRequest): Observable<UpdateRuleResponse> {
    return this.http.put<UpdateRuleResponse>(`${this.apiUrl}/${ruleId}`, data);
  }

  createRule(data: CreateRuleRequest): Observable<CreateRuleResponse> {
    return this.http.post<CreateRuleResponse>(this.apiUrl, data);
  }

  deployToShadow(ruleId: number, logic: string, description: string): Observable<ShadowDeployResponse> {
    return this.http.post<ShadowDeployResponse>(`${this.apiUrl}/${ruleId}/shadow`, { logic, description });
  }

  removeFromShadow(ruleId: number): Observable<ShadowDeployResponse> {
    return this.http.delete<ShadowDeployResponse>(`${this.apiUrl}/${ruleId}/shadow`);
  }

  promoteFromShadow(ruleId: number): Observable<ShadowDeployResponse> {
    return this.http.post<ShadowDeployResponse>(`${this.apiUrl}/${ruleId}/shadow/promote`, {});
  }

  getShadowConfig(): Observable<ShadowConfigResponse> {
    return this.http.get<ShadowConfigResponse>(`${environment.apiUrl}/api/v2/shadow`);
  }

  getShadowResults(limit: number = 50): Observable<ShadowResultsResponse> {
    return this.http.get<ShadowResultsResponse>(`${environment.apiUrl}/api/v2/shadow/results`, {
      params: { limit: limit.toString() }
    });
  }

  getShadowStats(): Observable<ShadowStatsResponse> {
    return this.http.get<ShadowStatsResponse>(`${environment.apiUrl}/api/v2/shadow/stats`);
  }
}
