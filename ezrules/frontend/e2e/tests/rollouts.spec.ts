import { expect, test } from '@playwright/test';
import { RolloutsPage } from '../pages/rollouts.page';

test.describe('Rule Rollouts Page', () => {
  let rolloutsPage: RolloutsPage;

  test.beforeEach(async ({ page }) => {
    rolloutsPage = new RolloutsPage(page);
  });

  test('should load the rollout page successfully', async ({ page }) => {
    await rolloutsPage.goto();
    await expect(page).toHaveURL(/.*rule-rollouts/);
    await expect(page).toHaveTitle(/ezrules/);
  });

  test('should display the correct page heading', async () => {
    await rolloutsPage.goto();
    await expect(rolloutsPage.heading).toHaveText('Rule Rollouts');
  });

  test('should render either empty state or active rollout table', async () => {
    await rolloutsPage.goto();
    await rolloutsPage.waitForLoad();

    const emptyVisible = await rolloutsPage.emptyState.isVisible().catch(() => false);
    const tableVisible = await rolloutsPage.rolloutsTable.isVisible().catch(() => false);
    expect(emptyVisible || tableVisible).toBeTruthy();
  });

  test('should be accessible from the sidebar', async ({ page }) => {
    await page.goto('/rules');
    const link = page.locator('a[href="/rule-rollouts"]');
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/.*rule-rollouts/);
  });

  test('promote dialog cancel button closes dialog when a rollout exists', async () => {
    await rolloutsPage.goto();
    await rolloutsPage.waitForLoad();

    const rolloutCount = await rolloutsPage.getRolloutCount();
    if (rolloutCount === 0) {
      return;
    }

    await rolloutsPage.clickPromoteButton(0);
    await expect(rolloutsPage.promoteDialog).toBeVisible();
    await rolloutsPage.clickCancelPromoteButton();
    await expect(rolloutsPage.promoteDialog).not.toBeVisible();
  });
});
