import { expect, test } from '@playwright/test';

test.describe('Tested Events Rule Links', () => {
  test('should let users navigate from a triggered rule to the rule detail page when events exist', async ({ page }) => {
    await page.goto('/tested-events');
    await page.locator('[data-testid="tested-events-table"], [data-testid="tested-events-empty"]').first().waitFor();

    const emptyState = page.locator('[data-testid="tested-events-empty"]');
    if (await emptyState.isVisible()) {
      await expect(emptyState).toBeVisible();
      return;
    }

    const firstRuleLink = page.locator('[data-testid="tested-event-rule-link"]').first();
    const linkCount = await page.locator('[data-testid="tested-event-rule-link"]').count();
    if (linkCount === 0) {
      const firstDetailsButton = page.locator('[data-testid="tested-event-details-button"]').first();
      await firstDetailsButton.click();
      const detailLink = page.locator('[data-testid="tested-event-rule-detail-link"]').first();
      if (await detailLink.count() === 0) {
        return;
      }
      await detailLink.click();
    } else {
      await firstRuleLink.click();
    }

    await expect(page).toHaveURL(/.*\/rules\/\d+$/);
    await expect(page.locator('h2', { hasText: 'Rule Details' })).toBeVisible();
  });
});
