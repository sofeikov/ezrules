import { APIRequestContext, expect, test } from '@playwright/test';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

test.describe('Tested Events Nested Field Highlights', () => {
  const createdRuleIds: number[] = [];
  const authHeaders = () => ({ Authorization: `Bearer ${getAuthToken()}` });
  let originalMainRuleExecutionMode: string | null = null;

  test.afterEach(async ({ request }) => {
    while (createdRuleIds.length > 0) {
      const ruleId = createdRuleIds.pop();
      if (!ruleId) {
        continue;
      }
      await request.post(`${API_BASE}/api/v2/rules/${ruleId}/archive`, {
        headers: authHeaders(),
      });
    }
    if (originalMainRuleExecutionMode && originalMainRuleExecutionMode !== 'all_matches') {
      await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders(),
        data: { main_rule_execution_mode: originalMainRuleExecutionMode },
      });
    }
  });

  test('highlights nested paths and narrows to the hovered rule', async ({ page, request }) => {
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

    const eventId = `e2e-nested-highlight-${Date.now()}`;

    const ageRuleId = await createAndPromoteRule(
      request,
      `E2E_EVENTS_NESTED_${Date.now()}_A`,
      'Highlight nested age path',
      "if $customer.profile.age >= 21:\n\treturn !HOLD"
    );
    createdRuleIds.push(ageRuleId);

    const countryRuleId = await createAndPromoteRule(
      request,
      `E2E_EVENTS_NESTED_${Date.now()}_B`,
      'Highlight nested country path',
      "if $customer.country == 'GB':\n\treturn !RELEASE"
    );
    createdRuleIds.push(countryRuleId);

    const evaluateResponse = await request.post(`${API_BASE}/api/v2/evaluate`, {
      headers: authHeaders(),
      data: {
        event_id: eventId,
        event_timestamp: Math.floor(Date.now() / 1000),
        event_data: {
          amount: 2500,
          currency: 'GBP',
          txn_type: 'purchase',
          channel: 'web',
          customer_id: 'cust-e2e-nested-highlight',
          customer_country: 'GB',
          billing_country: 'GB',
          shipping_country: 'GB',
          ip_country: 'GB',
          merchant_id: 'mrc_dailycart',
          merchant_category: 'groceries',
          merchant_country: 'GB',
          email_domain: 'example.com',
          account_age_days: 400,
          email_age_days: 200,
          customer_avg_amount_30d: 2100,
          customer_std_amount_30d: 600,
          prior_chargebacks_180d: 0,
          manual_review_hits_30d: 0,
          decline_count_24h: 0,
          txn_velocity_10m: 1,
          txn_velocity_1h: 1,
          unique_cards_24h: 1,
          device_age_days: 120,
          device_trust_score: 95,
          has_3ds: 1,
          card_present: 1,
          is_guest_checkout: 0,
          password_reset_age_hours: 240,
          distance_from_home_km: 8,
          ip_proxy_score: 0,
          beneficiary_country: 'GB',
          beneficiary_age_days: 120,
          local_hour: 14,
          customer: {
            profile: {
              age: 34,
            },
            country: 'GB',
          },
          merchant: {
            country: 'US',
          },
        },
      },
    });
    expect(evaluateResponse.ok(), await evaluateResponse.text()).toBeTruthy();

    await page.goto('/tested-events');
    await page.locator('[data-testid="tested-events-table"]').waitFor();
    const targetRow = page.locator('[data-testid="tested-event-row"]').filter({ hasText: eventId }).first();
    await expect(targetRow).toBeVisible();
    await targetRow.locator('[data-testid="tested-event-details-button"]').click();

    const customerField = page.locator('[data-testid="tested-event-payload-field"][data-field-name="customer"]').first();
    const customerProfileField = page
      .locator('[data-testid="tested-event-payload-field"][data-field-name="customer.profile"]')
      .first();
    const customerAgeField = page
      .locator('[data-testid="tested-event-payload-field"][data-field-name="customer.profile.age"]')
      .first();
    const customerCountryField = page
      .locator('[data-testid="tested-event-payload-field"][data-field-name="customer.country"]')
      .first();
    const merchantCountryField = page
      .locator('[data-testid="tested-event-payload-field"][data-field-name="merchant.country"]')
      .first();

    await expect(customerField).toHaveAttribute('data-highlighted', 'true');
    await expect(customerProfileField).toHaveAttribute('data-highlighted', 'true');
    await expect(customerAgeField).toHaveAttribute('data-highlighted', 'true');
    await expect(customerCountryField).toHaveAttribute('data-highlighted', 'true');
    await expect(merchantCountryField).toHaveAttribute('data-highlighted', 'false');

    const ageRule = page
      .locator('[data-testid="tested-event-triggered-rule"]')
      .filter({ hasText: 'Highlight nested age path' })
      .first();
    await ageRule.hover();

    await expect(customerField).toHaveAttribute('data-highlighted', 'true');
    await expect(customerProfileField).toHaveAttribute('data-highlighted', 'true');
    await expect(customerAgeField).toHaveAttribute('data-highlighted', 'true');
    await expect(customerCountryField).toHaveAttribute('data-highlighted', 'false');

    const countryRule = page
      .locator('[data-testid="tested-event-triggered-rule"]')
      .filter({ hasText: 'Highlight nested country path' })
      .first();
    await countryRule.hover();

    await expect(customerField).toHaveAttribute('data-highlighted', 'true');
    await expect(customerProfileField).toHaveAttribute('data-highlighted', 'false');
    await expect(customerAgeField).toHaveAttribute('data-highlighted', 'false');
    await expect(customerCountryField).toHaveAttribute('data-highlighted', 'true');
  });
});

async function createAndPromoteRule(
  request: APIRequestContext,
  rid: string,
  description: string,
  logic: string
): Promise<number> {
  const createResponse = await request.post(`${API_BASE}/api/v2/rules`, {
    headers: { Authorization: `Bearer ${getAuthToken()}` },
    data: {
      rid,
      description,
      logic,
    },
  });
  expect(createResponse.ok()).toBeTruthy();
  const createPayload = await createResponse.json();
  expect(createPayload.success).toBeTruthy();

  const ruleId = createPayload.rule.r_id as number;
  const promoteResponse = await request.post(`${API_BASE}/api/v2/rules/${ruleId}/promote`, {
    headers: { Authorization: `Bearer ${getAuthToken()}` },
  });
  expect(promoteResponse.ok()).toBeTruthy();
  return ruleId;
}
