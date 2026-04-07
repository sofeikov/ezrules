import { APIRequestContext, expect, test } from '@playwright/test';
import { LabelsPage } from '../pages/labels.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

function authHeaders() {
  return { Authorization: `Bearer ${getAuthToken()}` };
}

async function createLabel(request: APIRequestContext, labelName: string) {
  const response = await request.post(`${API_BASE}/api/v2/labels`, {
    headers: authHeaders(),
    data: { label_name: labelName },
  });
  const payload = await response.json();
  if (response.status() !== 201 || !payload.success) {
    throw new Error(`Failed to create label ${labelName}: ${JSON.stringify(payload)}`);
  }
}

async function createEvaluatedEvent(request: APIRequestContext, eventId: string) {
  const response = await request.post(`${API_BASE}/api/v2/evaluate`, {
    headers: authHeaders(),
    data: {
      event_id: eventId,
      event_timestamp: Math.floor(Date.now() / 1000),
      event_data: {
        amount: 245,
        currency: 'USD',
        txn_type: 'card_purchase',
        channel: 'web',
        customer_id: `cust-${eventId}`,
        customer_country: 'US',
        billing_country: 'US',
        shipping_country: 'US',
        ip_country: 'US',
        merchant_id: `merchant-${eventId}`,
        merchant_category: 'electronics',
        merchant_country: 'US',
        email_domain: 'example.com',
        account_age_days: 365,
        email_age_days: 365,
        customer_avg_amount_30d: 200,
        customer_std_amount_30d: 20,
        prior_chargebacks_180d: 0,
        manual_review_hits_30d: 0,
        decline_count_24h: 0,
        txn_velocity_10m: 1,
        txn_velocity_1h: 1,
        unique_cards_24h: 1,
        device_age_days: 180,
        device_trust_score: 92,
        has_3ds: 1,
        card_present: 0,
        is_guest_checkout: 0,
        password_reset_age_hours: 720,
        distance_from_home_km: 4,
        ip_proxy_score: 0,
        beneficiary_country: 'US',
        beneficiary_age_days: 365,
        local_hour: 11,
      },
    },
  });
  if (!response.ok()) {
    throw new Error(`Failed to create evaluated event ${eventId}: ${response.status()} ${await response.text()}`);
  }
}

test.describe('Tested Events Labels', () => {
  test('shows uploaded CSV labels in the tested events table', async ({ page, request }) => {
    const labelsPage = new LabelsPage(page);
    const suffix = Date.now();
    const labelName = `E2E_TESTED_EVENTS_${suffix}`;
    const eventId = `e2e-tested-events-${suffix}`;

    await createLabel(request, labelName);
    await createEvaluatedEvent(request, eventId);

    await labelsPage.goto();
    await labelsPage.waitForLabelsToLoad();
    await labelsPage.uploadCsvContent(`${eventId},${labelName}\n`);
    await expect(labelsPage.uploadResult).toContainText('1 applied');

    await page.goto('/tested-events');
    await page.locator('[data-testid="tested-events-table"]').waitFor();

    const labeledRow = page.locator('[data-testid="tested-event-row"]').filter({ hasText: eventId }).first();
    await expect(labeledRow).toBeVisible();
    await expect(labeledRow.locator('[data-testid="tested-event-label"]')).toContainText(labelName);
  });
});
