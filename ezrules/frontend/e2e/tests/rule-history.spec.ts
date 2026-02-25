import { readFileSync } from 'fs';
import { join } from 'path';
import { test, expect } from '@playwright/test';
import { RuleDetailPage } from '../pages/rule-detail.page';
import { RuleHistoryPage } from '../pages/rule-history.page';

const API_BASE = 'http://localhost:8888';

/** Read the JWT access token from the saved auth state file. */
function getAuthToken(): string {
  const state = JSON.parse(readFileSync(join(__dirname, '../.auth/user.json'), 'utf-8'));
  const origin = state.origins?.find((o: any) => o.origin === 'http://localhost:4200');
  return origin?.localStorage?.find((e: any) => e.name === 'ezrules_access_token')?.value ?? '';
}

/**
 * E2E tests for the Rule History (diff timeline) functionality.
 * Tests that the history page loads, displays diffs correctly,
 * and navigation works as expected.
 *
 * Each test creates its own rule via the API and deletes it in afterEach,
 * making tests fully independent and safe to run in parallel with other files.
 */

test.describe('Rule History Diff Timeline', () => {
  let ruleDetailPage: RuleDetailPage;
  let historyPage: RuleHistoryPage;
  let testRuleId: number;

  test.beforeEach(async ({ page, request }) => {
    ruleDetailPage = new RuleDetailPage(page);
    historyPage = new RuleHistoryPage(page);

    const resp = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
      data: {
        rid: `E2E_HISTORY_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        description: 'E2E test rule for history tests',
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

  /**
   * Helper: ensures the rule has at least two revisions by editing twice,
   * so the history page has at least one diff to display.
   */
  async function ensureMultipleRevisions(page: any): Promise<void> {
    await ruleDetailPage.goto(testRuleId);
    await ruleDetailPage.waitForRuleToLoad();

    const originalDescription = await ruleDetailPage.getDescription();

    // First edit: change description
    await ruleDetailPage.clickEdit();
    await ruleDetailPage.setDescription('History test edit ' + Date.now());
    await Promise.all([
      page.waitForResponse((resp: any) => resp.url().includes('/api/v2/rules/') && resp.request().method() === 'PUT'),
      ruleDetailPage.clickSave()
    ]);
    await ruleDetailPage.waitForSaveSuccess();

    // Second edit: restore original (creates another revision)
    await ruleDetailPage.clickEdit();
    await ruleDetailPage.setDescription(originalDescription);
    await Promise.all([
      page.waitForResponse((resp: any) => resp.url().includes('/api/v2/rules/') && resp.request().method() === 'PUT'),
      ruleDetailPage.clickSave()
    ]);
    await ruleDetailPage.waitForSaveSuccess();
  }

  test.describe('Navigation to History Page', () => {
    test('should navigate to history page via "Visualize history" link', async ({ page }) => {
      await ensureMultipleRevisions(page);

      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      // The "Visualize history" link should be visible
      const visualizeLink = page.locator('a:has-text("Visualize history")');
      await expect(visualizeLink).toBeVisible();

      // Click it and verify navigation
      await visualizeLink.click();
      await expect(page).toHaveURL(new RegExp(`/rules/${testRuleId}/history`));
    });

    test('should load history page via direct URL', async ({ page }) => {
      await ensureMultipleRevisions(page);

      await historyPage.goto(testRuleId);
      await historyPage.waitForHistoryToLoad();

      await expect(historyPage.pageTitle).toBeVisible();
    });
  });

  test.describe('History Page Content', () => {
    test('should display the page title with rule ID', async ({ page }) => {
      await ensureMultipleRevisions(page);

      await historyPage.goto(testRuleId);
      await historyPage.waitForHistoryToLoad();

      await expect(historyPage.pageTitle).toBeVisible();
    });

    test('should display the legend with Added and Removed labels', async ({ page }) => {
      await ensureMultipleRevisions(page);

      await historyPage.goto(testRuleId);
      await historyPage.waitForHistoryToLoad();

      await expect(page.locator('text=Added')).toBeVisible();
      await expect(page.locator('text=Removed')).toBeVisible();
    });

    test('should display at least one diff card', async ({ page }) => {
      await ensureMultipleRevisions(page);

      await historyPage.goto(testRuleId);
      await historyPage.waitForHistoryToLoad();

      const cardCount = await historyPage.getDiffCardCount();
      expect(cardCount).toBeGreaterThan(0);
    });

    test('should show "Current" label on the most recent diff card', async ({ page }) => {
      await ensureMultipleRevisions(page);

      await historyPage.goto(testRuleId);
      await historyPage.waitForHistoryToLoad();

      // First card (newest first) should mention "Current"
      const firstCard = historyPage.diffCards.first();
      await expect(firstCard).toContainText('Current');
    });

    test('should show description change indicator when description differs', async ({ page }) => {
      await ensureMultipleRevisions(page);

      await historyPage.goto(testRuleId);
      await historyPage.waitForHistoryToLoad();

      // At least one card should show the description changed indicator
      // (since ensureMultipleRevisions changes the description)
      await expect(historyPage.descriptionChangeIndicator.first()).toBeVisible();
    });
  });

  test.describe('Navigation Back', () => {
    test('should navigate back to rule detail via "Back to rule" link', async ({ page }) => {
      await ensureMultipleRevisions(page);

      await historyPage.goto(testRuleId);
      await historyPage.waitForHistoryToLoad();

      await historyPage.clickBackToRule();
      await expect(page).toHaveURL(new RegExp(`/rules/${testRuleId}$`));
    });

    test('should navigate back via breadcrumb rule link', async ({ page }) => {
      await ensureMultipleRevisions(page);

      await historyPage.goto(testRuleId);
      await historyPage.waitForHistoryToLoad();

      await historyPage.clickBreadcrumbRule();
      await expect(page).toHaveURL(new RegExp(`/rules/${testRuleId}$`));
    });

    test('should navigate back to all rules via breadcrumb', async ({ page }) => {
      await ensureMultipleRevisions(page);

      await historyPage.goto(testRuleId);
      await historyPage.waitForHistoryToLoad();

      await historyPage.breadcrumb.locator('a:has-text("All Rules")').click();
      await expect(page).toHaveURL(/\/rules/);
    });
  });

  test.describe('Error Handling', () => {
    test('should show error for non-existent rule history page', async ({ page }) => {
      await historyPage.goto(999999);

      await historyPage.waitForHistoryToLoad();
      await expect(historyPage.errorMessage).toBeVisible({ timeout: 10000 });
    });
  });
});
