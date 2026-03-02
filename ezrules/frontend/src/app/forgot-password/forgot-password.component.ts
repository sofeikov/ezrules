import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-forgot-password',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  template: `
    <div class="min-h-screen flex items-center justify-center bg-gray-100 p-4">
      <div class="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
        <h1 class="text-2xl font-bold text-gray-900 mb-2">Forgot Password</h1>
        <p class="text-sm text-gray-600 mb-6">Enter your email and we will send a reset link.</p>

        <div *ngIf="message" class="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded text-sm mb-4">
          {{ message }}
        </div>

        <div *ngIf="error" class="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm mb-4">
          {{ error }}
        </div>

        <form (ngSubmit)="onSubmit()" class="space-y-4">
          <div>
            <label for="email" class="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              id="email"
              type="email"
              [(ngModel)]="email"
              name="email"
              required
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              [disabled]="loading"
            />
          </div>
          <button
            type="submit"
            [disabled]="loading || !email"
            class="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {{ loading ? 'Sending...' : 'Send Reset Link' }}
          </button>
        </form>

        <div class="mt-4 text-sm">
          <a routerLink="/login" class="text-blue-600 hover:underline">Back to sign in</a>
        </div>
      </div>
    </div>
  `
})
export class ForgotPasswordComponent {
  email = '';
  loading = false;
  message: string | null = null;
  error: string | null = null;

  constructor(private authService: AuthService) {}

  onSubmit(): void {
    this.loading = true;
    this.error = null;
    this.message = null;

    this.authService.forgotPassword(this.email.trim()).subscribe({
      next: (response) => {
        this.loading = false;
        this.message = response.message;
      },
      error: () => {
        this.loading = false;
        this.error = 'Unable to process request right now.';
      }
    });
  }
}
