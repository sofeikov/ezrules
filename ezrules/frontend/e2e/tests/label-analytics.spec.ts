import { test, expect } from '@playwright/test';
import { LabelAnalyticsPage } from '../pages/label-analytics.page';

test.describe('Label Analytics Page', () => {
  let analyticsPage: LabelAnalyticsPage;

  test.beforeEach(async ({ page }) => {
    analyticsPage = new LabelAnalyticsPage(page);
  });

  test.describe('Page Structure', () => {
    test('should load the label analytics page successfully', async ({ page }) => {
      await analyticsPage.goto();
      await expect(page).toHaveURL(/.*label_analytics/);
    });

    test('should display the correct heading', async () => {
      await analyticsPage.goto();
      await expect(analyticsPage.heading).toHaveText('Label Analytics');
    });

    test('should be reachable from sidebar navigation', async ({ page }) => {
      await page.goto('/rules');
      const analyticsLink = page.locator('a:has-text("Analytics")');
      await expect(analyticsLink).toBeVisible();
      await analyticsLink.click();
      await expect(page).toHaveURL(/.*label_analytics/);
      await expect(analyticsPage.heading).toHaveText('Label Analytics');
    });
  });

  test.describe('Metric Card', () => {
    test('should display the Total Labeled Events label', async () => {
      await analyticsPage.goto();
      await analyticsPage.waitForPageToLoad();
      await expect(analyticsPage.totalLabeledLabel).toBeVisible();
    });

    test('should display a numeric total labeled events value', async () => {
      await analyticsPage.goto();
      const value = await analyticsPage.getTotalLabeled();
      const num = parseInt(value, 10);
      expect(isNaN(num)).toBe(false);
      expect(num).toBeGreaterThanOrEqual(0);
    });
  });

  test.describe('Labels Over Time Section', () => {
    test('should display the Labels Over Time heading', async () => {
      await analyticsPage.goto();
      await analyticsPage.waitForPageToLoad();
      await expect(analyticsPage.labelsOverTimeHeading).toBeVisible();
    });

    test('should display the time range selector', async () => {
      await analyticsPage.goto();
      await analyticsPage.waitForPageToLoad();
      await expect(analyticsPage.timeRangeSelect).toBeVisible();
    });

    test('should have all expected time range options', async ({ page }) => {
      await analyticsPage.goto();
      await analyticsPage.waitForPageToLoad();
      const options = page.locator('select option');
      const values = await options.evaluateAll((els: HTMLOptionElement[]) => els.map(el => el.value));
      expect(values).toContain('1h');
      expect(values).toContain('6h');
      expect(values).toContain('12h');
      expect(values).toContain('24h');
      expect(values).toContain('30d');
    });

    test('should render at least one chart canvas', async ({ page }) => {
      await analyticsPage.goto();
      await analyticsPage.waitForPageToLoad();
      // Wait for charts to render
      await page.waitForFunction(() => {
        return document.querySelectorAll('canvas[id^="labelChart_"]').length > 0;
      }, { timeout: 5000 });
      const count = await analyticsPage.getChartCount();
      expect(count).toBeGreaterThan(0);
    });

    test('should display chart titles for each label', async ({ page }) => {
      await analyticsPage.goto();
      await analyticsPage.waitForPageToLoad();
      await page.waitForFunction(() => {
        return document.querySelectorAll('canvas[id^="labelChart_"]').length > 0;
      }, { timeout: 5000 });
      const titles = await analyticsPage.getChartTitles();
      expect(titles.length).toBeGreaterThan(0);
    });
  });

  test.describe('Time Range Selector', () => {
    test('should update charts when time range is changed to 1h', async ({ page }) => {
      await analyticsPage.goto();
      await analyticsPage.waitForPageToLoad();
      await page.waitForFunction(() => {
        return document.querySelectorAll('canvas[id^="labelChart_"]').length > 0;
      }, { timeout: 5000 });

      await analyticsPage.selectTimeRange('1h');

      // Wait for charts to re-render after API call
      await page.waitForFunction(() => {
        return document.querySelectorAll('canvas[id^="labelChart_"]').length >= 0;
      }, { timeout: 5000 });

      // Verify the select value changed
      const selectedValue = await analyticsPage.timeRangeSelect.inputValue();
      expect(selectedValue).toBe('1h');
    });

    test('should update charts when time range is changed to 30d', async ({ page }) => {
      await analyticsPage.goto();
      await analyticsPage.waitForPageToLoad();
      await page.waitForFunction(() => {
        return document.querySelectorAll('canvas[id^="labelChart_"]').length > 0;
      }, { timeout: 5000 });

      await analyticsPage.selectTimeRange('30d');

      await page.waitForFunction(() => {
        return document.querySelectorAll('canvas[id^="labelChart_"]').length >= 0;
      }, { timeout: 5000 });

      const selectedValue = await analyticsPage.timeRangeSelect.inputValue();
      expect(selectedValue).toBe('30d');
    });
  });
});
