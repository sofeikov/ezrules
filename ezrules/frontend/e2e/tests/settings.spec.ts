import { test, expect } from '@playwright/test';
import { SettingsPage } from '../pages/settings.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

test.describe('Settings Page', () => {
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
    const authHeaders = { Authorization: `Bearer ${getAuthToken()}` };
    const currentSettingsResponse = await request.get(`${API_BASE}/api/v2/settings/runtime`, { headers: authHeaders });
    expect(currentSettingsResponse.ok()).toBeTruthy();
    const currentSettings = await currentSettingsResponse.json();
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
      const restoreResponse = await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders,
        data: {
          rule_quality_lookback_days: currentSettings.rule_quality_lookback_days,
          auto_promote_active_rule_updates: currentSettings.auto_promote_active_rule_updates,
          neutral_outcome: currentSettings.neutral_outcome,
        },
      });
      expect(restoreResponse.ok()).toBeTruthy();
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
  });

  test('should allow reordering the outcome hierarchy', async ({ page }) => {
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
  });
});
