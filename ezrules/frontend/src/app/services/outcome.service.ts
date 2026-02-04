import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface OutcomesResponse {
  outcomes: string[];
}

export interface CreateOutcomeResponse {
  success: boolean;
  outcome?: string;
  error?: string;
}

export interface DeleteOutcomeResponse {
  message: string;
}

@Injectable({
  providedIn: 'root'
})
export class OutcomeService {
  private apiUrl = `${environment.apiUrl}/api/outcomes`;

  constructor(private http: HttpClient) { }

  getOutcomes(): Observable<OutcomesResponse> {
    return this.http.get<OutcomesResponse>(this.apiUrl);
  }

  createOutcome(outcome: string): Observable<CreateOutcomeResponse> {
    return this.http.post<CreateOutcomeResponse>(this.apiUrl, { outcome });
  }

  deleteOutcome(outcome: string): Observable<DeleteOutcomeResponse> {
    return this.http.delete<DeleteOutcomeResponse>(`${this.apiUrl}/${outcome}`);
  }
}
