import { test, expect } from '@playwright/test';
import { AuditTrailPage } from '../pages/audit-trail.page';

/**
 * E2E tests for the Audit Trail page.
 * The page uses an accordion layout with collapsible sections.
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

  test.describe('Accordion Sections', () => {
    test('should display all seven accordion sections', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.ruleHistoryHeading).toBeVisible();
      await expect(auditTrailPage.configHistoryHeading).toBeVisible();
      await expect(auditTrailPage.userListHistoryHeading).toBeVisible();
      await expect(auditTrailPage.outcomeHistoryHeading).toBeVisible();
      await expect(auditTrailPage.labelHistoryHeading).toBeVisible();
      await expect(auditTrailPage.userAccountHistoryHeading).toBeVisible();
      await expect(auditTrailPage.rolePermissionHistoryHeading).toBeVisible();
    });

    test('should toggle Rule History section on click', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      // Initially collapsed - no table visible
      await expect(auditTrailPage.ruleHistoryTable).not.toBeVisible();
      // Expand
      await auditTrailPage.expandSection('rules');
      // Section content should now be visible (table or empty message)
      const ruleContent = auditTrailPage.ruleHistoryAccordion.locator('..').locator('div').last();
      await expect(ruleContent).toBeVisible();
    });

    test('should toggle Configuration History section on click', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.configHistoryTable).not.toBeVisible();
      await auditTrailPage.expandSection('config');
      const configContent = auditTrailPage.configHistoryAccordion.locator('..').locator('div').last();
      await expect(configContent).toBeVisible();
    });

    test('should toggle User List History section on click', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.userListHistoryTable).not.toBeVisible();
      await auditTrailPage.expandSection('userLists');
      const ulContent = auditTrailPage.userListHistoryAccordion.locator('..').locator('div').last();
      await expect(ulContent).toBeVisible();
    });

    test('should toggle Outcome History section on click', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.outcomeHistoryTable).not.toBeVisible();
      await auditTrailPage.expandSection('outcomes');
      const outcomeContent = auditTrailPage.outcomeHistoryAccordion.locator('..').locator('div').last();
      await expect(outcomeContent).toBeVisible();
    });

    test('should toggle Label History section on click', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.labelHistoryTable).not.toBeVisible();
      await auditTrailPage.expandSection('labels');
      const labelContent = auditTrailPage.labelHistoryAccordion.locator('..').locator('div').last();
      await expect(labelContent).toBeVisible();
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
      await auditTrailPage.expandSection('rules');
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
      await auditTrailPage.expandSection('rules');
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
      await auditTrailPage.expandSection('rules');
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
      await auditTrailPage.expandSection('config');
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

  test.describe('User List History Section', () => {
    test('should display the User List History heading', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.userListHistoryHeading).toBeVisible();
    });

    test('should display correct column headers for user list history', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await auditTrailPage.expandSection('userLists');
      const rowCount = await auditTrailPage.getUserListHistoryRowCount();
      if (rowCount > 0) {
        const headers = await auditTrailPage.getUserListHistoryColumnHeaders();
        expect(headers).toContain('List Name');
        expect(headers).toContain('Action');
        expect(headers).toContain('Details');
        expect(headers).toContain('Changed By');
        expect(headers).toContain('Changed');
      }
    });
  });

  test.describe('Outcome History Section', () => {
    test('should display the Outcome History heading', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.outcomeHistoryHeading).toBeVisible();
    });

    test('should display correct column headers for outcome history', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await auditTrailPage.expandSection('outcomes');
      const rowCount = await auditTrailPage.getOutcomeHistoryRowCount();
      if (rowCount > 0) {
        const headers = await auditTrailPage.getOutcomeHistoryColumnHeaders();
        expect(headers).toContain('Outcome');
        expect(headers).toContain('Action');
        expect(headers).toContain('Changed By');
        expect(headers).toContain('Changed');
      }
    });
  });

  test.describe('Label History Section', () => {
    test('should display the Label History heading', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.labelHistoryHeading).toBeVisible();
    });

    test('should display correct column headers for label history', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await auditTrailPage.expandSection('labels');
      const rowCount = await auditTrailPage.getLabelHistoryRowCount();
      if (rowCount > 0) {
        const headers = await auditTrailPage.getLabelHistoryColumnHeaders();
        expect(headers).toContain('Label');
        expect(headers).toContain('Action');
        expect(headers).toContain('Changed By');
        expect(headers).toContain('Changed');
      }
    });
  });

  test.describe('User Account History Section', () => {
    test('should display the User Account History heading', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.userAccountHistoryHeading).toBeVisible();
    });

    test('should toggle User Account History section on click', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.userAccountHistoryTable).not.toBeVisible();
      await auditTrailPage.expandSection('userAccounts');
      const uaContent = auditTrailPage.userAccountHistoryAccordion.locator('..').locator('div').last();
      await expect(uaContent).toBeVisible();
    });

    test('should display correct column headers for user account history', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await auditTrailPage.expandSection('userAccounts');
      const rowCount = await auditTrailPage.getUserAccountHistoryRowCount();
      if (rowCount > 0) {
        const headers = await auditTrailPage.getUserAccountHistoryColumnHeaders();
        expect(headers).toContain('Email');
        expect(headers).toContain('Action');
        expect(headers).toContain('Details');
        expect(headers).toContain('Changed By');
        expect(headers).toContain('Changed');
      }
    });
  });

  test.describe('Role & Permission History Section', () => {
    test('should display the Role & Permission History heading', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.rolePermissionHistoryHeading).toBeVisible();
    });

    test('should toggle Role & Permission History section on click', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.rolePermissionHistoryTable).not.toBeVisible();
      await auditTrailPage.expandSection('rolePermissions');
      const rpContent = auditTrailPage.rolePermissionHistoryAccordion.locator('..').locator('div').last();
      await expect(rpContent).toBeVisible();
    });

    test('should display correct column headers for role permission history', async () => {
      await auditTrailPage.goto();
      await auditTrailPage.waitForPageToLoad();
      await auditTrailPage.expandSection('rolePermissions');
      const rowCount = await auditTrailPage.getRolePermissionHistoryRowCount();
      if (rowCount > 0) {
        const headers = await auditTrailPage.getRolePermissionHistoryColumnHeaders();
        expect(headers).toContain('Role Name');
        expect(headers).toContain('Action');
        expect(headers).toContain('Details');
        expect(headers).toContain('Changed By');
        expect(headers).toContain('Changed');
      }
    });
  });
});
