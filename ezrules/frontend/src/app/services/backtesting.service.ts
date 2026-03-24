import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface BacktestTriggerResponse {
  success: boolean;
  task_id: string;
  message: string;
  error?: string;
}

export interface BacktestResultItem {
  task_id: string;
  created_at: string | null;
  stored_logic: string | null;
  proposed_logic: string | null;
}

export interface BacktestResultsResponse {
  results: BacktestResultItem[];
}

export interface BacktestQualityMetric {
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

export interface BacktestQualitySummary {
  pair_count: number;
  average_precision: number | null;
  average_recall: number | null;
  average_f1: number | null;
  best_pair: string | null;
  worst_pair: string | null;
}

export interface BacktestTaskResult {
  status: string;
  stored_result?: Record<string, number>;
  proposed_result?: Record<string, number>;
  stored_result_rate?: Record<string, number>;
  proposed_result_rate?: Record<string, number>;
  total_records?: number;
  eligible_records?: number;
  skipped_records?: number;
  labeled_records?: number;
  label_counts?: Record<string, number>;
  stored_quality_summary?: BacktestQualitySummary | null;
  proposed_quality_summary?: BacktestQualitySummary | null;
  stored_quality_metrics?: BacktestQualityMetric[];
  proposed_quality_metrics?: BacktestQualityMetric[];
  warnings?: string[];
  error?: string;
}

@Injectable({
  providedIn: 'root'
})
export class BacktestingService {
  private apiUrl = `${environment.apiUrl}/api/v2/backtesting`;

  constructor(private http: HttpClient) { }

  private freshParams(): HttpParams {
    return new HttpParams().set('_ts', Date.now().toString());
  }

  triggerBacktest(ruleId: number, newLogic: string): Observable<BacktestTriggerResponse> {
    return this.http.post<BacktestTriggerResponse>(this.apiUrl, {
      r_id: ruleId,
      new_rule_logic: newLogic
    });
  }

  getBacktestResults(ruleId: number): Observable<BacktestResultsResponse> {
    return this.http.get<BacktestResultsResponse>(`${this.apiUrl}/${ruleId}`, {
      params: this.freshParams()
    });
  }

  getTaskResult(taskId: string): Observable<BacktestTaskResult> {
    return this.http.get<BacktestTaskResult>(`${this.apiUrl}/task/${taskId}`, {
      params: this.freshParams()
    });
  }
}
