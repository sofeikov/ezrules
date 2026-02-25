import { readFileSync } from 'fs';
import { join } from 'path';
import { test, expect } from '@playwright/test';
import { RuleDetailPage } from '../pages/rule-detail.page';

const API_BASE = 'http://localhost:8888';

/** Read the JWT access token from the saved auth state file. */
function getAuthToken(): string {
  const state = JSON.parse(readFileSync(join(__dirname, '../.auth/user.json'), 'utf-8'));
  const origin = state.origins?.find((o: any) => o.origin === 'http://localhost:4200');
  return origin?.localStorage?.find((e: any) => e.name === 'ezrules_access_token')?.value ?? '';
}

/**
 * E2E tests for the Rule Revision navigation functionality.
 * Tests that clicking a revision link displays the historical rule in read-only mode.
 *
 * Each test creates its own rule via the API and deletes it in afterEach,
 * making tests fully independent and safe to run in parallel with other files.
 */

test.describe('Rule Revision Navigation', () => {
  let ruleDetailPage: RuleDetailPage;
  let testRuleId: number;

  test.beforeEach(async ({ page, request }) => {
    ruleDetailPage = new RuleDetailPage(page);

    const resp = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
      data: {
        rid: `E2E_REVISION_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        description: 'E2E test rule for revision tests',
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
});
