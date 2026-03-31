import { expect, test } from '@playwright/test';
import { DashboardRuleActivityPage } from '../pages/dashboard-rule-activity.page';

test.describe('Dashboard Rule Activity', () => {
  let dashboardPage: DashboardRuleActivityPage;

  test.beforeEach(async ({ page }) => {
    dashboardPage = new DashboardRuleActivityPage(page);
  });

  test('should display most and least firing rule cards', async () => {
    const responsePromise = dashboardPage.waitForRuleActivityResponse('6h');
    await dashboardPage.goto();
    const response = await responsePromise;

    expect(response.ok()).toBeTruthy();
    await expect(dashboardPage.mostFiringCard).toBeVisible();
    await expect(dashboardPage.leastFiringCard).toBeVisible();
    await expect(dashboardPage.mostFiringHeading).toBeVisible();
    await expect(dashboardPage.leastFiringHeading).toBeVisible();
    await expect(dashboardPage.explanatoryNote).toBeVisible();
    await expect(dashboardPage.mostFiringState.first()).toBeVisible();
    await expect(dashboardPage.leastFiringState.first()).toBeVisible();
  });

  test('should link ranked rules to the rule detail page when rows are present', async () => {
    const responsePromise = dashboardPage.waitForRuleActivityResponse('6h');
    await dashboardPage.goto();
    const response = await responsePromise;

    expect(response.ok()).toBeTruthy();

    if (await dashboardPage.leastFiringLinks.count()) {
      await expect(dashboardPage.leastFiringLinks.first()).toHaveAttribute('href', /\/rules\/\d+$/);
      return;
    }

    if (await dashboardPage.mostFiringLinks.count()) {
      await expect(dashboardPage.mostFiringLinks.first()).toHaveAttribute('href', /\/rules\/\d+$/);
    }
  });

  test('should refetch rule activity when the time range changes', async () => {
    await dashboardPage.goto();
    await expect(dashboardPage.timeRangeSelect).toHaveValue('6h');

    const responsePromise = dashboardPage.waitForRuleActivityResponse('1h');
    await dashboardPage.selectTimeRange('1h');
    const response = await responsePromise;

    expect(response.ok()).toBeTruthy();
    await expect(dashboardPage.timeRangeSelect).toHaveValue('1h');
    await expect(dashboardPage.mostFiringCard).toBeVisible();
    await expect(dashboardPage.leastFiringCard).toBeVisible();
  });
});
