import { test, expect } from '@playwright/test';
import { SettingsPage } from '../pages/settings.page';

test.describe('Runtime Settings Auto-Promote', () => {
  test('shows the active-rule auto-promotion control and saves current values', async ({ page }) => {
    const settingsPage = new SettingsPage(page);
    await settingsPage.goto();
    await settingsPage.waitForPageToLoad();

    await expect(settingsPage.autoPromoteActiveRuleUpdatesCheckbox).toBeVisible();

    const currentLookback = await settingsPage.getLookbackDays();
    const currentAutoPromoteValue = await settingsPage.isAutoPromoteActiveRuleUpdatesEnabled();

    await settingsPage.setLookbackDays(currentLookback);
    await settingsPage.setAutoPromoteActiveRuleUpdates(currentAutoPromoteValue);
    await settingsPage.save();

    await expect(settingsPage.successMessage).toBeVisible();
  });
});
