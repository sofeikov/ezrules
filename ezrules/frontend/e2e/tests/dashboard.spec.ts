import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/dashboard.page';

/**
 * E2E tests for the Dashboard page.
 */
test.describe('Dashboard Page', () => {
  let dashboardPage: DashboardPage;

  test.beforeEach(async ({ page }) => {
    dashboardPage = new DashboardPage(page);
  });

  test.describe('Page Structure', () => {
    test('should load the dashboard page successfully', async ({ page }) => {
      await dashboardPage.goto();
      await expect(page).toHaveURL(/.*dashboard/);
    });

    test('should display the correct heading', async () => {
      await dashboardPage.goto();
      await expect(dashboardPage.heading).toHaveText('Dashboard');
    });

    test('should display the page description', async ({ page }) => {
      await dashboardPage.goto();
      const description = page.locator('text=Overview of transaction monitoring activity');
      await expect(description).toBeVisible();
    });

    test('should be reachable from sidebar navigation', async ({ page }) => {
      await page.goto('/rules');
      const dashboardLink = page.locator('a:has-text("Dashboard")');
      await expect(dashboardLink).toBeVisible();
      await dashboardLink.click();
      await expect(page).toHaveURL(/.*dashboard/);
      await expect(dashboardPage.heading).toHaveText('Dashboard');
    });
  });

  test.describe('Metric Card', () => {
    test('should display the Active Rules label', async () => {
      await dashboardPage.goto();
      await dashboardPage.waitForPageToLoad();
      await expect(dashboardPage.activeRulesLabel).toBeVisible();
    });

    test('should display a numeric active rules count', async () => {
      await dashboardPage.goto();
      const value = await dashboardPage.getActiveRulesCount();
      const num = parseInt(value, 10);
      expect(isNaN(num)).toBe(false);
      expect(num).toBeGreaterThanOrEqual(0);
    });
  });

  test.describe('Transaction Volume Section', () => {
    test('should display the Transaction Volume heading', async () => {
      await dashboardPage.goto();
      await dashboardPage.waitForPageToLoad();
      await expect(dashboardPage.transactionVolumeHeading).toBeVisible();
    });
  });

  test.describe('Rule Outcomes Section', () => {
    test('should display the Rule Outcomes Over Time heading', async () => {
      await dashboardPage.goto();
      await dashboardPage.waitForPageToLoad();
      await expect(dashboardPage.outcomesHeading).toBeVisible();
    });
  });

  test.describe('Time Range Selector', () => {
    test('should display the time range selector', async () => {
      await dashboardPage.goto();
      await dashboardPage.waitForPageToLoad();
      await expect(dashboardPage.timeRangeSelect).toBeVisible();
    });

    test('should have all expected time range options', async ({ page }) => {
      await dashboardPage.goto();
      await dashboardPage.waitForPageToLoad();
      const options = page.locator('select option');
      const values = await options.evaluateAll((els: HTMLOptionElement[]) => els.map(el => el.value));
      expect(values).toContain('1h');
      expect(values).toContain('6h');
      expect(values).toContain('12h');
      expect(values).toContain('24h');
      expect(values).toContain('30d');
    });

    test('should update when time range is changed to 1h', async () => {
      await dashboardPage.goto();
      await dashboardPage.waitForPageToLoad();

      await dashboardPage.selectTimeRange('1h');

      const selectedValue = await dashboardPage.timeRangeSelect.inputValue();
      expect(selectedValue).toBe('1h');
    });

    test('should update when time range is changed to 30d', async () => {
      await dashboardPage.goto();
      await dashboardPage.waitForPageToLoad();

      await dashboardPage.selectTimeRange('30d');

      const selectedValue = await dashboardPage.timeRangeSelect.inputValue();
      expect(selectedValue).toBe('30d');
    });
  });
});
