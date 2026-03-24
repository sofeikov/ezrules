import { APIRequestContext, expect, test } from '@playwright/test';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

function buildEvaluatedEventData(eventId: string, amount: number, country?: string) {
  return {
    amount,
    country,
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

async function waitForBacktestCompletion(request: APIRequestContext, ruleId: number) {
  const headers = { Authorization: `Bearer ${getAuthToken()}` };
  const resultsResponse = await request.get(`${API_BASE}/api/v2/backtesting/${ruleId}`, { headers });
  expect(resultsResponse.ok()).toBeTruthy();
  const resultsData = await resultsResponse.json();
  const taskId = resultsData.results?.[0]?.task_id as string | undefined;
  expect(taskId).toBeTruthy();

  let taskData: { status?: string; skipped_records?: number } | null = null;
  for (let attempt = 0; attempt < 15; attempt += 1) {
    const taskResponse = await request.get(`${API_BASE}/api/v2/backtesting/task/${taskId}`, { headers });
    expect(taskResponse.ok()).toBeTruthy();
    taskData = await taskResponse.json();
    if (taskData?.status && taskData.status !== 'PENDING') {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  expect(taskData?.status).toBe('SUCCESS');
  return taskData;
}

test.describe('Backtesting Eligibility Warnings', () => {
  test('should show skipped-record context when a proposed rule introduces a new field', async ({ page, request }) => {
    const createResponse = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
      data: {
        rid: `E2E_BT_WARN_${Date.now()}`,
        description: 'backtest eligibility warning test',
        logic: "if $amount > 100:\n\treturn 'HOLD'",
      },
    });
    const createData = await createResponse.json();
    const ruleId = createData.rule.r_id as number;

    try {
      const events = [
        {
          event_id: `btwarn-${ruleId}-1`,
          event_timestamp: 1700000001,
          event_data: buildEvaluatedEventData(`btwarn-${ruleId}-1`, 150, 'US'),
        },
        {
          event_id: `btwarn-${ruleId}-2`,
          event_timestamp: 1700000002,
          event_data: buildEvaluatedEventData(`btwarn-${ruleId}-2`, 200),
        },
      ];

      for (const payload of events) {
        const evaluateResponse = await request.post(`${API_BASE}/api/v2/evaluate`, {
          headers: { Authorization: `Bearer ${getAuthToken()}` },
          data: payload,
        });
        expect(evaluateResponse.ok()).toBeTruthy();
      }

      await page.goto(`/rules/${ruleId}`);
      await page.getByRole('button', { name: 'Edit Rule' }).click();

      const logicEditor = page.locator('textarea[placeholder="Enter rule logic"]').first();
      await logicEditor.fill('if $amount > 100 and $country == "US":\n\treturn "BLOCK"');

      await page.getByTestId('backtest-button').click();
      await expect(page.getByTestId('backtest-results-card')).toBeVisible({ timeout: 15000 });

      const taskData = await waitForBacktestCompletion(request, ruleId);
      await page.goto(`/rules/${ruleId}`);
      await expect(page.getByTestId('backtest-results-card')).toBeVisible({ timeout: 15000 });

      const firstResult = page.getByTestId('backtest-item-0');
      await firstResult.locator('button').first().click();
      await expect(page.getByTestId('backtest-status-0')).toHaveText('Completed');

      const skippedSummary = page.getByTestId('backtest-skipped-summary');
      await expect(skippedSummary).toBeVisible();
      await expect(skippedSummary).toContainText(`skipped ${taskData.skipped_records}`);
      await expect(skippedSummary).toContainText('country');
    } finally {
      await request.delete(`${API_BASE}/api/v2/rules/${ruleId}`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
    }
  });
});
