import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface UserListEntry {
  id: number;
  value: string;
  created_at: string | null;
}

export interface UserListItem {
  id: number;
  name: string;
  entry_count: number;
  created_at: string | null;
}

export interface UserListDetail {
  id: number;
  name: string;
  entry_count: number;
  created_at: string | null;
  entries: UserListEntry[];
}

interface UserListsListResponse {
  lists: UserListItem[];
}

interface UserListMutationResponse {
  success: boolean;
  message: string;
  list?: UserListItem;
  error?: string;
}

interface UserListEntryMutationResponse {
  success: boolean;
  message: string;
  entry?: UserListEntry;
  error?: string;
}

@Injectable({
  providedIn: 'root'
})
export class UserListService {
  private apiUrl = `${environment.apiUrl}/api/v2/user-lists`;

  constructor(private http: HttpClient) { }

  getUserLists(): Observable<UserListItem[]> {
    return this.http.get<UserListsListResponse>(this.apiUrl).pipe(
      map(response => response.lists)
    );
  }

  createUserList(name: string): Observable<UserListMutationResponse> {
    return this.http.post<UserListMutationResponse>(this.apiUrl, { name });
  }

  deleteUserList(listId: number): Observable<UserListMutationResponse> {
    return this.http.delete<UserListMutationResponse>(`${this.apiUrl}/${listId}`);
  }

  getUserListDetail(listId: number): Observable<UserListDetail> {
    return this.http.get<UserListDetail>(`${this.apiUrl}/${listId}`);
  }

  addEntry(listId: number, value: string): Observable<UserListEntryMutationResponse> {
    return this.http.post<UserListEntryMutationResponse>(
      `${this.apiUrl}/${listId}/entries`,
      { value }
    );
  }

  deleteEntry(listId: number, entryId: number): Observable<UserListEntryMutationResponse> {
    return this.http.delete<UserListEntryMutationResponse>(
      `${this.apiUrl}/${listId}/entries/${entryId}`
    );
  }
}
