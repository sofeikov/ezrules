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
      transaction_id: eventId,
      effective_at: eventTimestamp,
      event_data: buildEvaluatedEventData(eventId, amount),
    },
  });

  if (!response.ok()) {
    throw new Error(`Failed to create evaluated event ${eventId}: ${response.status()} ${await response.text()}`);
  }
}

test.describe('Rule Detail Triggered Transactions', () => {
  let ruleDetailPage: RuleDetailPage;
  let testRuleId: number;
  let originalMainRuleExecutionMode: string | null = null;

  test.beforeEach(async ({ page, request }) => {
    ruleDetailPage = new RuleDetailPage(page);
    originalMainRuleExecutionMode = null;

    const settingsResponse = await request.get(`${API_BASE}/api/v2/settings/runtime`, {
      headers: authHeaders(),
    });
    expect(settingsResponse.ok()).toBeTruthy();
    const settingsPayload = await settingsResponse.json();
    originalMainRuleExecutionMode = settingsPayload.main_rule_execution_mode as string;
    if (originalMainRuleExecutionMode !== 'all_matches') {
      const updateResponse = await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders(),
        data: { main_rule_execution_mode: 'all_matches' },
      });
      expect(updateResponse.ok()).toBeTruthy();
    }

    const response = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: authHeaders(),
      data: {
        rid: `E2E_TRIGGERS_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        description: 'E2E rule for recent triggered transactions',
        logic: "if $amount >= 150:\n\treturn !HOLD",
      },
    });
    const payload = await response.json();
    if (!payload.success || !payload.rule?.r_id) {
      throw new Error(`Failed to create trigger rule: ${JSON.stringify(payload)}`);
    }
    testRuleId = payload.rule.r_id;

    const promoteResponse = await request.post(`${API_BASE}/api/v2/rules/${testRuleId}/promote`, {
      headers: authHeaders(),
    });
    const promotePayload = await promoteResponse.json();
    if (!promoteResponse.ok() || !promotePayload.success) {
      throw new Error(`Failed to promote trigger rule: ${JSON.stringify(promotePayload)}`);
    }
  });

  test.afterEach(async ({ request }) => {
    if (testRuleId) {
      await request.delete(`${API_BASE}/api/v2/rules/${testRuleId}`, {
        headers: authHeaders(),
      });
      testRuleId = 0;
    }

    if (originalMainRuleExecutionMode && originalMainRuleExecutionMode !== 'all_matches') {
      await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders(),
        data: { main_rule_execution_mode: originalMainRuleExecutionMode },
      });
    }
  });

  test('loads recent triggered transactions in batches', async ({ page, request }) => {
    const now = Math.floor(Date.now() / 1000);
    for (let index = 0; index < 12; index += 1) {
      await createEvaluatedEvent(request, {
        eventId: `rule-triggered-${testRuleId}-${index}`,
        amount: 200 + index,
        eventTimestamp: now + index,
      });
    }

    const firstPageResponsePromise = page.waitForResponse((response) =>
      response.url().includes(`/api/v2/rules/${testRuleId}/triggered-events`) &&
      response.url().includes('limit=10') &&
      response.url().includes('offset=0'),
    );

    await ruleDetailPage.goto(testRuleId);
    await ruleDetailPage.waitForRuleToLoad();
    const firstPageResponse = await firstPageResponsePromise;
    expect(firstPageResponse.ok()).toBeTruthy();

    await expect(ruleDetailPage.triggeredEventsCard).toBeVisible();
    await expect(ruleDetailPage.triggeredEventsRows).toHaveCount(10);
    await expect(ruleDetailPage.triggeredEventsStatus).toContainText('Showing 10 of 12');
    await expect(ruleDetailPage.triggeredEventsRows.first()).toContainText(`rule-triggered-${testRuleId}-11`);
    await expect(ruleDetailPage.triggeredEventsLoadMoreButton).toBeVisible();

    const secondPageResponsePromise = page.waitForResponse((response) =>
      response.url().includes(`/api/v2/rules/${testRuleId}/triggered-events`) &&
      response.url().includes('limit=10') &&
      response.url().includes('offset=10'),
    );
    await ruleDetailPage.clickTriggeredEventsLoadMore();
    const secondPageResponse = await secondPageResponsePromise;
    expect(secondPageResponse.ok()).toBeTruthy();

    await expect(ruleDetailPage.triggeredEventsRows).toHaveCount(12);
    await expect(ruleDetailPage.triggeredEventsStatus).toContainText('Showing 12 of 12');
    await expect(ruleDetailPage.triggeredEventsRows.last()).toContainText(`rule-triggered-${testRuleId}-0`);
    await expect(ruleDetailPage.triggeredEventsLoadMoreButton).toHaveCount(0);
  });

  test('shows an empty state when the rule has no triggered transactions', async ({ page }) => {
    const responsePromise = page.waitForResponse((response) =>
      response.url().includes(`/api/v2/rules/${testRuleId}/triggered-events`) &&
      response.url().includes('offset=0'),
    );

    await ruleDetailPage.goto(testRuleId);
    await ruleDetailPage.waitForRuleToLoad();
    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();

    await expect(ruleDetailPage.triggeredEventsCard).toBeVisible();
    await expect(ruleDetailPage.triggeredEventsEmptyState).toBeVisible();
    await expect(ruleDetailPage.triggeredEventsRows).toHaveCount(0);
    await expect(ruleDetailPage.triggeredEventsLoadMoreButton).toHaveCount(0);
  });
});
