import { expect, test } from '@playwright/test';

test.describe('Tested Events Refresh', () => {
  test('should show a refresh action on the tested events page', async ({ page }) => {
    await page.goto('/tested-events');
    await page.locator('[data-testid="tested-events-table"], [data-testid="tested-events-empty"]').first().waitFor();

    const refreshButton = page.locator('[data-testid="tested-events-refresh-button"]');
    await expect(refreshButton).toBeVisible();
    await expect(refreshButton).toContainText('Refresh');
  });
});
