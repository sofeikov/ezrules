import { APIRequestContext, expect, test } from '@playwright/test';
import { RuleDetailPage } from '../pages/rule-detail.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

function authHeaders() {
  return { Authorization: `Bearer ${getAuthToken()}` };
}

function buildEvaluatedEventData(eventId: string, amount: number) {
  return {
    amount,
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
    account_age_days: 400,
    email_age_days: 400,
    customer_avg_amount_30d: 110,
    customer_std_amount_30d: 25,
    prior_chargebacks_180d: 0,
    manual_review_hits_30d: 0,
    decline_count_24h: 0,
    txn_velocity_10m: 1,
    txn_velocity_1h: 1,
    unique_cards_24h: 1,
    device_age_days: 100,
    device_trust_score: 90,
    has_3ds: 1,
    card_present: 0,
    is_guest_checkout: 0,
    password_reset_age_hours: 720,
    distance_from_home_km: 5,
    ip_proxy_score: 0,
    beneficiary_country: 'US',
    beneficiary_age_days: 400,
    local_hour: 12,
  };
}

async function createEvaluatedEvent(
  request: APIRequestContext,
  {
    eventId,
    amount,
    eventTimestamp,
  }: {
    eventId: string;
    amount: number;
    eventTimestamp: number;
  },
) {
  const response = await request.post(`${API_BASE}/api/v2/evaluate`, {
    headers: authHeaders(),
    data: {
      event_id: eventId,
      event_timestamp: eventTimestamp,
      event_data: buildEvaluatedEventData(eventId, amount),
    },
  });

  if (!response.ok()) {
    throw new Error(`Failed to create evaluated event ${eventId}: ${response.status()} ${await response.text()}`);
  }
}

test.describe('Rule Detail Performance', () => {
  let ruleDetailPage: RuleDetailPage;
  let testRuleId: number;

  test.beforeEach(async ({ page, request }) => {
    ruleDetailPage = new RuleDetailPage(page);

    const response = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: authHeaders(),
      data: {
        rid: `E2E_PERF_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        description: 'E2E rule for performance chart coverage',
        logic: "if $amount >= 150:\n\treturn !HOLD\nreturn !RELEASE",
      },
    });
    const payload = await response.json();
    if (!payload.success || !payload.rule?.r_id) {
      throw new Error(`Failed to create performance rule: ${JSON.stringify(payload)}`);
    }
    testRuleId = payload.rule.r_id;

    const promoteResponse = await request.post(`${API_BASE}/api/v2/rules/${testRuleId}/promote`, {
      headers: authHeaders(),
    });
    const promotePayload = await promoteResponse.json();
    if (!promoteResponse.ok() || !promotePayload.success) {
      throw new Error(`Failed to promote performance rule: ${JSON.stringify(promotePayload)}`);
    }
  });

  test.afterEach(async ({ request }) => {
    if (!testRuleId) {
      return;
    }

    await request.delete(`${API_BASE}/api/v2/rules/${testRuleId}`, {
      headers: authHeaders(),
    });
    testRuleId = 0;
  });

  test('shows an empty state when a rule has no stored hits', async ({ page }) => {
    const responsePromise = page.waitForResponse((response) =>
      response.url().includes(`/api/v2/analytics/rules/${testRuleId}/outcomes-distribution`) &&
      response.url().includes('aggregation=6h'),
    );

    await ruleDetailPage.goto(testRuleId);
    await ruleDetailPage.waitForRuleToLoad();
    const response = await responsePromise;

    expect(response.ok()).toBeTruthy();
    const payload = await response.json();
    expect(payload.datasets).toEqual([]);

    await expect(ruleDetailPage.performanceCard).toBeVisible();
    await expect(ruleDetailPage.performanceEmptyState).toBeVisible();
  });

  test('renders the rule performance chart and refreshes it when the time range changes', async ({ page, request }) => {
    const now = Math.floor(Date.now() / 1000);
    await createEvaluatedEvent(request, {
      eventId: `rule-performance-${testRuleId}-release`,
      amount: 90,
      eventTimestamp: now - 180,
    });
    await createEvaluatedEvent(request, {
      eventId: `rule-performance-${testRuleId}-hold-1`,
      amount: 220,
      eventTimestamp: now - 120,
    });
    await createEvaluatedEvent(request, {
      eventId: `rule-performance-${testRuleId}-hold-2`,
      amount: 260,
      eventTimestamp: now - 60,
    });

    const initialResponsePromise = page.waitForResponse((response) =>
      response.url().includes(`/api/v2/analytics/rules/${testRuleId}/outcomes-distribution`) &&
      response.url().includes('aggregation=6h'),
    );

    await ruleDetailPage.goto(testRuleId);
    await ruleDetailPage.waitForRuleToLoad();
    const initialResponse = await initialResponsePromise;

    expect(initialResponse.ok()).toBeTruthy();
    const initialPayload = await initialResponse.json();
    expect(initialPayload.datasets.map((dataset: { label: string }) => dataset.label)).toEqual(['HOLD', 'RELEASE']);

    await expect(ruleDetailPage.performanceCard).toBeVisible();
    await expect(ruleDetailPage.performanceChart).toBeVisible();
    await expect(ruleDetailPage.performanceTotalHits).toHaveText('3');
    await expect(ruleDetailPage.performanceOutcomeCount).toHaveText('2');
    await expect(ruleDetailPage.performanceTimeRangeSelect).toHaveValue('6h');

    const updatedResponsePromise = page.waitForResponse((response) =>
      response.url().includes(`/api/v2/analytics/rules/${testRuleId}/outcomes-distribution`) &&
      response.url().includes('aggregation=1h'),
    );

    await ruleDetailPage.selectPerformanceTimeRange('1h');
    const updatedResponse = await updatedResponsePromise;

    expect(updatedResponse.ok()).toBeTruthy();
    await expect(ruleDetailPage.performanceTimeRangeSelect).toHaveValue('1h');
    await expect(ruleDetailPage.performanceChart).toBeVisible();
    await expect(ruleDetailPage.performanceTotalHits).toHaveText('3');
  });
});
