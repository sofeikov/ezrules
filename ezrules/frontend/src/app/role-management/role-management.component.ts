import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../services/auth.service';
import { RoleService, RoleListItem } from '../services/role.service';
import { UserService, UserListItem } from '../services/user.service';
import { ACTION_PERMISSION_REQUIREMENTS, hasPermissionRequirement } from '../auth/permissions';
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
  deleteRoleError: string | null = null;
  assignError: string | null = null;
  removeRoleError: string | null = null;
  canViewUsers: boolean = false;
  canCreateRole: boolean = false;
  canDeleteRole: boolean = false;
  canManageUserRoles: boolean = false;
  canManagePermissions: boolean = false;

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
        this.canViewUsers = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.viewUsers);
        this.canCreateRole = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.createRole);
        this.canDeleteRole = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.deleteRole);
        this.canManageUserRoles = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.manageUserRoles);
        this.canManagePermissions = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.managePermissions);
        this.loadData();
      },
      error: () => {
        this.canViewUsers = false;
        this.canCreateRole = false;
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
    if (!this.assignUserId || !this.assignRoleId) return;

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

  showReadOnlyNotice(): boolean {
    return !this.canCreateRole && !this.canDeleteRole && !this.canManageUserRoles && !this.canManagePermissions;
  }

  permissionsLinkLabel(): string {
    return this.canManagePermissions ? 'Manage Permissions' : 'View Permissions';
  }
}
