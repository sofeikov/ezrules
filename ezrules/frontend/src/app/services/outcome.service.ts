import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
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

interface OutcomeListItem {
  ao_id: number;
  outcome_name: string;
  created_at: string | null;
}

interface OutcomesListResponseV2 {
  outcomes: OutcomeListItem[];
}

interface OutcomeMutationResponseV2 {
  success: boolean;
  message: string;
  error?: string;
  outcome?: OutcomeListItem;
}

@Injectable({
  providedIn: 'root'
})
export class OutcomeService {
  private apiUrl = `${environment.apiUrl}/api/v2/outcomes`;

  constructor(private http: HttpClient) { }

  getOutcomes(): Observable<OutcomesResponse> {
    return this.http.get<OutcomesListResponseV2>(this.apiUrl).pipe(
      map(response => ({
        outcomes: response.outcomes.map(o => o.outcome_name)
      }))
    );
  }

  createOutcome(outcome: string): Observable<CreateOutcomeResponse> {
    return this.http.post<OutcomeMutationResponseV2>(this.apiUrl, { outcome_name: outcome }).pipe(
      map(response => ({
        success: response.success,
        outcome: response.outcome?.outcome_name,
        error: response.error
      }))
    );
  }

  deleteOutcome(outcome: string): Observable<DeleteOutcomeResponse> {
    return this.http.delete<OutcomeMutationResponseV2>(`${this.apiUrl}/${outcome}`).pipe(
      map(response => ({ message: response.message }))
    );
  }
}
