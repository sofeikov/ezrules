import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { RoleService, PermissionItem } from '../services/role.service';
import { SidebarComponent } from '../components/sidebar.component';

interface PermissionGroup {
  resourceType: string;
  permissions: PermissionItem[];
}

@Component({
  selector: 'app-role-permissions',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent],
  templateUrl: './role-permissions.component.html'
})
export class RolePermissionsComponent implements OnInit {
  roleId: number = 0;
  roleName: string = '';
  allPermissions: PermissionItem[] = [];
  permissionGroups: PermissionGroup[] = [];
  selectedPermissionIds: Set<number> = new Set();

  loading: boolean = true;
  saving: boolean = false;
  error: string | null = null;
  saveError: string | null = null;
  saveSuccess: boolean = false;

  constructor(
    private route: ActivatedRoute,
    private roleService: RoleService
  ) { }

  ngOnInit(): void {
    this.roleId = Number(this.route.snapshot.paramMap.get('id'));
    this.loadData();
  }

  loadData(): void {
    this.loading = true;
    this.error = null;

    let permissionsLoaded = false;
    let roleLoaded = false;

    const checkDone = () => {
      if (permissionsLoaded && roleLoaded) {
        this.buildPermissionGroups();
        this.loading = false;
      }
    };

    this.roleService.getAllPermissions().subscribe({
      next: (permissions) => {
        this.allPermissions = permissions;
        permissionsLoaded = true;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load permissions. Please try again.';
        this.loading = false;
      }
    });

    this.roleService.getRolePermissions(this.roleId).subscribe({
      next: (response) => {
        if (response.role) {
          this.roleName = response.role.name;
          this.selectedPermissionIds = new Set(
            response.role.permissions.map(p => p.id)
          );
        }
        roleLoaded = true;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load role details. Please try again.';
        this.loading = false;
      }
    });
  }

  buildPermissionGroups(): void {
    const groupMap = new Map<string, PermissionItem[]>();

    for (const perm of this.allPermissions) {
      const key = perm.resource_type ?? 'Other';
      if (!groupMap.has(key)) {
        groupMap.set(key, []);
      }
      groupMap.get(key)!.push(perm);
    }

    this.permissionGroups = Array.from(groupMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([resourceType, permissions]) => ({
        resourceType,
        permissions: permissions.sort((a, b) => a.name.localeCompare(b.name))
      }));
  }

  isPermissionSelected(permId: number): boolean {
    return this.selectedPermissionIds.has(permId);
  }

  togglePermission(permId: number): void {
    if (this.selectedPermissionIds.has(permId)) {
      this.selectedPermissionIds.delete(permId);
    } else {
      this.selectedPermissionIds.add(permId);
    }
    this.saveSuccess = false;
  }

  getSelectedPermissions(): PermissionItem[] {
    return this.allPermissions.filter(p => this.selectedPermissionIds.has(p.id));
  }

  formatPermissionName(name: string): string {
    return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  savePermissions(): void {
    this.saving = true;
    this.saveError = null;
    this.saveSuccess = false;

    const permissionIds = Array.from(this.selectedPermissionIds);

    this.roleService.updateRolePermissions(this.roleId, permissionIds).subscribe({
      next: (response) => {
        if (response.success) {
          this.saveSuccess = true;
          if (response.role) {
            this.selectedPermissionIds = new Set(
              response.role.permissions.map(p => p.id)
            );
          }
        } else {
          this.saveError = response.error ?? 'Failed to save permissions.';
        }
        this.saving = false;
      },
      error: (err: HttpErrorResponse) => {
        this.saveError = err.error?.detail ?? 'Failed to save permissions. Please try again.';
        this.saving = false;
      }
    });
  }
}
