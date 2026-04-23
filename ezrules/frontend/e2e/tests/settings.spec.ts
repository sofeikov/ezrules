import { test, expect } from '@playwright/test';
import { SettingsPage } from '../pages/settings.page';
import { AuditTrailPage } from '../pages/audit-trail.page';
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

  test('should persist strict mode enablement and surface the audit entry', async ({ page, request }) => {
    const auditTrailPage = new AuditTrailPage(page);
    const authHeaders = { Authorization: `Bearer ${getAuthToken()}` };
    const currentSettingsResponse = await request.get(`${API_BASE}/api/v2/settings/runtime`, { headers: authHeaders });
    expect(currentSettingsResponse.ok()).toBeTruthy();
    const currentSettings = await currentSettingsResponse.json();

    try {
      const prepareResponse = await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders,
        data: { strict_mode_enabled: false },
      });
      expect(prepareResponse.ok()).toBeTruthy();

      await settingsPage.goto();
      await settingsPage.waitForPageToLoad();

      const cards = page.locator('.space-y-6 > div.bg-white.rounded-lg.shadow');
      await expect(settingsPage.strictModeCard).toBeVisible();
      await expect(settingsPage.strictModeStatus).toHaveText('Not Enabled');
      await expect(settingsPage.strictModeAuditLink).toBeVisible();
      await expect(settingsPage.strictModeAuditLink).toHaveAttribute('href', /\/audit#strict-mode$/);
      await expect(cards.first()).toHaveAttribute('id', 'settings-strictModeCard');
      await expect(settingsPage.strictModeCheckbox).not.toBeChecked();

      await settingsPage.setStrictModeEnabled(true);
      await settingsPage.saveStrictMode();

      await expect(page.locator('text=Strict mode enabled successfully.')).toBeVisible();
      await expect(settingsPage.strictModeStatus).toHaveText('Enabled');
      await expect(settingsPage.strictModeCheckbox).toBeChecked();

      await settingsPage.strictModeAuditLink.click();
      await expect(page).toHaveURL(/\/audit#strict-mode$/);
      await auditTrailPage.waitForPageToLoad();
      await expect(auditTrailPage.strictModeAccordion).toBeVisible();
      await expect(auditTrailPage.strictModeTable).toBeVisible();
      await expect(auditTrailPage.strictModeTable.locator('tbody tr').first()).toContainText('Enabled');
      await expect(auditTrailPage.strictModeTable.locator('tbody tr').first()).toContainText('true');
    } finally {
      const restoreResponse = await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders,
        data: { strict_mode_enabled: currentSettings.strict_mode_enabled },
      });
      expect(restoreResponse.ok()).toBeTruthy();
    }
  });

  test('should require typed confirmation before disabling strict mode', async ({ request }) => {
    const authHeaders = { Authorization: `Bearer ${getAuthToken()}` };
    const currentSettingsResponse = await request.get(`${API_BASE}/api/v2/settings/runtime`, { headers: authHeaders });
    expect(currentSettingsResponse.ok()).toBeTruthy();
    const currentSettings = await currentSettingsResponse.json();

    try {
      const prepareResponse = await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders,
        data: { strict_mode_enabled: true },
      });
      expect(prepareResponse.ok()).toBeTruthy();

      await settingsPage.goto();
      await settingsPage.waitForPageToLoad();

      await expect(settingsPage.strictModeStatus).toHaveText('Enabled');
      await settingsPage.setStrictModeEnabled(false);
      await settingsPage.saveStrictMode();

      await expect(settingsPage.strictModeDisableDialog).toBeVisible();
      await expect(settingsPage.strictModeDisableConfirmButton).toBeDisabled();

      await settingsPage.strictModeDisableConfirmationInput.fill('DISABLE STRICT MODE');
      await expect(settingsPage.strictModeDisableConfirmButton).toBeEnabled();
      await settingsPage.strictModeDisableConfirmButton.click();

      await expect(settingsPage.strictModeDisableDialog).toHaveCount(0);
      await expect(settingsPage.strictModeStatus).toHaveText('Not Enabled');
      await expect(settingsPage.strictModeCheckbox).not.toBeChecked();
      await expect(settingsPage.page.locator('text=Strict mode disabled successfully.')).toBeVisible();
    } finally {
      const restoreResponse = await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders,
        data: { strict_mode_enabled: currentSettings.strict_mode_enabled },
      });
      expect(restoreResponse.ok()).toBeTruthy();
    }
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
          strict_mode_enabled: currentSettings.strict_mode_enabled,
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

  test('should allow configuring OpenAI AI authoring settings', async ({ request, page }) => {
    const authHeaders = { Authorization: `Bearer ${getAuthToken()}` };
    const currentSettingsResponse = await request.get(`${API_BASE}/api/v2/settings/ai-authoring`, { headers: authHeaders });
    expect(currentSettingsResponse.ok()).toBeTruthy();
    const currentSettings = await currentSettingsResponse.json();

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
      const restoreResponse = await request.put(`${API_BASE}/api/v2/settings/ai-authoring`, {
        headers: authHeaders,
        data: {
          provider: currentSettings.provider,
          enabled: currentSettings.enabled,
          model: currentSettings.model,
          clear_api_key: currentSettings.api_key_configured ? undefined : true,
        },
      });
      expect(restoreResponse.ok()).toBeTruthy();
    }
  });
});
