import { test, expect } from '../support/fixtures';
import { SettingsPage } from '../pages/settings.page';
import {
  expectRuntimeSettingsRestored,
  getAIAuthoringSettings,
  getOutcomeHierarchy,
  getRuntimeSettings,
  restoreAIAuthoringSettings,
  restoreOutcomeHierarchy,
  restoreRuntimeSettings,
} from '../support/api-helpers';
import { SETTINGS_TAG, STATEFUL_TAG } from '../support/tags';

test.describe(`Settings Page ${STATEFUL_TAG} ${SETTINGS_TAG}`, () => {
  let settingsPage: SettingsPage;

  test.beforeEach(async ({ page }) => {
    settingsPage = new SettingsPage(page);
  });

  test('should load the settings page successfully', async ({ page }) => {
    await settingsPage.goto();
    await expect(page).toHaveURL(/.*settings/);
    await expect(settingsPage.heading).toHaveText('Settings');
  });

  test('should be reachable from settings sidebar section', async ({ page }) => {
    await page.goto('/dashboard');
    const settingsLink = page.locator('a:has-text("General")');
    await expect(settingsLink).toBeVisible();
    await settingsLink.click();

    await expect(page).toHaveURL(/.*settings/);
    await expect(settingsPage.heading).toHaveText('Settings');
  });

  test('should allow saving rule quality lookback setting', async () => {
    await settingsPage.goto();
    await settingsPage.waitForPageToLoad();

    const current = await settingsPage.getLookbackDays();
    await settingsPage.setLookbackDays(current);
    await settingsPage.save();

    await expect(settingsPage.successMessage).toBeVisible();
  });

  test('should allow choosing a neutral outcome and surface it in allowlist helper text', async ({ page, request }) => {
    const currentSettings = await getRuntimeSettings(request);
    try {
      await settingsPage.goto();
      await settingsPage.waitForPageToLoad();

      const originalNeutralOutcome = await settingsPage.getNeutralOutcome();
      const nextNeutralOutcome = originalNeutralOutcome === 'HOLD' ? 'RELEASE' : 'HOLD';

      await settingsPage.setNeutralOutcome(nextNeutralOutcome);
      await settingsPage.save();
      await expect(settingsPage.successMessage).toBeVisible();

      await page.goto('/rules/create');
      await page.locator('[data-testid="rule-lane-select"]').selectOption('allowlist');
      await expect(page.locator('text=They must return').first()).toContainText(
        `They must return !${nextNeutralOutcome}.`
      );
    } finally {
      await restoreRuntimeSettings(request, currentSettings);
      await expectRuntimeSettingsRestored(request, currentSettings);
    }
  });

  test('should allow adding and deleting curated rule quality pairs', async ({ page }) => {
    await settingsPage.goto();
    await settingsPage.waitForPageToLoad();

    const outcomeOptions = await page.locator('#settings-pairOutcome option').allTextContents();
    const labelOptions = await page.locator('#settings-pairLabel option').allTextContents();
    expect(outcomeOptions.length).toBeGreaterThan(0);
    expect(labelOptions.length).toBeGreaterThan(0);

    const selectedOutcome = outcomeOptions[0].trim();
    const selectedLabel = labelOptions[0].trim();

    await settingsPage.addPair(selectedOutcome, selectedLabel);

    const targetRow = page
      .locator('#settings-pairsTable tbody tr')
      .filter({ hasText: selectedOutcome })
      .filter({ hasText: selectedLabel })
      .first();
    await expect(targetRow).toBeVisible();

    await targetRow.locator('button:has-text("Delete")').click();
    await expect(page.locator('text=Pair deleted successfully.')).toBeVisible();
    await expect(targetRow).toHaveCount(0);
  });

  test('should allow reordering the outcome hierarchy', async ({ page, request }) => {
    const originalHierarchy = await getOutcomeHierarchy(request);
    try {
      await settingsPage.goto();
      await settingsPage.waitForPageToLoad();

      const initialHierarchy = await settingsPage.getOutcomeHierarchy();
      expect(initialHierarchy.length).toBeGreaterThan(1);

      const targetOutcome = initialHierarchy[0].trim();
      await settingsPage.moveOutcomeDownByName(targetOutcome);
      await settingsPage.saveOutcomeHierarchy();

      await expect(page.locator('text=Outcome hierarchy saved successfully.')).toBeVisible();

      const updatedHierarchy = (await settingsPage.getOutcomeHierarchy()).map(item => item.trim());
      expect(updatedHierarchy[1]).toBe(targetOutcome);
    } finally {
      await restoreOutcomeHierarchy(request, originalHierarchy);
      const restoredHierarchy = await getOutcomeHierarchy(request);
      expect(restoredHierarchy.outcomes.map(outcome => outcome.ao_id)).toEqual(
        originalHierarchy.outcomes.map(outcome => outcome.ao_id)
      );
    }
  });

  test('should allow configuring OpenAI AI authoring settings', async ({ request, page }) => {
    const currentSettings = await getAIAuthoringSettings(request);

    try {
      await settingsPage.goto();
      await settingsPage.waitForPageToLoad();

      await settingsPage.setAiProvider('openai');
      await settingsPage.setAiModel('gpt-4.1-mini');
      if (!currentSettings.api_key_configured) {
        await settingsPage.setAiApiKey('sk-demo-settings-key');
      }
      await settingsPage.setAiEnabled(true);
      await settingsPage.saveAiSettings();

      await expect(page.locator('text=AI authoring settings saved successfully.')).toBeVisible();
      await expect(settingsPage.aiProviderSelect).toHaveValue('openai');
      await expect(settingsPage.aiModelInput).toHaveValue('gpt-4.1-mini');
    } finally {
      const restoredSettings = await restoreAIAuthoringSettings(request, currentSettings);
      expect(restoredSettings.provider).toBe(currentSettings.provider);
      expect(restoredSettings.enabled).toBe(currentSettings.api_key_configured ? currentSettings.enabled : false);
      expect(restoredSettings.model).toBe(currentSettings.model);
      expect(restoredSettings.api_key_configured).toBe(currentSettings.api_key_configured);
    }
  });
});
