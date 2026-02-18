import { test, expect } from '@playwright/test';
import { AuditTrailPage } from '../pages/audit-trail.page';

/**
 * E2E tests for the Field Type History section in the Audit Trail page.
 */
test.describe('Audit Trail - Field Type History Section', () => {
  let auditTrailPage: AuditTrailPage;

  test.beforeEach(async ({ page }) => {
    auditTrailPage = new AuditTrailPage(page);
  });

  test('should display the Field Type History accordion heading', async () => {
    await auditTrailPage.goto();
    await auditTrailPage.waitForPageToLoad();
    await expect(auditTrailPage.fieldTypeHistoryHeading).toBeVisible();
  });

  test('should show Field Type History section collapsed by default', async () => {
    await auditTrailPage.goto();
    await auditTrailPage.waitForPageToLoad();
    await expect(auditTrailPage.fieldTypeHistoryTable).not.toBeVisible();
  });

  test('should expand Field Type History section on click', async () => {
    await auditTrailPage.goto();
    await auditTrailPage.waitForPageToLoad();
    await auditTrailPage.expandSection('fieldTypes');
    const ftContent = auditTrailPage.fieldTypeHistoryAccordion.locator('..').locator('div').last();
    await expect(ftContent).toBeVisible();
  });

  test('should display correct column headers for field type history when expanded with data', async () => {
    await auditTrailPage.goto();
    await auditTrailPage.waitForPageToLoad();
    await auditTrailPage.expandSection('fieldTypes');
    const rowCount = await auditTrailPage.getFieldTypeHistoryRowCount();
    if (rowCount > 0) {
      const headers = await auditTrailPage.getFieldTypeHistoryColumnHeaders();
      expect(headers).toContain('Field Name');
      expect(headers).toContain('Type');
      expect(headers).toContain('Action');
      expect(headers).toContain('Changed By');
      expect(headers).toContain('Changed');
    }
  });

  test('should show empty message when no field type history entries exist', async () => {
    await auditTrailPage.goto();
    await auditTrailPage.waitForPageToLoad();
    await auditTrailPage.expandSection('fieldTypes');
    const rowCount = await auditTrailPage.getFieldTypeHistoryRowCount();
    if (rowCount === 0) {
      const emptyMsg = auditTrailPage.fieldTypeHistoryAccordion.locator('..').locator('text=No field type history entries found.');
      await expect(emptyMsg).toBeVisible();
    }
  });
});
