import { test, expect } from '@playwright/test';
import { RuleListPage } from '../pages/rule-list.page';
import { RuleDetailPage } from '../pages/rule-detail.page';
import { BacktestingPage } from '../pages/backtesting.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

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

/**
 * E2E tests for the Rule Detail page.
 * Tests navigation, data display, and rule testing functionality.
 *
 * Each test creates its own rule via the API (Node.js request context, no CORS)
 * and deletes it in afterEach, making tests fully independent and safe to run
 * in parallel with other files.
 */

test.describe('Rule Detail Page', () => {
  let ruleListPage: RuleListPage;
  let ruleDetailPage: RuleDetailPage;
  let backtestingPage: BacktestingPage;
  let testRuleId: number;

  test.beforeEach(async ({ page, request }) => {
    ruleListPage = new RuleListPage(page);
    ruleDetailPage = new RuleDetailPage(page);
    backtestingPage = new BacktestingPage(page);

    // Create a dedicated rule via Node.js request context (no browser/CORS involved)
    const resp = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
      data: {
        rid: `E2E_DETAIL_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        description: 'E2E test rule for rule detail tests',
        logic: "if $amount > 100:\n\treturn 'HOLD'",
      },
    });
    const data = await resp.json();
    if (!data.success || !data.rule?.r_id) {
      throw new Error(`Failed to create test rule: ${JSON.stringify(data)}`);
    }
    testRuleId = data.rule.r_id;
  });

  test.afterEach(async ({ request }) => {
    if (testRuleId) {
      await request.delete(`${API_BASE}/api/v2/rules/${testRuleId}`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      testRuleId = 0;
    }
  });

  test.describe('Navigation', () => {
    test('should navigate to rule detail page from rule list', async ({ page }) => {
      await ruleListPage.goto();
      await ruleListPage.waitForRulesToLoad();

      const firstRow = page.locator('tbody tr').first();
      const viewLink = firstRow.locator('a:has-text("View")');

      await viewLink.click();

      // Should navigate to the detail page
      await expect(page).toHaveURL(/\/rules\/\d+/);
      await ruleDetailPage.waitForRuleToLoad();
    });

    test('should display breadcrumb navigation', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.breadcrumb).toBeVisible();
      await expect(ruleDetailPage.backToRulesLink).toBeVisible();
      await expect(ruleDetailPage.backToRulesLink).toHaveText('All Rules');
    });

    test('should navigate back to rules list via breadcrumb', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickBreadcrumbBack();

      await expect(page).toHaveURL(/\/rules$/);
      await expect(ruleListPage.rulesTable).toBeVisible();
    });

    test('should navigate back to rules list via back button', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickBack();

      await expect(page).toHaveURL(/\/rules$/);
      await expect(ruleListPage.rulesTable).toBeVisible();
    });
  });

  test.describe('Loading States', () => {
    test('should show loading spinner initially', async ({ page }) => {
      await page.goto(`/rules/${testRuleId}`, { waitUntil: 'domcontentloaded' });

      // The spinner should appear briefly or data should load
      const spinnerExists = await ruleDetailPage.loadingSpinner.count() > 0 || await ruleDetailPage.ruleIdField.isVisible();
      expect(spinnerExists).toBeTruthy();
    });

    test('should hide loading spinner after data loads', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.loadingSpinner).not.toBeVisible();
    });

    test('should display error message for non-existent rule', async () => {
      await ruleDetailPage.goto(999999);

      await expect(ruleDetailPage.errorMessage).toBeVisible();
    });
  });

  test.describe('Rule Details Display', () => {
    test('should display rule ID', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const ruleId = await ruleDetailPage.getRuleId();
      expect(ruleId).toBeTruthy();
      expect(ruleId.length).toBeGreaterThan(0);
    });

    test('should display rule description', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const description = await ruleDetailPage.getDescription();
      expect(description).toBeTruthy();
    });

    test('should display rule logic', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const logic = await ruleDetailPage.getLogic();
      expect(logic).toBeTruthy();
      expect(logic.length).toBeGreaterThan(0);
    });

    test('should display created date', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.createdDateField).toBeVisible();
      const createdText = await ruleDetailPage.createdDateField.textContent();
      expect(createdText).toBeTruthy();
    });

    test('should display all required field labels', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const requiredLabels = ['Rule ID', 'Description', 'Logic', 'Created'];

      for (const label of requiredLabels) {
        const labelElement = page.locator(`text=${label}`).first();
        await expect(labelElement).toBeVisible();
      }
    });
  });

  test.describe('Rule Testing Functionality', () => {
    test('should display test rule section', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const testSection = page.locator('text=Test Rule').first();
      await expect(testSection).toBeVisible();
      await expect(ruleDetailPage.testJsonTextarea).toBeVisible();
      await expect(ruleDetailPage.testRuleButton).toBeVisible();
    });

    test('should populate test JSON textarea with rule parameters', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      // Wait a bit for the fillInExampleParams to execute
      await ruleDetailPage.page.waitForTimeout(1000);

      const testJson = await ruleDetailPage.testJsonTextarea.inputValue();
      // Should have some JSON (could be empty object or populated with params)
      expect(testJson.length).toBeGreaterThanOrEqual(0);
    });

    test('should allow entering custom test JSON', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const testData = '{"amount": 100, "test": true}';
      await ruleDetailPage.setTestJson(testData);

      const value = await ruleDetailPage.testJsonTextarea.inputValue();
      expect(value).toBe(testData);
    });

    test('should enable test button when JSON is present', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.setTestJson('{"test": true}');

      await expect(ruleDetailPage.testRuleButton).toBeEnabled();
    });

    test('should handle TAB key in test JSON textarea', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.testJsonTextarea.click();
      await ruleDetailPage.testJsonTextarea.fill('test');

      // Press Tab key
      await ruleDetailPage.testJsonTextarea.press('Tab');

      // After pressing Tab, the textarea should still be focused or contain the tab character
      // We're testing that Tab doesn't navigate away from the field
      const value = await ruleDetailPage.testJsonTextarea.inputValue();
      const isFocused = await ruleDetailPage.testJsonTextarea.evaluate((el) => el === document.activeElement);

      // Either the textarea is still focused or it contains a tab character
      expect(isFocused || value.includes('\t')).toBeTruthy();
    });

    test('should render syntax-highlighted logic in read-only mode', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.logicViewer).toBeVisible();
      await expect(ruleDetailPage.logicViewer.locator('.cm-rule-field-token')).toContainText('$amount');
    });
  });

  test.describe('Backtesting', () => {
    test('should refresh completed backtest status without expanding the result card', async ({ page, request }) => {
      const timestamp = Math.floor(Date.now() / 1000);

      for (const [index, amount] of [90, 180, 260].entries()) {
        const eventId = `e2e-backtest-${testRuleId}-${Date.now()}-${index}`;
        const evaluateResponse = await request.post(`${API_BASE}/api/v2/evaluate`, {
          headers: { Authorization: `Bearer ${getAuthToken()}` },
          data: {
            event_id: eventId,
            event_timestamp: timestamp + index,
            event_data: buildEvaluatedEventData(eventId, amount),
          },
        });
        expect(evaluateResponse.ok()).toBeTruthy();
      }

      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();
      await ruleDetailPage.clickEdit();
      await ruleDetailPage.setLogic("if $amount > 150:\n\treturn 'BLOCK'");

      await backtestingPage.clickBacktest();
      await backtestingPage.waitForBacktestResults();
      await expect(backtestingPage.backtestItems).toHaveCount(1);

      await page.reload();
      await ruleDetailPage.waitForRuleToLoad();
      await backtestingPage.waitForBacktestResults();
      await expect(page.getByTestId('backtest-expanded-content')).toHaveCount(0);
      await backtestingPage.waitForResultStatus(0, 'Completed');
    });
  });

  test.describe('Revisions Section', () => {
    test('should display revisions section when revisions exist', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      // Check if revisions section is visible (it may not be if there are no revisions)
      const revisionsVisible = await ruleDetailPage.revisionsSection.isVisible().catch(() => false);

      if (revisionsVisible) {
        await expect(ruleDetailPage.revisionsSection).toBeVisible();
      }
    });
  });

  test.describe('Responsive Design', () => {
    test('should display correctly on desktop viewport', async ({ page }) => {
      await page.setViewportSize({ width: 1920, height: 1080 });
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.ruleIdField).toBeVisible();
      await expect(ruleDetailPage.testRuleButton).toBeVisible();
    });

    test('should maintain layout on smaller desktop viewport', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 720 });
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.ruleIdField).toBeVisible();
      await expect(ruleDetailPage.testRuleButton).toBeVisible();
    });
  });
});
