import { test, expect } from '@playwright/test';
import { RuleListPage } from '../pages/rule-list.page';
import { RuleDetailPage } from '../pages/rule-detail.page';

/**
 * E2E tests for the Rule Revision navigation functionality.
 * Tests that clicking a revision link displays the historical rule in read-only mode.
 */

test.describe('Rule Revision Navigation', () => {
  let ruleListPage: RuleListPage;
  let ruleDetailPage: RuleDetailPage;
  let testRuleId: number;

  test.beforeEach(async ({ page }) => {
    ruleListPage = new RuleListPage(page);
    ruleDetailPage = new RuleDetailPage(page);

    // Get a rule ID from the list to test with
    await ruleListPage.goto();
    await ruleListPage.waitForRulesToLoad();

    const ruleCount = await ruleListPage.getRuleCount();
    if (ruleCount === 0) {
      throw new Error('No rules available for testing. Please ensure test data exists.');
    }

    // Get the first rule's ID from the table
    const firstRow = page.locator('tbody tr').first();
    const viewLink = firstRow.locator('a:has-text("View")');
    const href = await viewLink.getAttribute('href');
    testRuleId = parseInt(href?.split('/').pop() || '1');
  });

  /**
   * Helper: ensures the rule has at least one revision by editing and saving it,
   * then restoring the original values. Returns the original description and logic.
   */
  async function ensureRevisionExists(page: any): Promise<{ originalDescription: string; originalLogic: string }> {
    await ruleDetailPage.goto(testRuleId);
    await ruleDetailPage.waitForRuleToLoad();

    const originalDescription = await ruleDetailPage.getDescription();
    const originalLogic = await ruleDetailPage.getLogic();

    // Edit and save to create a revision
    await ruleDetailPage.clickEdit();
    await ruleDetailPage.setDescription('Temp revision trigger ' + Date.now());

    await Promise.all([
      page.waitForResponse((resp: any) => resp.url().includes('/api/v2/rules/') && resp.request().method() === 'PUT'),
      ruleDetailPage.clickSave()
    ]);
    await ruleDetailPage.waitForSaveSuccess();

    // Restore original description
    await ruleDetailPage.clickEdit();
    await ruleDetailPage.setDescription(originalDescription);

    await Promise.all([
      page.waitForResponse((resp: any) => resp.url().includes('/api/v2/rules/') && resp.request().method() === 'PUT'),
      ruleDetailPage.clickSave()
    ]);
    await ruleDetailPage.waitForSaveSuccess();

    return { originalDescription, originalLogic };
  }

  test.describe('Revision Link Navigation', () => {
    test('should display revision links in the Other Rule Versions section', async ({ page }) => {
      await ensureRevisionExists(page);

      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.revisionsSection).toBeVisible();
      // At least one revision link should exist
      const linkCount = await ruleDetailPage.revisionLinks.count();
      expect(linkCount).toBeGreaterThan(0);
    });

    test('should navigate to revision page when clicking a revision link', async ({ page }) => {
      await ensureRevisionExists(page);

      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      // Click the first revision link
      await ruleDetailPage.clickRevision(0);

      // URL should match the revision pattern
      await expect(page).toHaveURL(/\/rules\/\d+\/revisions\/\d+/);
      await ruleDetailPage.waitForRuleToLoad();
    });

    test('revision links should use Angular routing (not full page reload)', async ({ page }) => {
      await ensureRevisionExists(page);

      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      // Get the href of the first revision link
      const revisionLink = ruleDetailPage.revisionLinks.first();
      const href = await revisionLink.getAttribute('href');

      // Should be an Angular route, not a Flask route
      expect(href).toMatch(/\/rules\/\d+\/revisions\/\d+/);
      expect(href).not.toMatch(/^\/rule\//);
    });
  });

  test.describe('Revision View Read-Only Mode', () => {
    test('should show revision banner when viewing a historical revision', async ({ page }) => {
      await ensureRevisionExists(page);

      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickRevision(0);
      await ruleDetailPage.waitForRuleToLoad();

      // Revision banner should be visible
      await expect(ruleDetailPage.revisionBanner).toBeVisible();
      await expect(ruleDetailPage.revisionBanner).toContainText('read-only');
    });

    test('should not show Edit Rule button in revision view', async ({ page }) => {
      await ensureRevisionExists(page);

      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickRevision(0);
      await ruleDetailPage.waitForRuleToLoad();

      // Edit button should not be visible
      await expect(ruleDetailPage.editButton).not.toBeVisible();
    });

    test('should hide the Other Rule Versions section in revision view', async ({ page }) => {
      await ensureRevisionExists(page);

      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickRevision(0);
      await ruleDetailPage.waitForRuleToLoad();

      // Revisions section should not be visible in revision view
      await expect(ruleDetailPage.revisionsSection).not.toBeVisible();
    });

    test('should display rule fields in read-only mode', async ({ page }) => {
      await ensureRevisionExists(page);

      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickRevision(0);
      await ruleDetailPage.waitForRuleToLoad();

      // Rule ID, description, and logic should be displayed
      const ruleId = await ruleDetailPage.getRuleId();
      expect(ruleId).toBeTruthy();

      const logic = await ruleDetailPage.getLogic();
      expect(logic.length).toBeGreaterThan(0);
    });
  });

  test.describe('Go to Latest Version', () => {
    test('should show "Go to latest version" link in the revision banner', async ({ page }) => {
      await ensureRevisionExists(page);

      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickRevision(0);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.goToLatestLink).toBeVisible();
    });

    test('should navigate back to latest rule when clicking "Go to latest version"', async ({ page }) => {
      await ensureRevisionExists(page);

      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickRevision(0);
      await ruleDetailPage.waitForRuleToLoad();

      // Click "Go to latest version"
      await ruleDetailPage.clickGoToLatest();

      // Should navigate back to the rule detail page (not a revision URL)
      await expect(page).toHaveURL(new RegExp(`/rules/${testRuleId}$`));
      await ruleDetailPage.waitForRuleToLoad();

      // Edit button should be visible again (latest view)
      await expect(ruleDetailPage.editButton).toBeVisible();

      // Revision banner should not be visible
      await expect(ruleDetailPage.revisionBanner).not.toBeVisible();
    });
  });

  test.describe('Direct URL Navigation', () => {
    test('should load revision page when navigating directly via URL', async ({ page }) => {
      await ensureRevisionExists(page);

      // Navigate directly to revision 1
      await ruleDetailPage.gotoRevision(testRuleId, 1);
      await ruleDetailPage.waitForRuleToLoad();

      // Should show revision banner
      await expect(ruleDetailPage.revisionBanner).toBeVisible();

      // URL should match
      await expect(page).toHaveURL(/\/rules\/\d+\/revisions\/1/);
    });

    test('should show error for non-existent revision', async ({ page }) => {
      // Navigate to a non-existent revision
      await ruleDetailPage.gotoRevision(testRuleId, 99999);

      // Should show error message
      await expect(ruleDetailPage.errorMessage).toBeVisible({ timeout: 10000 });
    });
  });

  test.describe('API Integration', () => {
    test('should fetch revision data from /api/v2/rules/:id/revisions/:rev endpoint', async ({ page }) => {
      await ensureRevisionExists(page);

      // Verify the API endpoint directly
      const response = await page.request.get(`http://localhost:8888/api/v2/rules/${testRuleId}/revisions/1`);
      expect(response.ok()).toBe(true);

      const data = await response.json();
      expect(data.r_id).toBe(testRuleId);
      expect(data.revision_number).toBe(1);
      expect(data.rid).toBeTruthy();
      expect(data.logic).toBeTruthy();
      expect(data.revisions).toEqual([]);
    });

    test('should return 404 for non-existent revision via API', async ({ page }) => {
      const response = await page.request.get(`http://localhost:8888/api/v2/rules/${testRuleId}/revisions/99999`);
      expect(response.ok()).toBe(false);
      expect(response.status()).toBe(404);
    });
  });
});
