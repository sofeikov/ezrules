import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule],
  template: `
    <div class="min-h-screen flex items-center justify-center bg-gray-100">
      <div class="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
        <div class="text-center mb-8">
          <h1 class="text-3xl font-bold text-gray-900">ezrules</h1>
          <p class="text-sm text-gray-500 mt-1">Transaction Monitoring</p>
        </div>

        <form (ngSubmit)="onSubmit()" class="space-y-6">
          <div *ngIf="demoPrefilled" class="bg-emerald-50 border border-emerald-200 text-emerald-700 px-4 py-3 rounded text-sm">
            Your demo credentials are filled in — just click <strong>Sign In</strong> to enter your sandbox.
          </div>

          <div *ngIf="error" class="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">
            {{ error }}
          </div>

          <div>
            <label for="email" class="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              id="email"
              type="email"
              [(ngModel)]="email"
              name="email"
              required
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="admin@example.com"
              [disabled]="loading"
            />
          </div>

          <div>
            <label for="password" class="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input
              id="password"
              type="password"
              [(ngModel)]="password"
              name="password"
              required
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Enter your password"
              [disabled]="loading"
            />
            <div class="mt-2 text-right">
              <a routerLink="/forgot-password" class="text-sm text-blue-600 hover:underline">Forgot password?</a>
            </div>
          </div>

          <button
            type="submit"
            [disabled]="loading || !email || !password"
            class="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <span *ngIf="!loading">Sign In</span>
            <span *ngIf="loading" class="flex items-center justify-center">
              <svg class="animate-spin h-5 w-5 mr-2" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
              Signing in...
            </span>
          </button>
        </form>
      </div>
    </div>
  `
})
export class LoginComponent implements OnInit {
  email = '';
  password = '';
  loading = false;
  error: string | null = null;
  demoPrefilled = false;

  constructor(
    private authService: AuthService,
    private router: Router,
    private route: ActivatedRoute,
  ) {}

  ngOnInit(): void {
    // Disposable-demo deep link: the landing page sends users here with
    // credentials in the URL fragment (#email=...&password=...). A fragment is
    // used instead of query params so the credentials are never sent to the
    // server or written to access logs. We prefill the form (no auto-submit —
    // the user clicks Sign In) and then strip the fragment so the credentials
    // don't linger in the address bar or browser history.
    const fragment = this.route.snapshot.fragment;
    if (!fragment) {
      return;
    }

    const params = new URLSearchParams(fragment);
    const email = params.get('email');
    const password = params.get('password');
    if (email && password) {
      this.email = email;
      this.password = password;
      this.demoPrefilled = true;
      history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }

  onSubmit(): void {
    this.loading = true;
    this.error = null;

    this.authService.login(this.email, this.password).subscribe({
      next: () => {
        this.router.navigate(['/dashboard']);
      },
      error: (err) => {
        this.loading = false;
        if (err.status === 401) {
          this.error = 'Invalid email or password.';
        } else {
          this.error = 'An error occurred. Please try again.';
        }
      }
    });
  }
}
