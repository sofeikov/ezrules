import { test, expect } from '@playwright/test';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

test.describe('Rule Allowlist Lane', () => {
  let createdRuleId = 0;

  test.afterEach(async ({ request }) => {
    if (createdRuleId) {
      await request.delete(`${API_BASE}/api/v2/rules/${createdRuleId}`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      createdRuleId = 0;
    }
  });

  test('creates an allowlist rule and surfaces the lane in the UI', async ({ page }) => {
    await page.goto('/rules/create');

    await page.locator('input[placeholder="Enter rule ID"]').fill(`E2E_ALLOWLIST_${Date.now()}`);
    await page.locator('label:has-text("Description") + textarea').fill('Allowlist rule created by e2e');
    await page.locator('[data-testid="rule-lane-select"]').selectOption('allowlist');
    await page.locator('label:has-text("Logic") + textarea').fill('if $country == "GB":\n\treturn !RELEASE');

    await Promise.all([
      page.waitForResponse(resp => resp.url().endsWith('/api/v2/rules') && resp.request().method() === 'POST'),
      page.locator('button:has-text("Create Rule")').click(),
    ]);

    await expect(page).toHaveURL(/\/rules\/\d+/);
    const urlMatch = page.url().match(/\/rules\/(\d+)/);
    createdRuleId = urlMatch ? parseInt(urlMatch[1], 10) : 0;

    await expect(page.locator('[data-testid="allowlist-active-badge"]')).toContainText('Allowlist');
    await expect(page.locator('label:has-text("Rule Lane") + div')).toContainText('Allowlist rules');

    await page.goto('/rules');
    await expect(page.locator('text=ALLOWLIST').first()).toBeVisible();
  });
});
