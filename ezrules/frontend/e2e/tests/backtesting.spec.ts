import { readFileSync } from 'fs';
import { join } from 'path';
import { test, expect } from '@playwright/test';
import { RuleDetailPage } from '../pages/rule-detail.page';
import { BacktestingPage } from '../pages/backtesting.page';

const API_BASE = 'http://localhost:8888';

/** Read the JWT access token from the saved auth state file. */
function getAuthToken(): string {
  const state = JSON.parse(readFileSync(join(__dirname, '../.auth/user.json'), 'utf-8'));
  const origin = state.origins?.find((o: any) => o.origin === 'http://localhost:4200');
  return origin?.localStorage?.find((e: any) => e.name === 'ezrules_access_token')?.value ?? '';
}

/**
 * E2E tests for the Backtesting functionality on the Rule Detail page.
 * Tests backtest button visibility, triggering backtests, and viewing results.
 *
 * Each test creates its own rule via the API and deletes it in afterEach,
 * making tests fully independent and safe to run in parallel with other files.
 */

test.describe('Backtesting Functionality', () => {
  let ruleDetailPage: RuleDetailPage;
  let backtestingPage: BacktestingPage;
  let testRuleId: number;

  test.beforeEach(async ({ page, request }) => {
    ruleDetailPage = new RuleDetailPage(page);
    backtestingPage = new BacktestingPage(page);

    const resp = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
      data: {
        rid: `E2E_BACKTEST_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        description: 'E2E test rule for backtesting tests',
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

  test.describe('Backtest Button Visibility', () => {
    test('should not show backtest button in view mode', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(backtestingPage.backtestButton).not.toBeVisible();
    });

    test('should show backtest button in edit mode', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickEdit();

      await expect(backtestingPage.backtestButton).toBeVisible();
    });

    test('should hide backtest button after cancelling edit', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickEdit();
      await expect(backtestingPage.backtestButton).toBeVisible();

      await ruleDetailPage.clickCancel();
      await expect(backtestingPage.backtestButton).not.toBeVisible();
    });
  });

  test.describe('Trigger Backtest', () => {
    test('should trigger backtest and show result in accordion', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickEdit();

      // Modify the logic slightly
      const newLogic = "if $amount > 999999:\n\treturn 'BACKTEST_TEST'";
      await ruleDetailPage.setLogic(newLogic);

      // Trigger backtest and wait for the POST response
      await Promise.all([
        page.waitForResponse(resp => resp.url().includes('/api/v2/backtesting') && resp.request().method() === 'POST'),
        backtestingPage.clickBacktest()
      ]);

      // Should show results card after backtest is triggered
      await backtestingPage.waitForBacktestResults();

      const resultCount = await backtestingPage.getResultCount();
      expect(resultCount).toBeGreaterThanOrEqual(1);
    });

    test('should show result status badge', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickEdit();

      const newLogic = "if $amount > 999999:\n\treturn 'STATUS_TEST'";
      await ruleDetailPage.setLogic(newLogic);

      await Promise.all([
        page.waitForResponse(resp => resp.url().includes('/api/v2/backtesting') && resp.request().method() === 'POST'),
        backtestingPage.clickBacktest()
      ]);

      await backtestingPage.waitForBacktestResults();

      // Status badge should be visible (either In Progress or Completed)
      const status = await backtestingPage.getResultStatus(0);
      expect(['In Progress', 'Completed', 'Failed']).toContain(status);
    });
  });

  test.describe('Expand Backtest Result', () => {
    test('should expand result and show diff and outcome table', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickEdit();

      const newLogic = "if $amount > 999999:\n\treturn 'EXPAND_TEST'";
      await ruleDetailPage.setLogic(newLogic);

      await Promise.all([
        page.waitForResponse(resp => resp.url().includes('/api/v2/backtesting') && resp.request().method() === 'POST'),
        backtestingPage.clickBacktest()
      ]);

      await backtestingPage.waitForBacktestResults();

      // Expand the first result
      await backtestingPage.expandResult(0);
      await backtestingPage.waitForExpandedContent();

      // Wait for SUCCESS status (task runs eagerly in test mode)
      await page.waitForFunction(() => {
        const status = document.querySelector('[data-testid="backtest-status-0"]');
        return status?.textContent?.trim() === 'Completed';
      }, { timeout: 20000 });

      // Should show diff section
      const diffSection = await backtestingPage.getDiffSection();
      await expect(diffSection).toBeVisible();

      // Should show outcome table
      const outcomeTable = await backtestingPage.getOutcomeTable();
      await expect(outcomeTable).toBeVisible();
    });
  });
});
