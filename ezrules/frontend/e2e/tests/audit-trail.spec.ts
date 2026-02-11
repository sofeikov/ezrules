import { test, expect } from '@playwright/test';
import { AuditTrailPage } from '../pages/audit-trail.page';

/**
 * E2E tests for the Audit Trail page.
 */
test.describe('Audit Trail Page', () => {
  let auditTrailPage: AuditTrailPage;

  test.beforeEach(async ({ page }) => {
    auditTrailPage = new AuditTrailPage(page);
  });

  test.describe('Page Structure', () => {
    test('should load the audit trail page successfully', async ({ page }) => {
      await auditTrailPage.goto();
      await expect(page).toHaveURL(/.*audit/);
    });

    test('should display the correct heading', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.heading).toHaveText('Audit Trail');
    });

    test('should display the page description', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.description).toBeVisible();
    });

    test('should be reachable from sidebar navigation', async ({ page }) => {
      await page.goto('/rules');
      const auditLink = page.locator('a:has-text("Audit Trail")');
      await expect(auditLink).toBeVisible();
      await auditLink.click();
      await expect(page).toHaveURL(/.*audit/);
      await expect(auditTrailPage.heading).toHaveText('Audit Trail');
    });
  });

  test.describe('Rule History Section', () => {
    test('should display the Rule History heading', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.ruleHistoryHeading).toBeVisible();
    });

    test('should display correct column headers for rule history', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      // Table only renders when there is history data
      const rowCount = await auditTrailPage.getRuleHistoryRowCount();
      if (rowCount > 0) {
        const headers = await auditTrailPage.getRuleHistoryColumnHeaders();
        expect(headers).toContain('Version');
        expect(headers).toContain('Rule ID');
        expect(headers).toContain('Description');
        expect(headers).toContain('Changed By');
        expect(headers).toContain('Changed');
      }
    });
  });

  test.describe('Rule History Links', () => {
    test('should have clickable links in Rule ID and Version columns', async ({ page }) => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      const rowCount = await auditTrailPage.getRuleHistoryRowCount();
      if (rowCount > 0) {
        // Rule ID column should link to the rule detail page
        const ruleIdLink = auditTrailPage.ruleHistoryTable.locator('tbody tr').first().locator('td').nth(1).locator('a');
        await expect(ruleIdLink).toBeVisible();
        const ruleIdHref = await ruleIdLink.getAttribute('href');
        expect(ruleIdHref).toMatch(/\/rules\/\d+/);

        // Version column should link to the specific revision
        const versionLink = auditTrailPage.ruleHistoryTable.locator('tbody tr').first().locator('td').first().locator('a');
        await expect(versionLink).toBeVisible();
        const versionHref = await versionLink.getAttribute('href');
        expect(versionHref).toMatch(/\/rules\/\d+\/revisions\/\d+/);
      }
    });

    test('should navigate to rule detail page when clicking Rule ID', async ({ page }) => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      const rowCount = await auditTrailPage.getRuleHistoryRowCount();
      if (rowCount > 0) {
        const ruleIdLink = auditTrailPage.ruleHistoryTable.locator('tbody tr').first().locator('td').nth(1).locator('a');
        await ruleIdLink.click();
        await expect(page).toHaveURL(/\/rules\/\d+$/);
      }
    });
  });

  test.describe('Configuration History Section', () => {
    test('should display the Configuration History heading', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.configHistoryHeading).toBeVisible();
    });

    test('should display correct column headers for config history', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      // Table only renders when there is history data
      const rowCount = await auditTrailPage.getConfigHistoryRowCount();
      if (rowCount > 0) {
        const headers = await auditTrailPage.getConfigHistoryColumnHeaders();
        expect(headers).toContain('Version');
        expect(headers).toContain('Label');
        expect(headers).toContain('Changed By');
        expect(headers).toContain('Changed');
      }
    });
  });
});
