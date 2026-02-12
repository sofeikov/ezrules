import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
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

export interface BacktestTaskResult {
  status: string;
  stored_result?: Record<string, number>;
  proposed_result?: Record<string, number>;
  stored_result_rate?: Record<string, number>;
  proposed_result_rate?: Record<string, number>;
  total_records?: number;
  error?: string;
}

@Injectable({
  providedIn: 'root'
})
export class BacktestingService {
  private apiUrl = `${environment.apiUrl}/api/v2/backtesting`;

  constructor(private http: HttpClient) { }

  triggerBacktest(ruleId: number, newLogic: string): Observable<BacktestTriggerResponse> {
    return this.http.post<BacktestTriggerResponse>(this.apiUrl, {
      r_id: ruleId,
      new_rule_logic: newLogic
    });
  }

  getBacktestResults(ruleId: number): Observable<BacktestResultsResponse> {
    return this.http.get<BacktestResultsResponse>(`${this.apiUrl}/${ruleId}`);
  }

  getTaskResult(taskId: string): Observable<BacktestTaskResult> {
    return this.http.get<BacktestTaskResult>(`${this.apiUrl}/task/${taskId}`);
  }
}
