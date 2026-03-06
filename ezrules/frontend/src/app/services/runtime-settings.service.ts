import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface RuntimeSettings {
  ruleQualityLookbackDays: number;
  defaultRuleQualityLookbackDays: number;
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

interface RuntimeSettingsV2 {
  rule_quality_lookback_days: number;
  default_rule_quality_lookback_days: number;
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

@Injectable({
  providedIn: 'root'
})
export class RuntimeSettingsService {
  private settingsUrl = `${environment.apiUrl}/api/v2/settings/runtime`;
  private ruleQualityPairsUrl = `${environment.apiUrl}/api/v2/settings/rule-quality-pairs`;

  constructor(private http: HttpClient) {}

  getRuntimeSettings(): Observable<RuntimeSettings> {
    return this.http.get<RuntimeSettingsV2>(this.settingsUrl).pipe(
      map(response => ({
        ruleQualityLookbackDays: response.rule_quality_lookback_days,
        defaultRuleQualityLookbackDays: response.default_rule_quality_lookback_days
      }))
    );
  }

  updateRuntimeSettings(ruleQualityLookbackDays: number): Observable<RuntimeSettings> {
    return this.http.put<RuntimeSettingsV2>(this.settingsUrl, {
      rule_quality_lookback_days: ruleQualityLookbackDays
    }).pipe(
      map(response => ({
        ruleQualityLookbackDays: response.rule_quality_lookback_days,
        defaultRuleQualityLookbackDays: response.default_rule_quality_lookback_days
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
}
