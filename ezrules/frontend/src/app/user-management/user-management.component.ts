import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../services/auth.service';
import { UserService, UserListItem, RoleListItem } from '../services/user.service';
import { ACTION_PERMISSION_REQUIREMENTS, hasPermissionRequirement } from '../auth/permissions';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-user-management',
  standalone: true,
  imports: [CommonModule, FormsModule, SidebarComponent],
  templateUrl: './user-management.component.html'
})
export class UserManagementComponent implements OnInit {
  users: UserListItem[] = [];
  roles: RoleListItem[] = [];

  newEmail: string = '';
  newPassword: string = '';
  selectedRoleId: number | null = null;
  inviteEmail: string = '';
  inviteRoleId: number | null = null;

  loading: boolean = true;
  error: string | null = null;
  createError: string | null = null;
  inviteError: string | null = null;
  inviteMessage: string | null = null;
  actionError: string | null = null;

  canViewRoles: boolean = false;
  canCreateUser: boolean = false;
  canModifyUser: boolean = false;
  canDeleteUser: boolean = false;
  canManageUserRoles: boolean = false;

  constructor(private userService: UserService, private authService: AuthService) { }

  ngOnInit(): void {
    this.loadPermissions();
    this.loadUsers();
  }

  loadPermissions(): void {
    this.authService.getCurrentUser().subscribe({
      next: (user) => {
        this.canViewRoles = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.viewRoles);
        this.canCreateUser = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.createUser);
        this.canModifyUser = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.modifyUser);
        this.canDeleteUser = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.deleteUser);
        this.canManageUserRoles = hasPermissionRequirement(user.permissions, ACTION_PERMISSION_REQUIREMENTS.manageUserRoles);

        if (this.canViewRoles) {
          this.loadRoles();
        }
      },
      error: () => {
        this.canViewRoles = false;
        this.canCreateUser = false;
        this.canModifyUser = false;
        this.canDeleteUser = false;
        this.canManageUserRoles = false;
      }
    });
  }

  loadUsers(): void {
    this.loading = true;
    this.error = null;

    this.userService.getUsers().subscribe({
      next: (users) => {
        this.users = users;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load users. Please try again.';
        this.loading = false;
      }
    });
  }

  loadRoles(): void {
    this.userService.getRoles().subscribe({
      next: (roles) => {
        this.roles = roles;
      },
      error: () => {
        // Non-critical - role dropdown just won't populate
      }
    });
  }

  createUser(): void {
    if (!this.newEmail.trim() || !this.newPassword.trim()) return;

    this.createError = null;
    this.inviteMessage = null;
    const roleIds = this.selectedRoleId ? [this.selectedRoleId] : undefined;

    this.userService.createUser(this.newEmail.trim(), this.newPassword, roleIds).subscribe({
      next: (response) => {
        if (response.success) {
          this.newEmail = '';
          this.newPassword = '';
          this.selectedRoleId = null;
          this.loadUsers();
        } else {
          this.createError = response.error ?? 'Failed to create user.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.createError = err.error?.error ?? 'Failed to create user. Please try again.';
      }
    });
  }

  inviteUser(): void {
    if (!this.inviteEmail.trim()) return;

    this.inviteError = null;
    this.inviteMessage = null;
    const roleIds = this.inviteRoleId ? [this.inviteRoleId] : undefined;

    this.userService.inviteUser(this.inviteEmail.trim(), roleIds).subscribe({
      next: (response) => {
        if (response.success) {
          this.inviteMessage = response.message;
          this.inviteEmail = '';
          this.inviteRoleId = null;
          this.loadUsers();
        } else {
          this.inviteError = response.error ?? 'Failed to send invitation.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.inviteError = err.error?.detail ?? 'Failed to send invitation. Please try again.';
      }
    });
  }

  deleteUser(userId: number, email: string): void {
    if (!confirm(`Are you sure you want to delete user "${email}"?`)) return;

    this.actionError = null;
    this.userService.deleteUser(userId).subscribe({
      next: (response) => {
        if (response.success) {
          this.loadUsers();
        } else {
          this.actionError = response.error ?? 'Failed to delete user.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.actionError = err.error?.detail ?? 'Failed to delete user. Please try again.';
      }
    });
  }

  toggleActive(user: UserListItem): void {
    const newStatus = !user.active;
    const action = newStatus ? 'activate' : 'deactivate';
    if (!confirm(`Are you sure you want to ${action} user "${user.email}"?`)) return;

    this.actionError = null;
    this.userService.updateUser(user.id, { active: newStatus }).subscribe({
      next: (response) => {
        if (response.success) {
          this.loadUsers();
        } else {
          this.actionError = response.error ?? `Failed to ${action} user.`;
        }
      },
      error: (err: HttpErrorResponse) => {
        this.actionError = err.error?.detail ?? `Failed to ${action} user. Please try again.`;
      }
    });
  }

  resetPassword(userId: number, email: string): void {
    const newPassword = prompt(`Enter new password for "${email}" (min 6 characters):`);
    if (!newPassword || newPassword.length < 6) {
      if (newPassword !== null) {
        this.actionError = 'Password must be at least 6 characters.';
      }
      return;
    }

    this.actionError = null;
    this.userService.updateUser(userId, { password: newPassword }).subscribe({
      next: (response) => {
        if (response.success) {
          alert('Password updated successfully.');
        } else {
          this.actionError = response.error ?? 'Failed to reset password.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.actionError = err.error?.detail ?? 'Failed to reset password. Please try again.';
      }
    });
  }

  assignRole(userId: number, event: Event): void {
    const select = event.target as HTMLSelectElement;
    const roleId = parseInt(select.value, 10);
    if (isNaN(roleId)) return;

    this.actionError = null;
    this.userService.assignRole(userId, roleId).subscribe({
      next: (response) => {
        if (response.success) {
          this.loadUsers();
        } else {
          this.actionError = response.error ?? 'Failed to assign role.';
        }
        select.value = '';
      },
      error: (err: HttpErrorResponse) => {
        this.actionError = err.error?.detail ?? 'Failed to assign role. Please try again.';
        select.value = '';
      }
    });
  }

  removeRole(userId: number, roleId: number, roleName: string, email: string): void {
    if (!confirm(`Remove role "${roleName}" from user "${email}"?`)) return;

    this.actionError = null;
    this.userService.removeRole(userId, roleId).subscribe({
      next: (response) => {
        if (response.success) {
          this.loadUsers();
        } else {
          this.actionError = response.error ?? 'Failed to remove role.';
        }
      },
      error: (err: HttpErrorResponse) => {
        this.actionError = err.error?.detail ?? 'Failed to remove role. Please try again.';
      }
    });
  }

  getAvailableRoles(user: UserListItem): RoleListItem[] {
    const assignedIds = new Set(user.roles.map(r => r.id));
    return this.roles.filter(r => !assignedIds.has(r.id));
  }

  showReadOnlyNotice(): boolean {
    return !this.canCreateUser && !this.canModifyUser && !this.canDeleteUser && !this.canManageUserRoles;
  }
}
