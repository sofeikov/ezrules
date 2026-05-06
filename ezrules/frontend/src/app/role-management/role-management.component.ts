import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../services/auth.service';
import { RoleService, RoleListItem } from '../services/role.service';
import { UserService, UserListItem } from '../services/user.service';
import {
  ACTION_PERMISSION_REQUIREMENTS,
  PermissionGrant,
  grantsFromPermissionNames,
  hasPermissionRequirement,
  permissionGrantIsCovered
} from '../auth/permissions';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-role-management',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent],
  templateUrl: './role-management.component.html'
})
export class RoleManagementComponent implements OnInit {
  roles: RoleListItem[] = [];
  users: UserListItem[] = [];

  newRoleName: string = '';
  newRoleDescription: string = '';
  assignUserId: number | null = null;
  assignRoleId: number | null = null;

  loading: boolean = true;
  error: string | null = null;
  createRoleError: string | null = null;
  editRoleError: string | null = null;
  deleteRoleError: string | null = null;
  assignError: string | null = null;
  removeRoleError: string | null = null;
  canViewUsers: boolean = false;
  canCreateRole: boolean = false;
  canModifyRole: boolean = false;
  canDeleteRole: boolean = false;
  canManageUserRoles: boolean = false;
  canManagePermissions: boolean = false;
  currentUserId: number | null = null;
  currentPermissions: string[] = [];
  currentPermissionGrants: PermissionGrant[] = [];
  editingRoleId: number | null = null;
  editRoleName: string = '';
  editRoleDescription: string = '';

  constructor(
    private roleService: RoleService,
    private userService: UserService,
    private authService: AuthService
  ) { }

  ngOnInit(): void {
    this.loadPermissions();
  }

