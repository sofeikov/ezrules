import { expect, test } from '@playwright/test';
import { TestedEventsPage } from '../pages/tested-events.page';

test.describe('Tested Events Page', () => {
  let testedEventsPage: TestedEventsPage;

  test.beforeEach(async ({ page }) => {
    testedEventsPage = new TestedEventsPage(page);
  });

  test('should load the tested events page successfully', async ({ page }) => {
    await testedEventsPage.goto();
    await testedEventsPage.waitForPageToLoad();

    await expect(page).toHaveURL(/.*tested-events/);
    await expect(testedEventsPage.heading).toHaveText('Tested Events');
  });

  test('should be reachable from sidebar navigation', async ({ page }) => {
    await page.goto('/rules');

    const testedEventsLink = page.locator('a:has-text("Tested Events")');
    await expect(testedEventsLink).toBeVisible();
    await testedEventsLink.click();

    await expect(page).toHaveURL(/.*tested-events/);
    await expect(testedEventsPage.heading).toHaveText('Tested Events');
  });

  test('should show recent events or an empty state', async () => {
    await testedEventsPage.goto();
    await testedEventsPage.waitForPageToLoad();

    await expect(testedEventsPage.page.locator('#tested-events-limit option:checked')).toHaveText('50');

    const eventCount = await testedEventsPage.getEventCount();
    if (eventCount === 0) {
      await expect(testedEventsPage.emptyState).toBeVisible();
      return;
    }

    await expect(testedEventsPage.table).toBeVisible();
    expect(eventCount).toBeGreaterThan(0);
  });

  test('should expand event details when events exist', async () => {
    await testedEventsPage.goto();
    await testedEventsPage.waitForPageToLoad();

    const eventCount = await testedEventsPage.getEventCount();
    if (eventCount === 0) {
      await expect(testedEventsPage.emptyState).toBeVisible();
      return;
    }

    await testedEventsPage.expandFirstEvent();
    await expect(testedEventsPage.detailsPanels.first()).toBeVisible();
    await expect(testedEventsPage.detailsPanels.first()).toContainText('Triggered rules');
    await expect(testedEventsPage.detailsPanels.first()).toContainText('Event payload');
  });
});
