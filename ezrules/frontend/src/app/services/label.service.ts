import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

interface LabelListItem {
  el_id: number;
  label: string;
}

interface LabelsListResponse {
  labels: LabelListItem[];
}

interface LabelMutationResponse {
  success: boolean;
  message: string;
  error?: string;
  label?: LabelListItem;
}

@Injectable({
  providedIn: 'root'
})
export class LabelService {
  private apiUrl = `${environment.apiUrl}/api/v2/labels`;

  constructor(private http: HttpClient) { }

  getLabels(): Observable<string[]> {
    return this.http.get<LabelsListResponse>(this.apiUrl).pipe(
      map(response => response.labels.map(l => l.label))
    );
  }

  addLabel(labelName: string): Observable<{ response: string; failed_to_add: string[] }> {
    return this.http.post<LabelMutationResponse>(this.apiUrl, { label_name: labelName }).pipe(
      map(response => {
        if (response.success) {
          return { response: response.message, failed_to_add: [] };
        } else {
          return { response: response.message, failed_to_add: [labelName] };
        }
      })
    );
  }

  deleteLabel(labelName: string): Observable<{ message: string }> {
    return this.http.delete<LabelMutationResponse>(`${this.apiUrl}/${labelName}`).pipe(
      map(response => ({ message: response.message }))
    );
  }
}
