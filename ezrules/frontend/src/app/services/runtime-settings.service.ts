import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface RuntimeSettings {
  autoPromoteActiveRuleUpdates: boolean;
  defaultAutoPromoteActiveRuleUpdates: boolean;
  strictModeEnabled: boolean;
  defaultStrictModeEnabled: boolean;
  mainRuleExecutionMode: string;
  defaultMainRuleExecutionMode: string;
  ruleQualityLookbackDays: number;
  defaultRuleQualityLookbackDays: number;
  neutralOutcome: string;
  defaultNeutralOutcome: string;
  invalidAllowlistRules: InvalidAllowlistRule[];
}

export interface AIAuthoringSettings {
  provider: string;
  supportedProviders: string[];
  enabled: boolean;
  model: string;
  apiKeyConfigured: boolean;
}

export interface InvalidAllowlistRule {
  rId: number;
  rid: string;
  description: string;
  error: string;
}

export interface RuleQualityPair {
  rqpId: number;
  outcome: string;
  label: string;
  active: boolean;
  createdAt: string;
  updatedAt: string;
  createdBy: string | null;
}

export interface RuleQualityPairOptions {
  outcomes: string[];
  labels: string[];
}

export interface OutcomeHierarchyItem {
  aoId: number;
  outcomeName: string;
  severityRank: number;
}

export interface RuntimeSettingsUpdateRequest {
  autoPromoteActiveRuleUpdates?: boolean;
  strictModeEnabled?: boolean;
  mainRuleExecutionMode?: string;
  ruleQualityLookbackDays?: number;
  neutralOutcome?: string;
}

export interface AIAuthoringSettingsUpdateRequest {
  provider?: string;
  enabled?: boolean;
  model?: string;
  apiKey?: string | null;
  clearApiKey?: boolean;
}

interface RuntimeSettingsV2 {
  auto_promote_active_rule_updates: boolean;
  default_auto_promote_active_rule_updates: boolean;
  strict_mode_enabled: boolean;
  default_strict_mode_enabled: boolean;
  main_rule_execution_mode: string;
  default_main_rule_execution_mode: string;
  rule_quality_lookback_days: number;
  default_rule_quality_lookback_days: number;
  neutral_outcome: string;
  default_neutral_outcome: string;
  invalid_allowlist_rules: InvalidAllowlistRuleV2[];
}

interface AIAuthoringSettingsV2 {
  provider: string;
  supported_providers: string[];
  enabled: boolean;
  model: string;
  api_key_configured: boolean;
}

interface InvalidAllowlistRuleV2 {
  r_id: number;
  rid: string;
  description: string;
  error: string;
}

interface RuleQualityPairV2 {
  rqp_id: number;
  outcome: string;
  label: string;
  active: boolean;
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

interface RuleQualityPairsListResponseV2 {
  pairs: RuleQualityPairV2[];
}

interface RuleQualityPairOptionsResponseV2 {
  outcomes: string[];
  labels: string[];
}

interface OutcomeHierarchyItemV2 {
  ao_id: number;
  outcome_name: string;
  severity_rank: number;
}

interface OutcomeHierarchyResponseV2 {
  outcomes: OutcomeHierarchyItemV2[];
}

@Injectable({
  providedIn: 'root'
})
export class RuntimeSettingsService {
  private settingsUrl = `${environment.apiUrl}/api/v2/settings/runtime`;
  private aiAuthoringSettingsUrl = `${environment.apiUrl}/api/v2/settings/ai-authoring`;
  private ruleQualityPairsUrl = `${environment.apiUrl}/api/v2/settings/rule-quality-pairs`;
  private outcomeHierarchyUrl = `${environment.apiUrl}/api/v2/settings/outcome-hierarchy`;

  constructor(private http: HttpClient) {}

  getRuntimeSettings(): Observable<RuntimeSettings> {
    return this.http.get<RuntimeSettingsV2>(this.settingsUrl).pipe(
      map(response => this.mapRuntimeSettings(response))
    );
  }

  updateRuntimeSettings(request: RuntimeSettingsUpdateRequest): Observable<RuntimeSettings> {
    return this.http.put<RuntimeSettingsV2>(this.settingsUrl, {
      auto_promote_active_rule_updates: request.autoPromoteActiveRuleUpdates,
      strict_mode_enabled: request.strictModeEnabled,
      main_rule_execution_mode: request.mainRuleExecutionMode,
      rule_quality_lookback_days: request.ruleQualityLookbackDays,
      neutral_outcome: request.neutralOutcome,
    }).pipe(
      map(response => this.mapRuntimeSettings(response))
    );
  }

