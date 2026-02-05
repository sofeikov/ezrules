import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface LabelsSummaryResponse {
  total_labeled: number;
}

export interface LabelDataset {
  label: string;
  data: number[];
  borderColor: string;
  backgroundColor: string;
}

export interface LabelsDistributionResponse {
  labels: string[];
  datasets: LabelDataset[];
}

interface LabelsSummaryResponseV2 {
  total_labeled: number;
  pie_chart: {
    labels: string[];
    data: number[];
    backgroundColor: string[];
  };
}

interface ChartDatasetV2 {
  label: string;
  data: number[];
  borderColor: string;
  backgroundColor: string;
  tension: number;
  fill: boolean;
}

interface LabelsDistributionResponseV2 {
  labels: string[];
  datasets: ChartDatasetV2[];
  aggregation: string;
}

@Injectable({
  providedIn: 'root'
})
export class LabelAnalyticsService {
  private apiUrl = `${environment.apiUrl}/api/v2/analytics`;

  constructor(private http: HttpClient) {}

  getSummary(): Observable<LabelsSummaryResponse> {
    return this.http.get<LabelsSummaryResponseV2>(`${this.apiUrl}/labels-summary`).pipe(
      map(response => ({
        total_labeled: response.total_labeled
      }))
    );
  }

  getDistribution(aggregation: string): Observable<LabelsDistributionResponse> {
    return this.http.get<LabelsDistributionResponseV2>(`${this.apiUrl}/labels-distribution`, {
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
