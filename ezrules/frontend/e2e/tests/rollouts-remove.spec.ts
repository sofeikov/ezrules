import { expect, test } from '@playwright/test';
import { RolloutsPage } from '../pages/rollouts.page';

test.describe('Rule Rollouts Remove Dialog', () => {
  let rolloutsPage: RolloutsPage;

  test.beforeEach(async ({ page }) => {
    rolloutsPage = new RolloutsPage(page);
  });

  test('remove dialog cancel button closes dialog when a rollout exists', async () => {
    await rolloutsPage.goto();
    await rolloutsPage.waitForLoad();

    const rolloutCount = await rolloutsPage.getRolloutCount();
    if (rolloutCount === 0) {
      return;
    }

    await rolloutsPage.clickRemoveButton(0);
    await expect(rolloutsPage.removeDialog).toBeVisible();
    await expect(rolloutsPage.removeDialog).toContainText('clear the rollout comparison history');
    await rolloutsPage.clickCancelRemoveButton();
    await expect(rolloutsPage.removeDialog).not.toBeVisible();
  });
});
