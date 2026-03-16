import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { SidebarComponent } from '../components/sidebar.component';
import { TestedEvent, TestedEventService } from '../services/tested-event.service';

interface PayloadLine {
  fieldName: string | null;
  highlighted: boolean;
  prefix?: string;
  suffix?: string;
  text?: string;
}

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
  hoveredRuleIdsByEvent = new Map<number, number>();
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
        this.hoveredRuleIdsByEvent = new Map(
          [...this.hoveredRuleIdsByEvent].filter(([eventId, ruleId]) =>
            this.events.some(
              (event) => event.tl_id === eventId && event.triggered_rules.some((rule) => rule.r_id === ruleId)
            )
          )
        );
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
      this.hoveredRuleIdsByEvent.delete(eventId);
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

  setHoveredRule(eventId: number, ruleId: number | null): void {
    if (ruleId === null) {
      this.hoveredRuleIdsByEvent.delete(eventId);
      return;
    }
    this.hoveredRuleIdsByEvent.set(eventId, ruleId);
  }

  isRuleHovered(eventId: number, ruleId: number): boolean {
    return this.hoveredRuleIdsByEvent.get(eventId) === ruleId;
  }

  payloadHint(event: TestedEvent): string {
    return this.hoveredRuleIdsByEvent.has(event.tl_id)
      ? 'Highlighting fields referenced by the hovered rule inside the payload JSON.'
      : 'Highlighting fields referenced by any triggered rule. Hover a rule to focus the JSON view.';
  }

  payloadLines(event: TestedEvent): PayloadLine[] {
    const highlightedFields = this.highlightedFields(event);
    const entries = Object.entries(event.event_data);
    const lines: PayloadLine[] = [{ text: '{', fieldName: null, highlighted: false }];

    entries.forEach(([key, value], index) => {
      const valueLines = this.stringifyJsonValue(value).split('\n');
      const highlighted = highlightedFields.has(key);
      const trailingComma = index < entries.length - 1 ? ',' : '';

      lines.push({
        fieldName: key,
        highlighted,
        prefix: '  "',
        suffix: `": ${valueLines[0]}${valueLines.length === 1 ? trailingComma : ''}`,
      });

      valueLines.slice(1, -1).forEach((line) => {
        lines.push({
          text: `  ${line}`,
          fieldName: key,
          highlighted,
        });
      });

      if (valueLines.length > 1) {
        lines.push({
          text: `  ${valueLines[valueLines.length - 1]}${trailingComma}`,
          fieldName: key,
          highlighted,
        });
      }
    });

    lines.push({ text: '}', fieldName: null, highlighted: false });
    return lines;
  }

  referencedFieldSummary(fields: string[]): string {
    if (fields.length === 0) {
      return 'This rule does not reference any event fields.';
    }
    if (fields.length === 1) {
      return 'Hover to highlight 1 referenced field in the payload JSON.';
    }
    return `Hover to highlight ${fields.length} referenced fields in the payload JSON.`;
  }

  private highlightedFields(event: TestedEvent): Set<string> {
    const hoveredRuleId = this.hoveredRuleIdsByEvent.get(event.tl_id);
    const fields = hoveredRuleId === undefined
      ? event.triggered_rules.flatMap((rule) => rule.referenced_fields)
      : event.triggered_rules
          .filter((rule) => rule.r_id === hoveredRuleId)
          .flatMap((rule) => rule.referenced_fields);
    return new Set(fields);
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

  private stringifyJsonValue(value: unknown): string {
    try {
      return JSON.stringify(value, null, 2) ?? 'null';
    } catch {
      return '"[unserializable]"';
    }
  }
}
