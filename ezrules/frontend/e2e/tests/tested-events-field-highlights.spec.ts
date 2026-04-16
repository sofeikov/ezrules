import { expect, test } from '@playwright/test';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

test.describe('Tested Events Field Highlights', () => {
  const createdRuleIds: number[] = [];
  const authHeaders = () => ({ Authorization: `Bearer ${getAuthToken()}` });

  test.afterEach(async ({ request }) => {
    while (createdRuleIds.length > 0) {
      const ruleId = createdRuleIds.pop();
      if (!ruleId) {
        continue;
      }
      await request.delete(`${API_BASE}/api/v2/rules/${ruleId}`, {
        headers: authHeaders(),
      });
    }
  });

  test('highlights all referenced fields by default and narrows to the hovered rule', async ({ page, request }) => {
    const holdRuleResponse = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: authHeaders(),
      data: {
        rid: `E2E_EVENTS_FIELDS_${Date.now()}_A`,
        description: 'Highlight amount field',
        logic: "if $amount >= 1000:\n\treturn !HOLD",
      },
    });
    const holdRuleData = await holdRuleResponse.json();
    if (!holdRuleData.success || !holdRuleData.rule?.r_id) {
      throw new Error(`Failed to create amount rule: ${JSON.stringify(holdRuleData)}`);
    }
    createdRuleIds.push(holdRuleData.rule.r_id);
    const holdPromoteResponse = await request.post(`${API_BASE}/api/v2/rules/${holdRuleData.rule.r_id}/promote`, {
      headers: authHeaders(),
    });
    expect(holdPromoteResponse.ok()).toBeTruthy();

    const releaseRuleResponse = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: authHeaders(),
      data: {
        rid: `E2E_EVENTS_FIELDS_${Date.now()}_B`,
        description: 'Highlight country field',
        logic: "if $billing_country == 'GB':\n\treturn !RELEASE",
      },
    });
    const releaseRuleData = await releaseRuleResponse.json();
    if (!releaseRuleData.success || !releaseRuleData.rule?.r_id) {
      throw new Error(`Failed to create country rule: ${JSON.stringify(releaseRuleData)}`);
    }
    createdRuleIds.push(releaseRuleData.rule.r_id);
    const releasePromoteResponse = await request.post(`${API_BASE}/api/v2/rules/${releaseRuleData.rule.r_id}/promote`, {
      headers: authHeaders(),
    });
    expect(releasePromoteResponse.ok()).toBeTruthy();

    const evaluateResponse = await request.post(`${API_BASE}/api/v2/evaluate`, {
      headers: authHeaders(),
      data: {
        event_id: `e2e-field-highlight-${Date.now()}`,
        event_timestamp: Math.floor(Date.now() / 1000),
        event_data: {
          amount: 2500,
          currency: 'GBP',
          txn_type: 'purchase',
          channel: 'web',
          customer_id: 'cust-e2e-highlight',
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
        },
      },
    });
    if (!evaluateResponse.ok()) {
      throw new Error(`Evaluate request failed: ${evaluateResponse.status()} ${await evaluateResponse.text()}`);
    }

    await page.goto('/tested-events');
    await page.locator('[data-testid="tested-events-table"]').waitFor();
    await page.locator('[data-testid="tested-event-details-button"]').first().click();

    const amountField = page.locator('[data-testid="tested-event-payload-field"][data-field-name="amount"]').first();
    const billingCountryField = page
      .locator('[data-testid="tested-event-payload-field"][data-field-name="billing_country"]')
      .first();
    const merchantField = page
      .locator('[data-testid="tested-event-payload-field"][data-field-name="merchant_category"]')
      .first();

    await expect(amountField).toHaveAttribute('data-highlighted', 'true');
    await expect(billingCountryField).toHaveAttribute('data-highlighted', 'true');
    await expect(merchantField).toHaveAttribute('data-highlighted', 'false');

    const amountRule = page
      .locator('[data-testid="tested-event-triggered-rule"]')
      .filter({ hasText: 'Highlight amount field' })
      .first();
    await amountRule.hover();

    await expect(amountField).toHaveAttribute('data-highlighted', 'true');
    await expect(billingCountryField).toHaveAttribute('data-highlighted', 'false');
    await expect(merchantField).toHaveAttribute('data-highlighted', 'false');

    const countryRule = page
      .locator('[data-testid="tested-event-triggered-rule"]')
      .filter({ hasText: 'Highlight country field' })
      .first();
    await countryRule.hover();

    await expect(amountField).toHaveAttribute('data-highlighted', 'false');
    await expect(billingCountryField).toHaveAttribute('data-highlighted', 'true');
    await expect(merchantField).toHaveAttribute('data-highlighted', 'false');

    await page.locator('h3', { hasText: 'Event payload' }).hover();

    await expect(amountField).toHaveAttribute('data-highlighted', 'true');
    await expect(billingCountryField).toHaveAttribute('data-highlighted', 'true');
    await expect(merchantField).toHaveAttribute('data-highlighted', 'false');
  });
});
