import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { UserService, UserListItem, RoleListItem } from '../services/user.service';
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

  loading: boolean = true;
  error: string | null = null;
  createError: string | null = null;
  actionError: string | null = null;

  constructor(private userService: UserService) { }

  ngOnInit(): void {
    this.loadUsers();
    this.loadRoles();
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
}
