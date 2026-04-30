import { expect, test } from '@playwright/test';
import { AlertsPage } from '../pages/alerts.page';

test.describe('Alerts', () => {
  test('creates an outcome spike alert rule and shows notification controls', async ({ page }) => {
    const alertsPage = new AlertsPage(page);
    await alertsPage.goto();
    await alertsPage.waitForLoad();
    await expect(alertsPage.heading).toHaveText('Alerts');
    await expect(alertsPage.outcomeSelect).toContainText('CANCEL');
    const outcomeOptions = await alertsPage.outcomeSelect.locator('option').allTextContents();
    expect(outcomeOptions.map(option => option.trim())).toEqual(expect.arrayContaining(['CANCEL', 'HOLD', 'RELEASE']));

    const name = `CANCEL spike ${Date.now()}`;
    await alertsPage.createRule(name, 'CANCEL', 50);
    await expect(page.locator('text=Alert rule created.')).toBeVisible();
    await expect(page.locator('li').filter({ hasText: name })).toBeVisible();

    await page.goto('/dashboard');
    await expect(page.locator('[data-testid="notification-bell"]')).toBeVisible();
    await expect(page.locator('a[href="/alerts"]')).toBeVisible();
  });
});
