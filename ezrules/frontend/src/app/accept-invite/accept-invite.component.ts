import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-accept-invite',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  template: `
    <div class="min-h-screen flex items-center justify-center bg-gray-100 p-4">
      <div class="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
        <h1 class="text-2xl font-bold text-gray-900 mb-2">Accept Invitation</h1>
        <p class="text-sm text-gray-600 mb-6">Set your password to activate your account.</p>

        <div *ngIf="error" class="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm mb-4">
          {{ error }}
        </div>
        <div *ngIf="success" class="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded text-sm mb-4">
          {{ success }}
        </div>

        <form (ngSubmit)="onSubmit()" class="space-y-4" *ngIf="!success">
          <div>
            <label for="password" class="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input
              id="password"
              type="password"
              [(ngModel)]="password"
              name="password"
              required
              minlength="6"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              [disabled]="loading"
            />
          </div>
          <div>
            <label for="confirmPassword" class="block text-sm font-medium text-gray-700 mb-1">Confirm Password</label>
            <input
              id="confirmPassword"
              type="password"
              [(ngModel)]="confirmPassword"
              name="confirmPassword"
              required
              minlength="6"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              [disabled]="loading"
            />
          </div>
          <button
            type="submit"
            [disabled]="loading || !password || !confirmPassword"
            class="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {{ loading ? 'Submitting...' : 'Accept Invitation' }}
          </button>
        </form>

        <div class="mt-4 text-sm">
          <a routerLink="/login" class="text-blue-600 hover:underline">Back to sign in</a>
        </div>
      </div>
    </div>
  `
})
export class AcceptInviteComponent implements OnInit {
  token = '';
  password = '';
  confirmPassword = '';
  loading = false;
  error: string | null = null;
  success: string | null = null;

  constructor(
    private authService: AuthService,
    private route: ActivatedRoute,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.token = this.route.snapshot.queryParamMap.get('token') ?? '';
    if (!this.token) {
      this.error = 'Missing invitation token.';
    }
  }

  onSubmit(): void {
    if (!this.token) {
      this.error = 'Missing invitation token.';
      return;
    }
    if (this.password.length < 6) {
      this.error = 'Password must be at least 6 characters.';
      return;
    }
    if (this.password !== this.confirmPassword) {
      this.error = 'Passwords do not match.';
      return;
    }

    this.loading = true;
    this.error = null;
    this.authService.acceptInvite(this.token, this.password).subscribe({
      next: (response) => {
        this.loading = false;
        this.success = response.message;
        setTimeout(() => this.router.navigate(['/login']), 1200);
      },
      error: (err) => {
        this.loading = false;
        this.error = err.error?.detail ?? 'Failed to accept invitation.';
      }
    });
  }
}
