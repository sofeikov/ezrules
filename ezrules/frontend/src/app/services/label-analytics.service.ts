import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
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

@Injectable({
  providedIn: 'root'
})
export class LabelAnalyticsService {
  private baseUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  getSummary(): Observable<LabelsSummaryResponse> {
    return this.http.get<LabelsSummaryResponse>(`${this.baseUrl}/api/labels_summary`);
  }

  getDistribution(aggregation: string): Observable<LabelsDistributionResponse> {
    return this.http.get<LabelsDistributionResponse>(`${this.baseUrl}/api/labels_distribution`, {
      params: { aggregation }
    });
  }
}
