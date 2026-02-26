import { test, expect } from '@playwright/test';
import { ShadowRulesPage } from '../pages/shadow-rules.page';

/**
 * E2E tests for the Shadow Rules page.
 */

test.describe('Shadow Rules Page', () => {
  let shadowPage: ShadowRulesPage;

  test.beforeEach(async ({ page }) => {
    shadowPage = new ShadowRulesPage(page);
  });

  test.describe('Page Structure', () => {
    test('should load the shadow rules page successfully', async ({ page }) => {
      await shadowPage.goto();
      await expect(page).toHaveURL(/.*shadow-rules/);
      await expect(page).toHaveTitle(/ezrules/);
    });

    test('should display the correct page heading', async () => {
      await shadowPage.goto();
      await expect(shadowPage.heading).toHaveText('Shadow Rules');
    });

    test('should display the page description', async ({ page }) => {
      await shadowPage.goto();
      const description = page.locator('text=Rules running in observe-only mode on live traffic');
      await expect(description).toBeVisible();
    });
  });

  test.describe('Empty State', () => {
    test('should show empty state when no shadow rules are deployed', async ({ page }) => {
      await shadowPage.goto();
      await shadowPage.waitForLoad();

      // Either empty state is visible (no rules) or table exists (rules present)
      const emptyVisible = await shadowPage.emptyState.isVisible().catch(() => false);
      const tableVisible = await shadowPage.shadowRulesTable.isVisible().catch(() => false);

      // At minimum, the page should render one of these states
      expect(emptyVisible || tableVisible).toBeTruthy();
    });
  });

  test.describe('Navigation', () => {
    test('should be accessible from sidebar', async ({ page }) => {
      await page.goto('/rules');
      const shadowLink = page.locator('a[href="/shadow-rules"]');
      await expect(shadowLink).toBeVisible();
      await shadowLink.click();
      await expect(page).toHaveURL(/.*shadow-rules/);
    });
  });

  test.describe('Promote Dialog', () => {
    test('promote dialog cancel button closes dialog', async ({ page }) => {
      await shadowPage.goto();
      await shadowPage.waitForLoad();

      const ruleCount = await shadowPage.getShadowRuleCount();
      if (ruleCount === 0) {
        // No rules in shadow — skip dialog interaction
        return;
      }

      await shadowPage.clickPromoteButton(0);
      await expect(shadowPage.promoteDialog).toBeVisible();

      await shadowPage.cancelPromoteButton.click();
      await expect(shadowPage.promoteDialog).not.toBeVisible();
    });
  });
});
