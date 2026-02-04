import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class LabelService {
  private apiUrl = `${environment.apiUrl}/labels`;
  private apiDeleteUrl = `${environment.apiUrl}/api/labels`;

  constructor(private http: HttpClient) { }

  getLabels(): Observable<string[]> {
    return this.http.get<string[]>(this.apiUrl);
  }

  addLabel(labelName: string): Observable<{ response: string; failed_to_add: string[] }> {
    return this.http.post<{ response: string; failed_to_add: string[] }>(this.apiUrl, { label_name: labelName });
  }

  deleteLabel(labelName: string): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.apiDeleteUrl}/${labelName}`);
  }
}
