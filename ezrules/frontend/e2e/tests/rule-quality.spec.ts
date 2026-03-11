import { test, expect } from '@playwright/test';
import { RuleQualityPage } from '../pages/rule-quality.page';

test.describe('Rule Quality Page', () => {
  let ruleQualityPage: RuleQualityPage;

  test.beforeEach(async ({ page }) => {
    ruleQualityPage = new RuleQualityPage(page);
  });

  test('should load the rule quality page successfully', async ({ page }) => {
    await ruleQualityPage.goto();
    await expect(page).toHaveURL(/.*rule-quality/);
    await expect(ruleQualityPage.heading).toHaveText('Rule Quality');
  });

  test('should be reachable from sidebar navigation', async ({ page }) => {
    await page.goto('/dashboard');
    const ruleQualityLink = page.locator('a:has-text("Rule Quality")');
    await expect(ruleQualityLink).toBeVisible();
    await ruleQualityLink.click();

    await expect(page).toHaveURL(/.*rule-quality/);
    await expect(ruleQualityPage.heading).toHaveText('Rule Quality');
  });

  test('should show summary cards and pair metrics section', async () => {
    await ruleQualityPage.goto();
    await ruleQualityPage.waitForPageToLoad();

    await expect(ruleQualityPage.labeledEventsCardLabel).toBeVisible();
    await expect(ruleQualityPage.rulesAnalyzedCardLabel).toBeVisible();
    await expect(ruleQualityPage.pairMetricsHeading).toBeVisible();
  });

  test('should allow changing minimum support filter', async () => {
    await ruleQualityPage.goto();
    await ruleQualityPage.waitForPageToLoad();

    await ruleQualityPage.setMinSupport(3);
    await expect(ruleQualityPage.minSupportInput).toHaveValue('3');
  });

  test('should allow changing lookback days filter', async () => {
    await ruleQualityPage.goto();
    await ruleQualityPage.waitForPageToLoad();

    await ruleQualityPage.setLookbackDays(14);
    await expect(ruleQualityPage.lookbackDaysInput).toHaveValue('14');
  });

  test('should allow requesting a fresh snapshot report', async () => {
    await ruleQualityPage.goto();
    await ruleQualityPage.waitForPageToLoad();

    await expect(ruleQualityPage.refreshReportButton).toBeVisible();
    await ruleQualityPage.refreshReport();
    await ruleQualityPage.waitForPageToLoad();
  });

  test('should show pair rows or an explicit empty-state message', async () => {
    await ruleQualityPage.goto();
    await ruleQualityPage.waitForPageToLoad();

    const rowCount = await ruleQualityPage.getPairMetricRowCount();
    if (rowCount === 0) {
      await expect(ruleQualityPage.noDataMessage).toBeVisible();
    } else {
      expect(rowCount).toBeGreaterThan(0);
    }
  });

  test('should render rule references as links to rule detail pages', async ({ page }) => {
    await ruleQualityPage.goto();
    await ruleQualityPage.waitForPageToLoad();

    const linkCount = await ruleQualityPage.ruleLinks.count();
    if (linkCount === 0) {
      await expect(ruleQualityPage.noDataMessage).toBeVisible();
    } else {
      const firstLink = ruleQualityPage.ruleLinks.first();
      await expect(firstLink).toBeVisible();
      const href = await firstLink.getAttribute('href');
      expect(href).toMatch(/^\/rules\/\d+$/);

      await firstLink.click();
      await expect(page).toHaveURL(/\/rules\/\d+$/);
    }
  });
});