  loadPermissions(): void {
    this.authService.getCurrentUser().subscribe({
      next: (user) => {
        this.currentUserId = user.id;
        this.currentPermissions = user.permissions;
        this.currentPermissionGrants = user.permission_grants ?? grantsFromPermissionNames(user.permissions);
        this.canViewUsers = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.viewUsers);
        this.canCreateRole = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.createRole);
        this.canModifyRole = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.modifyRole);
        this.canDeleteRole = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.deleteRole);
        this.canManageUserRoles = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.manageUserRoles);
        this.canManagePermissions = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.managePermissions);
        this.loadData();
      },
      error: () => {
        this.currentUserId = null;
        this.currentPermissions = [];
        this.currentPermissionGrants = [];
        this.canViewUsers = false;
        this.canCreateRole = false;
        this.canModifyRole = false;
        this.canDeleteRole = false;
        this.canManageUserRoles = false;
        this.canManagePermissions = false;
        this.loadData();
      }
    });
  }

  loadData(): void {
    this.loading = true;
    this.error = null;

    let rolesLoaded = false;
    let usersLoaded = false;

    const checkDone = () => {
      if (rolesLoaded && usersLoaded) {
        this.loading = false;
      }
    };

    this.roleService.getRoles().subscribe({
      next: (roles) => {
        this.roles = roles;
        rolesLoaded = true;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load roles. Please try again.';
        this.loading = false;
      }
    });

    if (!this.canViewUsers) {
      this.users = [];
      usersLoaded = true;
      checkDone();
      return;
    }

    this.userService.getUsers().subscribe({
      next: (users) => {
        this.users = users;
        usersLoaded = true;
        checkDone();
      },
      error: () => {
        this.error = 'Failed to load users. Please try again.';
        this.loading = false;
      }
    });
  }

  createRole(): void {
    if (!this.canCreateRole) return;
    if (!this.newRoleName.trim()) return;

    this.createRoleError = null;
    const description = this.newRoleDescription.trim() || undefined;

    this.roleService.createRole(this.newRoleName.trim(), description).subscribe({
      next: (response) => {
        if (response.success) {
          this.newRoleName = '';
          this.newRoleDescription = '';
          this.loadData();
        } else {
          this.createRoleError = response.error ?? 'Failed to create role.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.createRoleError = err.error?.error ?? 'Failed to create role. Please try again.';
      }
    });
  }

  deleteRole(roleId: number, roleName: string): void {
    if (!this.canDeleteRole) return;
    if (!confirm(`Are you sure you want to delete role "${roleName}"?`)) return;

    this.deleteRoleError = null;
    this.roleService.deleteRole(roleId).subscribe({
      next: (response) => {
        if (response.success) {
          this.loadData();
        } else {
          this.deleteRoleError = response.error ?? 'Failed to delete role.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.deleteRoleError = err.error?.detail ?? 'Failed to delete role. Please try again.';
      }
    });
  }

  assignRole(): void {
    if (!this.canManageUserRoles) return;
    if (!this.assignUserId || !this.assignRoleId) return;
    if (this.isCurrentUser(this.assignUserId) || !this.getAssignableRoles().some(role => role.id === this.assignRoleId)) return;

    this.assignError = null;
    this.userService.assignRole(this.assignUserId, this.assignRoleId).subscribe({
      next: (response) => {
        if (response.success) {
          this.assignUserId = null;
          this.assignRoleId = null;
          this.loadData();
        } else {
          this.assignError = response.error ?? 'Failed to assign role.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.assignError = err.error?.detail ?? 'Failed to assign role. Please try again.';
      }
    });
  }

  removeRoleFromUser(userId: number, roleId: number, roleName: string, email: string): void {
    if (!this.canManageUserRoles) return;
    if (this.isCurrentUser(userId) || !this.getAssignableRoles().some(role => role.id === roleId)) return;
    if (!confirm(`Remove role "${roleName}" from user "${email}"?`)) return;

    this.removeRoleError = null;
    this.userService.removeRole(userId, roleId).subscribe({
      next: (response) => {
        if (response.success) {
          this.loadData();
        } else {
          this.removeRoleError = response.error ?? 'Failed to remove role.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.removeRoleError = err.error?.detail ?? 'Failed to remove role. Please try again.';
      }
    });
  }

  getUsersWithRoles(): UserListItem[] {
    return this.users.filter(u => u.roles.length > 0);
  }

  getAssignableUsers(): UserListItem[] {
    return this.users.filter(user => !this.isCurrentUser(user.id));
  }

  getAssignableRoles(): RoleListItem[] {
    return this.roles.filter(role =>
      (role.permissions ?? []).every(permission => permissionGrantIsCovered(this.currentPermissionGrants, permission))
    );
  }

  isAssignableRole(roleId: number): boolean {
    return this.getAssignableRoles().some(role => role.id === roleId);
  }

  isCurrentUser(userId: number): boolean {
    return this.currentUserId === userId;
  }

  startEditRole(role: RoleListItem): void {
    if (!this.canModifyRole) return;

    this.editingRoleId = role.id;
    this.editRoleName = role.name;
    this.editRoleDescription = role.description || '';
    this.editRoleError = null;
  }

  cancelEditRole(): void {
    this.editingRoleId = null;
    this.editRoleName = '';
    this.editRoleDescription = '';
    this.editRoleError = null;
  }

  saveRoleEdit(roleId: number): void {
    if (!this.canModifyRole) return;
    if (!this.editRoleName.trim()) {
      this.editRoleError = 'Role name is required.';
      return;
    }

    this.editRoleError = null;
    this.roleService.updateRole(roleId, this.editRoleName.trim(), this.editRoleDescription.trim() || null).subscribe({
      next: (response) => {
        if (response.success) {
          this.cancelEditRole();
          this.loadData();
        } else {
          this.editRoleError = response.error ?? 'Failed to update role.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.editRoleError = err.error?.detail ?? err.error?.error ?? 'Failed to update role. Please try again.';
      }
    });
  }

  showReadOnlyNotice(): boolean {
    return (
      !this.canCreateRole &&
      !this.canModifyRole &&
      !this.canDeleteRole &&
      !this.canManageUserRoles &&
      !this.canManagePermissions
    );
  }

  permissionsLinkLabel(): string {
    return this.canManagePermissions ? 'Manage Permissions' : 'View Permissions';
  }
}
