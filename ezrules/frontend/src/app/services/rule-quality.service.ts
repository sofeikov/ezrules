import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface RuleQualityPairMetric {
  rId: number;
  rid: string;
  description: string;
  outcome: string;
  label: string;
  truePositive: number;
  falsePositive: number;
  falseNegative: number;
  predictedPositives: number;
  actualPositives: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
}

export interface RuleQualitySummary {
  rId: number;
  rid: string;
  description: string;
  labeledEvents: number;
  pairCount: number;
  averagePrecision: number | null;
  averageRecall: number | null;
  averageF1: number | null;
  bestPair: string | null;
  worstPair: string | null;
}

export interface RuleQualityResponse {
  totalLabeledEvents: number;
  minSupport: number;
  lookbackDays: number;
  freezeAt: string;
  pairMetrics: RuleQualityPairMetric[];
  bestRules: RuleQualitySummary[];
  worstRules: RuleQualitySummary[];
}

export interface RuleQualityReportTaskResponse {
  reportId: number;
  taskId: string | null;
  status: string;
  minSupport: number;
  lookbackDays: number;
  freezeAt: string;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  cached: boolean;
  error: string | null;
  result: RuleQualityResponse | null;
}

interface RuleQualityPairMetricV2 {
  r_id: number;
  rid: string;
  description: string;
  outcome: string;
  label: string;
  true_positive: number;
  false_positive: number;
  false_negative: number;
  predicted_positives: number;
  actual_positives: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
}

interface RuleQualitySummaryV2 {
  r_id: number;
  rid: string;
  description: string;
  labeled_events: number;
  pair_count: number;
  average_precision: number | null;
  average_recall: number | null;
  average_f1: number | null;
  best_pair: string | null;
  worst_pair: string | null;
}

interface RuleQualityResponseV2 {
  total_labeled_events: number;
  min_support: number;
  lookback_days: number;
  freeze_at: string;
  pair_metrics: RuleQualityPairMetricV2[];
  best_rules: RuleQualitySummaryV2[];
  worst_rules: RuleQualitySummaryV2[];
}

interface RuleQualityReportRequestV2 {
  min_support: number;
  lookback_days?: number;
  force_refresh: boolean;
}

interface RuleQualityReportTaskResponseV2 {
  report_id: number;
  task_id: string | null;
  status: string;
  min_support: number;
  lookback_days: number;
  freeze_at: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  cached: boolean;
  error: string | null;
  result: RuleQualityResponseV2 | null;
}

@Injectable({
  providedIn: 'root'
})
export class RuleQualityService {
  private analyticsUrl = `${environment.apiUrl}/api/v2/analytics`;

  constructor(private http: HttpClient) {}

  private mapRuleQualityResponse(response: RuleQualityResponseV2): RuleQualityResponse {
    return {
      totalLabeledEvents: response.total_labeled_events,
      minSupport: response.min_support,
      lookbackDays: response.lookback_days,
      freezeAt: response.freeze_at,
      pairMetrics: response.pair_metrics.map(metric => ({
        rId: metric.r_id,
        rid: metric.rid,
        description: metric.description,
        outcome: metric.outcome,
        label: metric.label,
        truePositive: metric.true_positive,
        falsePositive: metric.false_positive,
        falseNegative: metric.false_negative,
        predictedPositives: metric.predicted_positives,
        actualPositives: metric.actual_positives,
        precision: metric.precision,
        recall: metric.recall,
        f1: metric.f1
      })),
      bestRules: response.best_rules.map(rule => ({
        rId: rule.r_id,
        rid: rule.rid,
        description: rule.description,
        labeledEvents: rule.labeled_events,
        pairCount: rule.pair_count,
        averagePrecision: rule.average_precision,
        averageRecall: rule.average_recall,
        averageF1: rule.average_f1,
        bestPair: rule.best_pair,
        worstPair: rule.worst_pair
      })),
      worstRules: response.worst_rules.map(rule => ({
        rId: rule.r_id,
        rid: rule.rid,
        description: rule.description,
        labeledEvents: rule.labeled_events,
        pairCount: rule.pair_count,
        averagePrecision: rule.average_precision,
        averageRecall: rule.average_recall,
        averageF1: rule.average_f1,
        bestPair: rule.best_pair,
        worstPair: rule.worst_pair
      }))
    };
  }

  getRuleQuality(minSupport: number, lookbackDays: number | null = null): Observable<RuleQualityResponse> {
    const params: Record<string, string> = { min_support: String(minSupport) };
    if (lookbackDays !== null) {
      params['lookback_days'] = String(lookbackDays);
    }

    return this.http.get<RuleQualityResponseV2>(`${this.analyticsUrl}/rule-quality`, { params }).pipe(
      map(response => this.mapRuleQualityResponse(response))
    );
  }

  requestRuleQualityReport(
    minSupport: number,
    lookbackDays: number | null = null,
    forceRefresh: boolean = false
  ): Observable<RuleQualityReportTaskResponse> {
    const payload: RuleQualityReportRequestV2 = {
      min_support: minSupport,
      force_refresh: forceRefresh
    };
    if (lookbackDays !== null) {
      payload.lookback_days = lookbackDays;
    }

    return this.http.post<RuleQualityReportTaskResponseV2>(
      `${this.analyticsUrl}/rule-quality/reports`,
      payload
    ).pipe(
      map(report => ({
        reportId: report.report_id,
        taskId: report.task_id,
        status: report.status,
        minSupport: report.min_support,
        lookbackDays: report.lookback_days,
        freezeAt: report.freeze_at,
        createdAt: report.created_at,
        startedAt: report.started_at,
        completedAt: report.completed_at,
        cached: report.cached,
        error: report.error,
        result: report.result ? this.mapRuleQualityResponse(report.result) : null
      }))
    );
  }

  getRuleQualityReport(reportId: number): Observable<RuleQualityReportTaskResponse> {
    return this.http.get<RuleQualityReportTaskResponseV2>(
      `${this.analyticsUrl}/rule-quality/reports/${reportId}`
    ).pipe(
      map(report => ({
        reportId: report.report_id,
        taskId: report.task_id,
        status: report.status,
        minSupport: report.min_support,
        lookbackDays: report.lookback_days,
        freezeAt: report.freeze_at,
        createdAt: report.created_at,
        startedAt: report.started_at,
        completedAt: report.completed_at,
        cached: report.cached,
        error: report.error,
        result: report.result ? this.mapRuleQualityResponse(report.result) : null
      }))
    );
  }
}
