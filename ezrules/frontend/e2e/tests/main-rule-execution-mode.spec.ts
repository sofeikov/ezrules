import { test, expect } from '@playwright/test';
import { SettingsPage } from '../pages/settings.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

test.describe('Main Rule Execution Mode', () => {
  test('should allow changing the main rule execution mode', async ({ page, request }) => {
    const settingsPage = new SettingsPage(page);
    const authHeaders = { Authorization: `Bearer ${getAuthToken()}` };
    const currentSettingsResponse = await request.get(`${API_BASE}/api/v2/settings/runtime`, { headers: authHeaders });
    expect(currentSettingsResponse.ok()).toBeTruthy();
    const currentSettings = await currentSettingsResponse.json();

    try {
      await settingsPage.goto();
      await settingsPage.waitForPageToLoad();

      const executionModeSelect = page.locator('#settings-mainRuleExecutionMode');
      await expect(executionModeSelect).toBeVisible();

      const originalMode = await executionModeSelect.inputValue();
      const nextMode = originalMode === 'first_match' ? 'all_matches' : 'first_match';

      await executionModeSelect.selectOption(nextMode);
      await page.locator('#settings-saveRuntimeSettings').click();

      await expect(page.locator('text=Settings saved successfully.')).toBeVisible();
      await expect(executionModeSelect).toHaveValue(nextMode);
    } finally {
      const restoreResponse = await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders,
        data: {
          rule_quality_lookback_days: currentSettings.rule_quality_lookback_days,
          auto_promote_active_rule_updates: currentSettings.auto_promote_active_rule_updates,
          main_rule_execution_mode: currentSettings.main_rule_execution_mode,
          neutral_outcome: currentSettings.neutral_outcome,
        },
      });
      expect(restoreResponse.ok()).toBeTruthy();
    }
  });
});
