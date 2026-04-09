import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export type RuleStatus = 'draft' | 'active' | 'paused' | 'archived';
export type RuleEvaluationLane = 'main' | 'allowlist';

export interface Rule {
  r_id: number;
  rid: string;
  description: string;
  logic: string;
  evaluation_lane: RuleEvaluationLane;
  status: RuleStatus;
  effective_from: string | null;
  approved_by: number | null;
  approved_at: string | null;
  created_at: string | null;
  in_shadow?: boolean;
  in_rollout?: boolean;
  rollout_percent?: number | null;
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
  valid: boolean;
  params: string[];
  referenced_lists: string[];
  warnings: string[];
  errors: RuleVerifyError[];
}

export interface RuleVerifyError {
  message: string;
  line: number | null;
  column: number | null;
  end_line: number | null;
  end_column: number | null;
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
  evaluation_lane: RuleEvaluationLane;
  status: RuleStatus;
  effective_from: string | null;
  approved_by: number | null;
  approved_at: string | null;
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
  evaluation_lane?: RuleEvaluationLane;
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
  evaluation_lane?: RuleEvaluationLane;
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

export interface RolloutDeployResponse {
  success: boolean;
  message: string;
  error?: string | null;
}

export interface RolloutRuleItem {
  r_id: number;
  rid: string;
  description: string;
  logic: string;
  traffic_percent: number;
}

export interface RolloutConfigResponse {
  rules: RolloutRuleItem[];
  version: number;
}

export interface RolloutResultItem {
  dr_id: number;
  tl_id: number;
  r_id: number;
  selected_variant: string;
  traffic_percent: number | null;
  bucket: number | null;
  control_result: string | null;
  candidate_result: string | null;
  returned_result: string | null;
  event_id: string;
  event_timestamp: number;
  created_at: string | null;
}

export interface RolloutResultsResponse {
  results: RolloutResultItem[];
  total: number;
}

export interface RolloutOutcomeCount {
  outcome: string;
  count: number;
}

export interface RolloutRuleStatsItem {
  r_id: number;
  traffic_percent: number;
  total: number;
  served_candidate: number;
  served_control: number;
  candidate_outcomes: RolloutOutcomeCount[];
  control_outcomes: RolloutOutcomeCount[];
}

export interface RolloutStatsResponse {
  rules: RolloutRuleStatsItem[];
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

  rollbackRule(ruleId: number, revisionNumber: number): Observable<UpdateRuleResponse> {
    return this.http.post<UpdateRuleResponse>(`${this.apiUrl}/${ruleId}/rollback`, {
      revision_number: revisionNumber
    });
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

  deployToRollout(
    ruleId: number,
    logic: string,
    description: string,
    trafficPercent: number
  ): Observable<RolloutDeployResponse> {
    return this.http.post<RolloutDeployResponse>(`${this.apiUrl}/${ruleId}/rollout`, {
      logic,
      description,
      traffic_percent: trafficPercent
    });
  }

  removeFromRollout(ruleId: number): Observable<RolloutDeployResponse> {
    return this.http.delete<RolloutDeployResponse>(`${this.apiUrl}/${ruleId}/rollout`);
  }

  promoteRollout(ruleId: number): Observable<RolloutDeployResponse> {
    return this.http.post<RolloutDeployResponse>(`${this.apiUrl}/${ruleId}/rollout/promote`, {});
  }

  promoteRule(ruleId: number): Observable<UpdateRuleResponse> {
    return this.http.post<UpdateRuleResponse>(`${this.apiUrl}/${ruleId}/promote`, {});
  }

  pauseRule(ruleId: number): Observable<UpdateRuleResponse> {
    return this.http.post<UpdateRuleResponse>(`${this.apiUrl}/${ruleId}/pause`, {});
  }

  resumeRule(ruleId: number): Observable<UpdateRuleResponse> {
    return this.http.post<UpdateRuleResponse>(`${this.apiUrl}/${ruleId}/resume`, {});
  }

  archiveRule(ruleId: number): Observable<UpdateRuleResponse> {
    return this.http.post<UpdateRuleResponse>(`${this.apiUrl}/${ruleId}/archive`, {});
  }

  deleteRule(ruleId: number): Observable<void> {
    return this.http.delete<void>(`${this.apiUrl}/${ruleId}`);
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

  getRolloutConfig(): Observable<RolloutConfigResponse> {
    return this.http.get<RolloutConfigResponse>(`${environment.apiUrl}/api/v2/rollouts`);
  }

  getRolloutResults(limit: number = 50): Observable<RolloutResultsResponse> {
    return this.http.get<RolloutResultsResponse>(`${environment.apiUrl}/api/v2/rollouts/results`, {
      params: { limit: limit.toString() }
    });
  }

  getRolloutStats(): Observable<RolloutStatsResponse> {
    return this.http.get<RolloutStatsResponse>(`${environment.apiUrl}/api/v2/rollouts/stats`);
  }
}
