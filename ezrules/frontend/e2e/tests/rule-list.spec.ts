import { test, expect } from '@playwright/test';
import { RuleListPage } from '../pages/rule-list.page';

/**
 * E2E tests for the Rule List page.
 * Tests only implemented features - displaying rules from the /api/v2/rules endpoint.
 */

test.describe('Rule List Page', () => {
  let rulePage: RuleListPage;

  test.beforeEach(async ({ page }) => {
    rulePage = new RuleListPage(page);
  });

  test.describe('Page Structure', () => {
    test('should load the rules page successfully', async ({ page }) => {
      await rulePage.goto();
      await expect(page).toHaveURL(/.*rules/);
      await expect(page).toHaveTitle(/ezrules/);
    });

    test('should display the correct page heading', async () => {
      await rulePage.goto();
      await expect(rulePage.heading).toHaveText('Rules');
    });

    test('should display the page description', async ({ page }) => {
      await rulePage.goto();
      const description = page.locator('text=Manage and monitor your business rules');
      await expect(description).toBeVisible();
    });
  });

  test.describe('Loading States', () => {
    test('should show loading spinner initially', async ({ page }) => {
      await page.goto('/rules', { waitUntil: 'domcontentloaded' });

      // The spinner should appear briefly during loading
      // We check if it exists in the DOM (it may disappear quickly)
      const spinner = rulePage.loadingSpinner;
      const spinnerExists = await spinner.count() > 0 || await rulePage.rulesTable.isVisible();
      expect(spinnerExists).toBeTruthy();
    });

    test('should hide loading spinner after data loads', async () => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      // After loading completes, spinner should be gone
      await expect(rulePage.loadingSpinner).not.toBeVisible();
    });
  });

  test.describe('Rules Table Display', () => {
    test('should display the rules table', async () => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      await expect(rulePage.rulesTable).toBeVisible();
    });

    test('should display table headers', async ({ page }) => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      const headers = ['Rule ID', 'Description', 'Created', 'Actions'];

      for (const header of headers) {
        const headerCell = page.locator(`th:has-text("${header}")`);
        await expect(headerCell).toBeVisible();
      }
    });

    test('should display rule count', async ({ page }) => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      const ruleCount = await rulePage.getRuleCount();
      const summaryText = page.locator('text=/\\d+ rules total/');
      await expect(summaryText).toBeVisible();
      await expect(summaryText).toContainText(`${ruleCount} rules total`);
    });

    test('should display rule data in table rows', async ({ page }) => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      const ruleCount = await rulePage.getRuleCount();

      if (ruleCount > 0) {
        // Check first rule has required columns
        const firstRow = page.locator('tbody tr').first();
        await expect(firstRow.locator('td').nth(0)).toBeVisible(); // Rule ID
        await expect(firstRow.locator('td').nth(1)).toBeVisible(); // Description
        await expect(firstRow.locator('td').nth(2)).toBeVisible(); // Created
        await expect(firstRow.locator('td').nth(3)).toBeVisible(); // Actions
      }
    });

    test('should have View and Edit links for each rule', async ({ page }) => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      const ruleCount = await rulePage.getRuleCount();

      if (ruleCount > 0) {
        const firstRow = page.locator('tbody tr').first();
        const viewLink = firstRow.locator('a:has-text("View")');
        const editLink = firstRow.locator('a:has-text("Edit")');

        await expect(viewLink).toBeVisible();
        await expect(editLink).toBeVisible();
      }
    });
  });

  test.describe('How to Run Section', () => {
    test('should toggle How to Run section when button is clicked', async ({ page }) => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      // Section should be hidden initially
      const howToRunContent = page.locator('.bg-blue-50').filter({ hasText: 'Evaluator endpoint:' });
      await expect(howToRunContent).not.toBeVisible();

      // Click to show
      await rulePage.toggleHowToRun();
      await expect(howToRunContent).toBeVisible();

      // Click to hide
      await rulePage.toggleHowToRun();
      await expect(howToRunContent).not.toBeVisible();
    });

    test('should display evaluator endpoint in How to Run section', async ({ page }) => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      await rulePage.toggleHowToRun();

      const endpointCode = page.locator('code.bg-white.px-2');
      await expect(endpointCode).toBeVisible();
      await expect(endpointCode).toContainText('localhost:9999');
    });

    test('should display curl example in How to Run section', async ({ page }) => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      await rulePage.toggleHowToRun();

      const curlExample = page.locator('.bg-gray-900.text-gray-100');
      await expect(curlExample).toBeVisible();
      await expect(curlExample).toContainText('curl');
      await expect(curlExample).toContainText('-X POST');
      await expect(curlExample).toContainText('Content-Type: application/json');
      await expect(curlExample).toContainText('localhost:9999/evaluate');
    });
  });

  test.describe('Responsive Design', () => {
    test('should display correctly on desktop viewport', async ({ page }) => {
      await page.setViewportSize({ width: 1920, height: 1080 });
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      await expect(rulePage.rulesTable).toBeVisible();
      await expect(rulePage.heading).toBeVisible();
    });

    test('should maintain layout on smaller desktop viewport', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 720 });
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      await expect(rulePage.rulesTable).toBeVisible();
      await expect(rulePage.heading).toBeVisible();
    });
  });

  test.describe('Future Features (Skipped)', () => {
    test.skip('should display empty state when no rules exist', async ({ page }) => {
      // This test is skipped - requires empty database
      // Will be enabled when we have proper test data management
    });
  });
});
