import { test, expect } from '@playwright/test';
import { RuleListPage } from '../pages/rule-list.page';
import { RuleDetailPage } from '../pages/rule-detail.page';
import { RuleHistoryPage } from '../pages/rule-history.page';

/**
 * E2E tests for the Rule History (diff timeline) functionality.
 * Tests that the history page loads, displays diffs correctly,
 * and navigation works as expected.
 */

test.describe('Rule History Diff Timeline', () => {
  let ruleListPage: RuleListPage;
  let ruleDetailPage: RuleDetailPage;
  let historyPage: RuleHistoryPage;
  let testRuleId: number;

  test.beforeEach(async ({ page }) => {
    ruleListPage = new RuleListPage(page);
    ruleDetailPage = new RuleDetailPage(page);
    historyPage = new RuleHistoryPage(page);

    // Get a rule ID from the list
    await ruleListPage.goto();
    await ruleListPage.waitForRulesToLoad();

    const ruleCount = await ruleListPage.getRuleCount();
    if (ruleCount === 0) {
      throw new Error('No rules available for testing. Please ensure test data exists.');
    }

    const firstRow = page.locator('tbody tr').first();
    const viewLink = firstRow.locator('a:has-text("View")');
    const href = await viewLink.getAttribute('href');
    testRuleId = parseInt(href?.split('/').pop() || '1');
  });

  /**
   * Helper: ensures the rule has at least two revisions by editing twice,
   * so the history page has at least one diff to display.
   */
  async function ensureMultipleRevisions(page: any): Promise<void> {
    await ruleDetailPage.goto(testRuleId);
    await ruleDetailPage.waitForRuleToLoad();

    const originalDescription = await ruleDetailPage.getDescription();
    const originalLogic = await ruleDetailPage.getLogic();

    // First edit: change description
    await ruleDetailPage.clickEdit();
    await ruleDetailPage.setDescription('History test edit ' + Date.now());
    await Promise.all([
      page.waitForResponse((resp: any) => resp.url().includes('/api/rules/') && resp.request().method() === 'PUT'),
      ruleDetailPage.clickSave()
    ]);
    await ruleDetailPage.waitForSaveSuccess();

    // Second edit: restore original (creates another revision)
    await ruleDetailPage.clickEdit();
    await ruleDetailPage.setDescription(originalDescription);
    await Promise.all([
      page.waitForResponse((resp: any) => resp.url().includes('/api/rules/') && resp.request().method() === 'PUT'),
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

  test.describe('API Integration', () => {
    test('should fetch history from /api/rules/:id/history endpoint', async ({ page }) => {
      await ensureMultipleRevisions(page);

      const response = await page.request.get(`http://localhost:8888/api/rules/${testRuleId}/history`);
      expect(response.ok()).toBe(true);

      const data = await response.json();
      expect(data.r_id).toBe(testRuleId);
      expect(data.rid).toBeTruthy();
      expect(Array.isArray(data.history)).toBe(true);
      expect(data.history.length).toBeGreaterThan(0);

      // Last entry should be current
      const lastEntry = data.history[data.history.length - 1];
      expect(lastEntry.is_current).toBe(true);
    });

    test('should return 404 for non-existent rule via history API', async ({ page }) => {
      const response = await page.request.get('http://localhost:8888/api/rules/999999/history');
      expect(response.ok()).toBe(false);
      expect(response.status()).toBe(404);
    });

    test('should respect limit parameter on history API', async ({ page }) => {
      await ensureMultipleRevisions(page);

      const response = await page.request.get(`http://localhost:8888/api/rules/${testRuleId}/history?limit=1`);
      expect(response.ok()).toBe(true);

      const data = await response.json();
      // With limit=1, at most 1 revision + current = 2 entries
      expect(data.history.length).toBeLessThanOrEqual(2);
      // Last entry is always current
      expect(data.history[data.history.length - 1].is_current).toBe(true);
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
