import { test, expect } from '../support/fixtures';
import { SettingsPage } from '../pages/settings.page';
import { expectRuntimeSettingsRestored, getRuntimeSettings } from '../support/api-helpers';
import { SETTINGS_TAG, STATEFUL_TAG } from '../support/tags';

test.describe(`Runtime Settings Auto-Promote ${STATEFUL_TAG} ${SETTINGS_TAG}`, () => {
  test('shows the active-rule auto-promotion control and saves current values', async ({ page, request }) => {
    const originalSettings = await getRuntimeSettings(request);
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
    await expectRuntimeSettingsRestored(request, originalSettings);
  });
});
