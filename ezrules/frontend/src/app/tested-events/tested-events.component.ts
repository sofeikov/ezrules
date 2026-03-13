import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { SidebarComponent } from '../components/sidebar.component';
import { TestedEvent, TestedEventService } from '../services/tested-event.service';

@Component({
  selector: 'app-tested-events',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, SidebarComponent],
  templateUrl: './tested-events.component.html'
})
export class TestedEventsComponent implements OnInit {
  events: TestedEvent[] = [];
  total: number = 0;
  limit: number = 50;
  loading: boolean = true;
  refreshing: boolean = false;
  error: string | null = null;
  hasLoadedOnce: boolean = false;
  expandedEventIds = new Set<number>();
  readonly limitOptions = [25, 50, 100, 200];

  constructor(private testedEventService: TestedEventService) {}

  ngOnInit(): void {
    this.loadEvents();
  }

  loadEvents(): void {
    if (this.hasLoadedOnce) {
      this.refreshing = true;
    } else {
      this.loading = true;
    }
    this.error = null;

    this.testedEventService.getTestedEvents(this.limit).subscribe({
      next: (response) => {
        this.events = response.events;
        this.total = response.total;
        this.loading = false;
        this.refreshing = false;
        this.hasLoadedOnce = true;
        this.expandedEventIds = new Set(
          [...this.expandedEventIds].filter((eventId) => this.events.some((event) => event.tl_id === eventId))
        );
      },
      error: () => {
        this.error = 'Failed to load tested events. Please try again.';
        this.loading = false;
        this.refreshing = false;
      }
    });
  }

  onLimitChange(): void {
    this.loadEvents();
  }

  refreshEvents(): void {
    if (this.loading || this.refreshing) {
      return;
    }
    this.loadEvents();
  }

  toggleDetails(eventId: number): void {
    if (this.expandedEventIds.has(eventId)) {
      this.expandedEventIds.delete(eventId);
      return;
    }
    this.expandedEventIds.add(eventId);
  }

  isExpanded(eventId: number): boolean {
    return this.expandedEventIds.has(eventId);
  }

  matchedEventCount(): number {
    return this.events.filter((event) => event.triggered_rules.length > 0).length;
  }

  unmatchedEventCount(): number {
    return this.events.filter((event) => event.triggered_rules.length === 0).length;
  }

  formatTimestamp(timestamp: number): string {
    return new Date(timestamp * 1000).toLocaleString();
  }

  outcomeBadgeClass(outcome: string | null): string {
    if (outcome === 'CANCEL') {
      return 'bg-red-100 text-red-800';
    }
    if (outcome === 'HOLD') {
      return 'bg-amber-100 text-amber-800';
    }
    if (outcome === 'RELEASE') {
      return 'bg-green-100 text-green-800';
    }
    return 'bg-gray-200 text-gray-700';
  }

  eventSummary(eventData: Record<string, unknown>): string {
    const entries = Object.entries(eventData).slice(0, 3);
    if (entries.length === 0) {
      return 'No event fields recorded';
    }
    return entries
      .map(([key, value]) => `${key}: ${this.stringifyValue(value)}`)
      .join(' • ');
  }

  private stringifyValue(value: unknown): string {
    if (value === null) {
      return 'null';
    }
    if (typeof value === 'string') {
      return value;
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }

    try {
      return JSON.stringify(value);
    } catch {
      return '[unserializable]';
    }
  }
}
