import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface OutcomesResponse {
  outcomes: OutcomeItem[];
}

export interface CreateOutcomeResponse {
  success: boolean;
  outcome?: OutcomeItem;
  error?: string;
}

export interface DeleteOutcomeResponse {
  message: string;
}

export interface OutcomeItem {
  ao_id: number;
  outcome_name: string;
  severity_rank: number;
  created_at: string | null;
}

interface OutcomesListResponseV2 {
  outcomes: OutcomeItem[];
}

interface OutcomeMutationResponseV2 {
  success: boolean;
  message: string;
  error?: string;
  outcome?: OutcomeItem;
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
        outcomes: response.outcomes.map(o => this.mapOutcome(o))
      }))
    );
  }

  createOutcome(outcome: string): Observable<CreateOutcomeResponse> {
    return this.http.post<OutcomeMutationResponseV2>(this.apiUrl, { outcome_name: outcome }).pipe(
      map(response => ({
        success: response.success,
        outcome: response.outcome ? this.mapOutcome(response.outcome) : undefined,
        error: response.error
      }))
    );
  }

  deleteOutcome(outcome: string): Observable<DeleteOutcomeResponse> {
    return this.http.delete<OutcomeMutationResponseV2>(`${this.apiUrl}/${outcome}`).pipe(
      map(response => ({ message: response.message }))
    );
  }

  private mapOutcome(outcome: OutcomeItem): OutcomeItem {
    return {
      ao_id: outcome.ao_id,
      outcome_name: outcome.outcome_name,
      severity_rank: outcome.severity_rank,
      created_at: outcome.created_at
    };
  }
}
