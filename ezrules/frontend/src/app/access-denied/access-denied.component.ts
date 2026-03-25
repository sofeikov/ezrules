import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { describePermissions } from '../auth/permissions';
import { SidebarComponent } from '../components/sidebar.component';

@Component({
  selector: 'app-access-denied',
  standalone: true,
  imports: [CommonModule, RouterModule, SidebarComponent],
  template: `
    <div class="flex min-h-screen bg-gray-50">
      <app-sidebar></app-sidebar>

      <div class="ml-64 flex-1">
        <div class="p-8 max-w-3xl">
          <div class="bg-white border border-amber-200 rounded-lg shadow-sm p-8">
            <div class="flex items-start gap-4">
              <div class="w-12 h-12 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
                <svg class="w-6 h-6 text-amber-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>

              <div class="min-w-0">
                <h1 class="text-2xl font-bold text-gray-900">Access denied</h1>
                <p class="mt-2 text-sm text-gray-600">
                  This page is hidden for your current role set because your account does not have the required permission.
                </p>

                <div *ngIf="requestedPath" class="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
                  <p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Requested path</p>
                  <p class="mt-1 text-sm font-mono text-gray-800">{{ requestedPath }}</p>
                </div>

                <div *ngIf="requiredAll.length > 0 || requiredAny.length > 0" class="mt-4 space-y-3">
                  <div *ngIf="requiredAll.length > 0" class="rounded-lg border border-gray-200 p-4">
                    <p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Required permissions</p>
                    <ul class="mt-2 flex flex-wrap gap-2">
                      <li
                        *ngFor="let permission of requiredAll"
                        class="inline-flex items-center rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700"
                      >
                        {{ permission }}
                      </li>
                    </ul>
                  </div>

                  <div *ngIf="requiredAny.length > 0" class="rounded-lg border border-gray-200 p-4">
                    <p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Any of these permissions would grant access</p>
                    <ul class="mt-2 flex flex-wrap gap-2">
                      <li
                        *ngFor="let permission of requiredAny"
                        class="inline-flex items-center rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700"
                      >
                        {{ permission }}
                      </li>
                    </ul>
                  </div>
                </div>

                <div class="mt-6 flex items-center gap-3">
                  <a
                    routerLink="/dashboard"
                    class="px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition-colors text-sm font-medium"
                  >
                    Go to dashboard
                  </a>
                  <a
                    routerLink="/rules"
                    class="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium"
                  >
                    Go to rules
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
})
export class AccessDeniedComponent implements OnInit {
  requestedPath: string | null = null;
  requiredAll: string[] = [];
  requiredAny: string[] = [];

  constructor(private route: ActivatedRoute) {}

  ngOnInit(): void {
    this.route.queryParamMap.subscribe((params) => {
      this.requestedPath = params.get('from');
      this.requiredAll = describePermissions((params.get('all') ?? '').split(',').filter(Boolean));
      this.requiredAny = describePermissions((params.get('any') ?? '').split(',').filter(Boolean));
    });
  }
}
