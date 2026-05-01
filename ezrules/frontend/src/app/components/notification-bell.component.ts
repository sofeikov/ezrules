import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { AlertService, InAppNotification } from '../services/alert.service';

@Component({
  selector: 'app-notification-bell',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="relative">
      <button
        type="button"
        class="relative flex h-9 w-9 items-center justify-center rounded-md text-gray-300 hover:bg-gray-800 hover:text-white"
        aria-label="Notifications"
        data-testid="notification-bell"
        (click)="toggleOpen()"
      >
        <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 10-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        <span
          *ngIf="unreadCount > 0"
          class="absolute -right-1 -top-1 min-w-5 rounded-full bg-red-600 px-1.5 py-0.5 text-center text-xs font-semibold text-white"
          data-testid="notification-unread-count"
        >
          {{ unreadCount > 99 ? '99+' : unreadCount }}
        </span>
      </button>

      <div
        *ngIf="open"
        class="absolute bottom-11 left-0 z-50 w-80 overflow-hidden rounded-md border border-gray-200 bg-white text-gray-900 shadow-xl"
        data-testid="notification-menu"
      >
        <div class="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h3 class="text-sm font-semibold">Notifications</h3>
          <button
            *ngIf="unreadCount > 0"
            type="button"
            class="text-xs font-medium text-blue-700 hover:text-blue-900"
            (click)="markAllRead()"
          >
            Mark all read
          </button>
        </div>

        <div *ngIf="loading" class="px-4 py-4 text-sm text-gray-500">Loading...</div>
        <div *ngIf="!loading && notifications.length === 0" class="px-4 py-4 text-sm text-gray-500">
          No notifications.
        </div>

        <button
          *ngFor="let notification of notifications"
          type="button"
          class="block w-full border-b border-gray-100 px-4 py-3 text-left hover:bg-gray-50"
          [class.bg-red-50]="!notification.read_at && notification.severity === 'critical'"
          (click)="openNotification(notification)"
        >
          <div class="flex items-start justify-between gap-3">
            <p class="text-sm font-semibold text-gray-900">{{ notification.title }}</p>
            <span
              *ngIf="!notification.read_at"
              class="mt-1 h-2 w-2 flex-shrink-0 rounded-full bg-red-600"
              aria-label="Unread"
            ></span>
          </div>
          <p class="mt-1 text-xs text-gray-600">{{ notification.body }}</p>
        </button>
      </div>
    </div>
  `
})
export class NotificationBellComponent implements OnInit {
  unreadCount = 0;
  notifications: InAppNotification[] = [];
  loading = false;
  open = false;

  constructor(private alertService: AlertService, private router: Router) {}

  ngOnInit(): void {
    this.loadUnreadCount();
  }

  toggleOpen(): void {
    this.open = !this.open;
    if (this.open) {
      this.loadNotifications();
    }
  }

  loadUnreadCount(): void {
    this.alertService.getUnreadCount().subscribe({
      next: (response) => {
        this.unreadCount = response.unread_count;
      },
      error: () => {
        this.unreadCount = 0;
      }
    });
  }

  loadNotifications(): void {
    this.loading = true;
    this.alertService.getNotifications(false, 10).subscribe({
      next: (response) => {
        this.notifications = response.notifications;
        this.loading = false;
      },
      error: () => {
        this.notifications = [];
        this.loading = false;
      }
    });
  }

  markAllRead(): void {
    this.alertService.markAllNotificationsRead().subscribe({
      next: (response) => {
        this.unreadCount = response.unread_count;
        this.loadNotifications();
      }
    });
  }

  openNotification(notification: InAppNotification): void {
    const navigate = () => {
      this.open = false;
      if (notification.action_url) {
        this.router.navigateByUrl(notification.action_url);
      }
    };

    if (notification.read_at) {
      navigate();
      return;
    }

    this.alertService.markNotificationRead(notification.id).subscribe({
      next: (response) => {
        this.unreadCount = response.unread_count;
        navigate();
      },
      error: () => navigate()
    });
  }
}
