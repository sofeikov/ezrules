import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { PermissionRequirement, ROUTE_PERMISSION_REQUIREMENTS, hasPermissionRequirement } from '../auth/permissions';
import { NotificationBellComponent } from './notification-bell.component';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, NotificationBellComponent],
  template: `
    <div class="w-64 bg-gray-900 text-white h-screen fixed left-0 top-0 flex flex-col">
      <div class="p-6">
        <h2 class="text-xl font-bold">ezrules</h2>
        <p class="text-xs text-gray-400 mt-1">Transaction Monitoring</p>
      </div>

      <nav class="mt-6 flex-1 overflow-y-auto">
        <a *ngIf="canAccess(routePermissions.dashboard)" href="/dashboard" [ngClass]="linkClasses('/dashboard')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
          </svg>
          <span>Dashboard</span>
        </a>

        <a *ngIf="canAccess(routePermissions.rules)" href="/rules" [ngClass]="linkClasses('/rules')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span>Rules</span>
        </a>

        <a *ngIf="canAccess(routePermissions.shadowRules)" href="/shadow-rules" [ngClass]="linkClasses('/shadow-rules')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
          <span>Shadow Rules</span>
        </a>

        <a *ngIf="canAccess(routePermissions.rollouts)" href="/rule-rollouts" [ngClass]="linkClasses('/rule-rollouts')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span>Rule Rollouts</span>
        </a>

        <a *ngIf="canAccess(routePermissions.labels)" href="/labels" [ngClass]="linkClasses('/labels')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5a2 2 0 012 2v13a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2zm7.75 4.25a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
          </svg>
          <span>Labels</span>
        </a>

        <a *ngIf="canAccess(routePermissions.outcomes)" href="/outcomes" [ngClass]="linkClasses('/outcomes')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          <span>Outcomes</span>
        </a>

        <a *ngIf="canAccess(routePermissions.testedEvents)" href="/tested-events" [ngClass]="linkClasses('/tested-events')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10m-11 9h12a2 2 0 002-2V7a2 2 0 00-2-2H6a2 2 0 00-2 2v11a2 2 0 002 2z" />
          </svg>
          <span>Tested Events</span>
        </a>

        <a *ngIf="canAccess(routePermissions.eventTester)" href="/event-tester" [ngClass]="linkClasses('/event-tester')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5a3 3 0 006 0M9 13l2 2 4-4" />
          </svg>
          <span>Event Tester</span>
        </a>

        <a *ngIf="canAccess(routePermissions.userLists)" href="/user-lists" [ngClass]="linkClasses('/user-lists')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
          </svg>
          <span>User Lists</span>
        </a>

        <a *ngIf="canAccess(routePermissions.labelAnalytics)" href="/label_analytics" [ngClass]="linkClasses('/label_analytics')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <span>Analytics</span>
        </a>

        <a *ngIf="canAccess(routePermissions.ruleQuality)" href="/rule-quality" [ngClass]="linkClasses('/rule-quality')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17v-2a4 4 0 014-4h8" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 3v18h18" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 13l4-4 3 3 5-5" />
          </svg>
          <span>Rule Quality</span>
        </a>

        <a *ngIf="canAccess(routePermissions.audit)" href="/audit" [ngClass]="linkClasses('/audit')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>Audit Trail</span>
        </a>

        <a *ngIf="canAccess(routePermissions.alerts)" href="/alerts" [ngClass]="linkClasses('/alerts')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 9v2m0 4h.01M5.07 19h13.86a2 2 0 001.74-2.99L13.74 4a2 2 0 00-3.48 0L3.33 16.01A2 2 0 005.07 19z" />
          </svg>
          <span>Alerts</span>
        </a>

        <a *ngIf="canAccess(routePermissions.users)" href="/management/users" [ngClass]="linkClasses('/management/users')">
          <svg class="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <span>Security</span>
        </a>

        <!-- Settings section -->
        <div *ngIf="showSettingsSection()" class="mt-2">
          <p class="px-6 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">Settings</p>

          <a *ngIf="canAccess(routePermissions.settings)" href="/settings" [ngClass]="subLinkClasses('/settings')">
            <svg class="w-4 h-4 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 16v-2m8-6h-2M6 12H4m12.364 5.364l-1.414-1.414M9.05 9.05 7.636 7.636m8.728 0L14.95 9.05m-5.9 5.9-1.414 1.414" />
            </svg>
            <span>General</span>
          </a>

          <a *ngIf="canAccess(routePermissions.roles)" href="/role_management" [ngClass]="subLinkClasses('/role_management')">
            <svg class="w-4 h-4 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <span>Role Management</span>
          </a>

          <a *ngIf="canAccess(routePermissions.fieldTypes)" href="/field-types" [ngClass]="subLinkClasses('/field-types')">
            <svg class="w-4 h-4 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 13h4M10 17h2" />
            </svg>
            <span>Field Types</span>
          </a>

          <a *ngIf="canAccess(routePermissions.apiKeys)" href="/api-keys" [ngClass]="subLinkClasses('/api-keys')">
            <svg class="w-4 h-4 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
            <span>API Keys</span>
          </a>
        </div>
      </nav>

      <div class="p-4 border-t border-gray-700 flex-shrink-0">
        <div class="mb-2 flex items-center justify-between gap-3">
          <p class="truncate text-xs text-gray-400">{{ userEmail }}</p>
          <app-notification-bell *ngIf="canAccess(routePermissions.alerts)"></app-notification-bell>
        </div>
        <button
          (click)="onLogout()"
          class="flex items-center text-gray-300 hover:text-white transition-colors text-sm"
        >
          <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          Sign Out
        </button>
      </div>
    </div>
  `
})
export class SidebarComponent implements OnInit {
  userEmail = '';
  permissions: string[] = [];
  readonly routePermissions = ROUTE_PERMISSION_REQUIREMENTS;

  constructor(private router: Router, private authService: AuthService) {}

  ngOnInit(): void {
    this.authService.getCurrentUser().subscribe({
      next: (user) => {
        this.userEmail = user.email;
        this.permissions = user.permissions;
      },
      error: () => {
        this.userEmail = '';
        this.permissions = [];
      }
    });
  }

  onLogout(): void {
    this.authService.logout();
  }

  linkClasses(path: string): Record<string, boolean> {
    const isActive = this.router.url === path || this.router.url.startsWith(path + '/');
    return {
      'flex items-center px-6 py-3': true,
      'bg-gray-800 text-white border-l-4 border-blue-500': isActive,
      'text-gray-300 hover:bg-gray-800 hover:text-white transition-colors': !isActive
    };
  }

  subLinkClasses(path: string): Record<string, boolean> {
    const isActive = this.router.url === path || this.router.url.startsWith(path + '/');
    return {
      'flex items-center pl-10 pr-6 py-2 text-sm': true,
      'bg-gray-800 text-white border-l-4 border-blue-500': isActive,
      'text-gray-400 hover:bg-gray-800 hover:text-white transition-colors': !isActive
    };
  }

  canAccess(requirement?: PermissionRequirement): boolean {
    return hasPermissionRequirement(this.permissions, requirement);
  }

  showSettingsSection(): boolean {
    return (
      this.canAccess(this.routePermissions.settings) ||
      this.canAccess(this.routePermissions.roles) ||
      this.canAccess(this.routePermissions.fieldTypes) ||
      this.canAccess(this.routePermissions.apiKeys)
    );
  }
}