  getAIAuthoringSettings(): Observable<AIAuthoringSettings> {
    return this.http.get<AIAuthoringSettingsV2>(this.aiAuthoringSettingsUrl).pipe(
      map(response => ({
        provider: response.provider,
        supportedProviders: response.supported_providers,
        enabled: response.enabled,
        model: response.model,
        apiKeyConfigured: response.api_key_configured,
      }))
    );
  }

  updateAIAuthoringSettings(request: AIAuthoringSettingsUpdateRequest): Observable<AIAuthoringSettings> {
    return this.http.put<AIAuthoringSettingsV2>(this.aiAuthoringSettingsUrl, {
      provider: request.provider,
      enabled: request.enabled,
      model: request.model,
      api_key: request.apiKey,
      clear_api_key: request.clearApiKey,
    }).pipe(
      map(response => ({
        provider: response.provider,
        supportedProviders: response.supported_providers,
        enabled: response.enabled,
        model: response.model,
        apiKeyConfigured: response.api_key_configured,
      }))
    );
  }

  getRuleQualityPairs(): Observable<RuleQualityPair[]> {
    return this.http.get<RuleQualityPairsListResponseV2>(this.ruleQualityPairsUrl).pipe(
      map(response => response.pairs.map(pair => this.mapRuleQualityPair(pair)))
    );
  }

  getRuleQualityPairOptions(): Observable<RuleQualityPairOptions> {
    return this.http.get<RuleQualityPairOptionsResponseV2>(`${this.ruleQualityPairsUrl}/options`).pipe(
      map(response => ({
        outcomes: response.outcomes,
        labels: response.labels
      }))
    );
  }

  createRuleQualityPair(outcome: string, label: string): Observable<RuleQualityPair> {
    return this.http.post<RuleQualityPairV2>(this.ruleQualityPairsUrl, {
      outcome,
      label
    }).pipe(
      map(pair => this.mapRuleQualityPair(pair))
    );
  }

  updateRuleQualityPair(pairId: number, active: boolean): Observable<RuleQualityPair> {
    return this.http.put<RuleQualityPairV2>(`${this.ruleQualityPairsUrl}/${pairId}`, {
      active
    }).pipe(
      map(pair => this.mapRuleQualityPair(pair))
    );
  }

  deleteRuleQualityPair(pairId: number): Observable<void> {
    return this.http.delete<void>(`${this.ruleQualityPairsUrl}/${pairId}`);
  }

  getOutcomeHierarchy(): Observable<OutcomeHierarchyItem[]> {
    return this.http.get<OutcomeHierarchyResponseV2>(this.outcomeHierarchyUrl).pipe(
      map(response => response.outcomes.map(item => this.mapOutcomeHierarchyItem(item)))
    );
  }

  updateOutcomeHierarchy(orderedAoIds: number[]): Observable<OutcomeHierarchyItem[]> {
    return this.http.put<OutcomeHierarchyResponseV2>(this.outcomeHierarchyUrl, {
      ordered_ao_ids: orderedAoIds
    }).pipe(
      map(response => response.outcomes.map(item => this.mapOutcomeHierarchyItem(item)))
    );
  }

  private mapRuleQualityPair(pair: RuleQualityPairV2): RuleQualityPair {
    return {
      rqpId: pair.rqp_id,
      outcome: pair.outcome,
      label: pair.label,
      active: pair.active,
      createdAt: pair.created_at,
      updatedAt: pair.updated_at,
      createdBy: pair.created_by
    };
  }

  private mapOutcomeHierarchyItem(item: OutcomeHierarchyItemV2): OutcomeHierarchyItem {
    return {
      aoId: item.ao_id,
      outcomeName: item.outcome_name,
      severityRank: item.severity_rank
    };
  }

  private mapInvalidAllowlistRule(rule: InvalidAllowlistRuleV2): InvalidAllowlistRule {
    return {
      rId: rule.r_id,
      rid: rule.rid,
      description: rule.description,
      error: rule.error,
    };
  }

  private mapRuntimeSettings(response: RuntimeSettingsV2): RuntimeSettings {
    return {
      autoPromoteActiveRuleUpdates: response.auto_promote_active_rule_updates,
      defaultAutoPromoteActiveRuleUpdates: response.default_auto_promote_active_rule_updates,
      strictModeEnabled: response.strict_mode_enabled,
      defaultStrictModeEnabled: response.default_strict_mode_enabled,
      mainRuleExecutionMode: response.main_rule_execution_mode,
      defaultMainRuleExecutionMode: response.default_main_rule_execution_mode,
      ruleQualityLookbackDays: response.rule_quality_lookback_days,
      defaultRuleQualityLookbackDays: response.default_rule_quality_lookback_days,
      neutralOutcome: response.neutral_outcome,
      defaultNeutralOutcome: response.default_neutral_outcome,
      invalidAllowlistRules: response.invalid_allowlist_rules.map((rule) => this.mapInvalidAllowlistRule(rule)),
    };
  }
}
