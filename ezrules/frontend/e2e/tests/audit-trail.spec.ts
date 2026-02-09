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
      const headers = await auditTrailPage.getRuleHistoryColumnHeaders();
      expect(headers).toContain('Version');
      expect(headers).toContain('Rule ID');
      expect(headers).toContain('Description');
      expect(headers).toContain('Changed');
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
      const headers = await auditTrailPage.getConfigHistoryColumnHeaders();
      expect(headers).toContain('Version');
      expect(headers).toContain('Label');
      expect(headers).toContain('Changed');
    });
  });
});
