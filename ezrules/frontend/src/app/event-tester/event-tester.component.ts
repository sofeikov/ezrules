import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { SidebarComponent } from '../components/sidebar.component';
import { EventTestResponse, EventTestRuleResult, EventTestService } from '../services/event-test.service';

const DEFAULT_EVENT_PAYLOAD: Record<string, unknown> = {
  account_age_days: 7,
  amount: 875.5,
  beneficiary_age_days: 1,
  beneficiary_country: 'IR',
  billing_country: 'US',
  card_present: 0,
  channel: 'web',
  currency: 'USD',
  customer: {
    id: 'cust_demo_001',
    country: 'US',
    profile: {
      age: 34,
      segment: 'established',
    },
    account: {
      age_days: 180,
      email_age_days: 365,
      prior_chargebacks_180d: 0,
    },
    behavior: {
      avg_amount_30d: 140,
      std_amount_30d: 30,
    },
  },
  customer_avg_amount_30d: 140,
  customer_country: 'US',
  customer_id: 'cust_demo_001',
  customer_std_amount_30d: 30,
  decline_count_24h: 7,
  device_age_days: 1,
  device_trust_score: 18,
  distance_from_home_km: 4200,
  email_age_days: 4,
  email_domain: 'mailinator.com',
  has_3ds: 0,
  ip_country: 'BR',
  ip_proxy_score: 92,
  is_guest_checkout: 1,
  is_verified: false,
  local_hour: 2,
  manual_review_hits_30d: 2,
  merchant_category: 'gift_cards',
  merchant_country: 'US',
  merchant_id: 'mrc_cardhub',
  password_reset_age_hours: 2,
  prior_chargebacks_180d: 2,
  receive_country: 'MX',
  score: 0.92,
  send_country: 'US',
  sender: {
    id: 'sender_demo_001',
    country: 'US',
    account: {
      age_days: 90,
    },
    origin: {
      country: 'BR',
    },
    device: {
      age_days: 1,
      trust_score: 18,
    },
  },
  shipping_country: 'MX',
  txn_type: 'wallet_cashout',
  txn_velocity_10m: 10,
  txn_velocity_1h: 6,
  unique_cards_24h: 5,
};

@Component({
  selector: 'app-event-tester',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, SidebarComponent],
  templateUrl: './event-tester.component.html'
})
export class EventTesterComponent implements OnInit {
  eventId = '';
  eventTimestamp = 0;
  eventJson = '';
  testing = false;
  error: string | null = null;
  result: EventTestResponse | null = null;

  constructor(private eventTestService: EventTestService) {}

  ngOnInit(): void {
    this.resetExample();
  }

  resetExample(): void {
    this.eventId = `test_evt_${Date.now()}`;
    this.eventTimestamp = Math.floor(Date.now() / 1000);
    this.eventJson = JSON.stringify(
      DEFAULT_EVENT_PAYLOAD,
      null,
      2
    );
    this.error = null;
    this.result = null;
  }

  runTest(): void {
    this.error = null;
    this.result = null;

    let eventData: Record<string, unknown>;
    try {
      const parsed = JSON.parse(this.eventJson);
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
        this.error = 'Event payload must be a JSON object.';
        return;
      }
      eventData = parsed as Record<string, unknown>;
    } catch {
      this.error = 'Event payload is malformed JSON.';
      return;
    }

    this.testing = true;
    this.eventTestService.runTest({
      event_id: this.eventId.trim() || `test_evt_${Date.now()}`,
      event_timestamp: Number(this.eventTimestamp),
      event_data: eventData,
    }).subscribe({
      next: (response) => {
        this.testing = false;
        this.result = response;
      },
      error: (error) => {
        this.testing = false;
        this.error = error.error?.detail || 'Event test failed.';
      }
    });
  }

  handleTextareaTab(event: KeyboardEvent): void {
    if (event.key !== 'Tab') {
      return;
    }
    event.preventDefault();
    const textarea = event.target as HTMLTextAreaElement;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const value = textarea.value;
    const nextValue = `${value.substring(0, start)}  ${value.substring(end)}`;
    textarea.value = nextValue;
    textarea.selectionStart = textarea.selectionEnd = start + 2;
    this.eventJson = nextValue;
  }

  matchedRules(): EventTestRuleResult[] {
    return this.result?.evaluated_rules.filter((rule) => rule.matched) ?? [];
  }

  nonMatchedRules(): EventTestRuleResult[] {
    return this.result?.evaluated_rules.filter((rule) => !rule.matched) ?? [];
  }

  outcomeEntries(): [string, number][] {
    return Object.entries(this.result?.outcome_counters ?? {});
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
    if (outcome) {
      return 'bg-blue-100 text-blue-800';
    }
    return 'bg-gray-200 text-gray-700';
  }

  formatTimestamp(timestamp: number): string {
    if (!Number.isFinite(timestamp)) {
      return '';
    }
    return new Date(timestamp * 1000).toLocaleString();
  }
}
