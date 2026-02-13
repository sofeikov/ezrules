import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface ChartDataset {
  label: string;
  data: number[];
  borderColor: string;
  backgroundColor: string;
}

export interface TimeSeriesResponse {
  labels: string[];
  data: number[];
}

export interface MultiSeriesResponse {
  labels: string[];
  datasets: ChartDataset[];
}

interface TimeSeriesResponseV2 {
  labels: string[];
  data: number[];
  aggregation: string;
}

interface ChartDatasetV2 {
  label: string;
  data: number[];
  borderColor: string;
  backgroundColor: string;
  tension: number;
  fill: boolean;
}

interface MultiSeriesResponseV2 {
  labels: string[];
  datasets: ChartDatasetV2[];
  aggregation: string;
}

interface RulesListResponseV2 {
  rules: { r_id: number }[];
  evaluator_endpoint: string;
}

@Injectable({
  providedIn: 'root'
})
export class DashboardService {
  private analyticsUrl = `${environment.apiUrl}/api/v2/analytics`;
  private rulesUrl = `${environment.apiUrl}/api/v2/rules`;

  constructor(private http: HttpClient) {}

  getActiveRulesCount(): Observable<number> {
    return this.http.get<RulesListResponseV2>(this.rulesUrl).pipe(
      map(response => response.rules.length)
    );
  }

  getTransactionVolume(aggregation: string): Observable<TimeSeriesResponse> {
    return this.http.get<TimeSeriesResponseV2>(`${this.analyticsUrl}/transaction-volume`, {
      params: { aggregation }
    }).pipe(
      map(response => ({
        labels: response.labels,
        data: response.data
      }))
    );
  }

  getOutcomesDistribution(aggregation: string): Observable<MultiSeriesResponse> {
    return this.http.get<MultiSeriesResponseV2>(`${this.analyticsUrl}/outcomes-distribution`, {
      params: { aggregation }
    }).pipe(
      map(response => ({
        labels: response.labels,
        datasets: response.datasets.map(ds => ({
          label: ds.label,
          data: ds.data,
          borderColor: ds.borderColor,
          backgroundColor: ds.backgroundColor
        }))
      }))
    );
  }
}
