import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface PermissionItem {
  id: number;
  name: string;
  description: string | null;
  resource_type: string | null;
}

export interface RoleListItem {
  id: number;
  name: string;
  description: string | null;
  user_count: number;
}

export interface RoleDetail {
  id: number;
  name: string;
  description: string | null;
  user_count: number;
  permissions: PermissionItem[];
}

export interface RoleMutationResponse {
  success: boolean;
  message: string;
  role?: RoleDetail;
  error?: string;
}

export interface RolePermissionsResponse {
  success: boolean;
  message: string;
  role?: RoleDetail;
  error?: string;
}

interface RolesListResponse {
  roles: RoleListItem[];
}

interface PermissionsListResponse {
  permissions: PermissionItem[];
}

@Injectable({
  providedIn: 'root'
})
export class RoleService {
  private rolesUrl = `${environment.apiUrl}/api/v2/roles`;

  constructor(private http: HttpClient) { }

  getRoles(): Observable<RoleListItem[]> {
    return this.http.get<RolesListResponse>(this.rolesUrl).pipe(
      map(response => response.roles)
    );
  }

  getRole(roleId: number): Observable<RoleDetail> {
    return this.http.get<RoleDetail>(`${this.rolesUrl}/${roleId}`);
  }

  createRole(name: string, description?: string): Observable<RoleMutationResponse> {
    const body: { name: string; description?: string } = { name };
    if (description) {
      body.description = description;
    }
    return this.http.post<RoleMutationResponse>(this.rolesUrl, body);
  }

  deleteRole(roleId: number): Observable<RoleMutationResponse> {
    return this.http.delete<RoleMutationResponse>(`${this.rolesUrl}/${roleId}`);
  }

  getAllPermissions(): Observable<PermissionItem[]> {
    return this.http.get<PermissionsListResponse>(`${this.rolesUrl}/permissions`).pipe(
      map(response => response.permissions)
    );
  }

  getRolePermissions(roleId: number): Observable<RolePermissionsResponse> {
    return this.http.get<RolePermissionsResponse>(`${this.rolesUrl}/${roleId}/permissions`);
  }

  updateRolePermissions(roleId: number, permissionIds: number[]): Observable<RolePermissionsResponse> {
    return this.http.put<RolePermissionsResponse>(`${this.rolesUrl}/${roleId}/permissions`, {
      permission_ids: permissionIds
    });
  }
}
