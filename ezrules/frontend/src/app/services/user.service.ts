import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface UserRole {
  id: number;
  name: string;
  description: string | null;
}

export interface UserListItem {
  id: number;
  email: string;
  active: boolean;
  roles: UserRole[];
}

export interface UserResponse {
  id: number;
  email: string;
  active: boolean;
  roles: UserRole[];
  last_login_at: string | null;
  current_login_at: string | null;
}

export interface UserMutationResponse {
  success: boolean;
  message: string;
  user?: UserResponse;
  error?: string;
}

export interface RoleAssignmentResponse {
  success: boolean;
  message: string;
  user?: UserResponse;
  error?: string;
}

export interface RoleListItem {
  id: number;
  name: string;
  description: string | null;
  user_count: number;
}

interface UsersListResponse {
  users: UserListItem[];
}

interface RolesListResponse {
  roles: RoleListItem[];
}

@Injectable({
  providedIn: 'root'
})
export class UserService {
  private usersUrl = `${environment.apiUrl}/api/v2/users`;
  private rolesUrl = `${environment.apiUrl}/api/v2/roles`;

  constructor(private http: HttpClient) { }

  getUsers(): Observable<UserListItem[]> {
    return this.http.get<UsersListResponse>(this.usersUrl).pipe(
      map(response => response.users)
    );
  }

  createUser(email: string, password: string, roleIds?: number[]): Observable<UserMutationResponse> {
    const body: { email: string; password: string; role_ids?: number[] } = { email, password };
    if (roleIds && roleIds.length > 0) {
      body.role_ids = roleIds;
    }
    return this.http.post<UserMutationResponse>(this.usersUrl, body);
  }

  updateUser(userId: number, data: { email?: string; password?: string; active?: boolean }): Observable<UserMutationResponse> {
    return this.http.put<UserMutationResponse>(`${this.usersUrl}/${userId}`, data);
  }

  deleteUser(userId: number): Observable<UserMutationResponse> {
    return this.http.delete<UserMutationResponse>(`${this.usersUrl}/${userId}`);
  }

  assignRole(userId: number, roleId: number): Observable<RoleAssignmentResponse> {
    return this.http.post<RoleAssignmentResponse>(`${this.usersUrl}/${userId}/roles`, { role_id: roleId });
  }

  removeRole(userId: number, roleId: number): Observable<RoleAssignmentResponse> {
    return this.http.delete<RoleAssignmentResponse>(`${this.usersUrl}/${userId}/roles/${roleId}`);
  }

  getRoles(): Observable<RoleListItem[]> {
    return this.http.get<RolesListResponse>(this.rolesUrl).pipe(
      map(response => response.roles)
    );
  }
}
