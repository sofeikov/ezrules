import { test, expect, type APIRequestContext } from '@playwright/test';
import { RuleListPage } from '../pages/rule-list.page';
import { SettingsPage } from '../pages/settings.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

async function apiRequest(
  request: APIRequestContext,
  path: string,
  method: string,
  data: unknown,
  authHeaders: Record<string, string>,
) {
  const response = await request.fetch(`${API_BASE}${path}`, {
    method,
    headers: authHeaders,
    data,
  });
  expect(response.ok()).toBeTruthy();
  return response;
}

async function createMainRule(
  request: APIRequestContext,
  authHeaders: Record<string, string>,
  rid: string,
  description: string,
  executionOrder: number,
) {
  const response = await apiRequest(
    request,
    '/api/v2/rules',
    'POST',
    {
      rid,
      description,
      logic: `if $amount > 0:\n\treturn "${rid}"`,
      execution_order: executionOrder,
      evaluation_lane: 'main',
    },
    authHeaders,
  );
  const payload = await response.json();
  const ruleId = payload.rule.r_id as number;
  await apiRequest(request, `/api/v2/rules/${ruleId}/promote`, 'POST', {}, authHeaders);
  return ruleId;
}

function buildRuntimeSettingsPayload(
  currentSettings: Record<string, unknown>,
  overrides: Partial<Record<'main_rule_execution_mode', string>>,
) {
  return {
    rule_quality_lookback_days: currentSettings.rule_quality_lookback_days,
    auto_promote_active_rule_updates: currentSettings.auto_promote_active_rule_updates,
    main_rule_execution_mode: overrides.main_rule_execution_mode ?? currentSettings.main_rule_execution_mode,
    neutral_outcome: currentSettings.neutral_outcome,
  };
}

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
      await page.locator('#settings-saveNeutralOutcome').click();

      await expect(page.locator('text=Settings saved successfully.')).toBeVisible();
      await expect(executionModeSelect).toHaveValue(nextMode);
    } finally {
      const restoreResponse = await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders,
        data: buildRuntimeSettingsPayload(currentSettings, {}),
      });
      expect(restoreResponse.ok()).toBeTruthy();
    }
  });

  test('should show rule-order controls only when first-match mode is enabled', async ({ page, request }) => {
    test.setTimeout(120000);
    const rulePage = new RuleListPage(page);
    const authHeaders = { Authorization: `Bearer ${getAuthToken()}` };
    const currentSettingsResponse = await request.get(`${API_BASE}/api/v2/settings/runtime`, { headers: authHeaders });
    expect(currentSettingsResponse.ok()).toBeTruthy();
    const currentSettings = await currentSettingsResponse.json();
    const createdRuleIds: number[] = [];
    let originalMainRuleIds: number[] = [];

    try {
      await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders,
        data: buildRuntimeSettingsPayload(currentSettings, { main_rule_execution_mode: 'all_matches' }),
      });

      await page.goto('/rules');
      await expect(page.locator('th:has-text("Order")')).toHaveCount(0);
      await expect(page.getByRole('button', { name: 'Reorder Rules' })).toHaveCount(0);

      await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders,
        data: buildRuntimeSettingsPayload(currentSettings, { main_rule_execution_mode: 'first_match' }),
      });

      await page.goto('/rules');
      await expect(page.locator('th:has-text("Order")')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Reorder Rules' })).toBeVisible();

      const originalRulesResponse = await request.get(`${API_BASE}/api/v2/rules`, { headers: authHeaders });
      expect(originalRulesResponse.ok()).toBeTruthy();
      const originalRulesPayload = await originalRulesResponse.json();
      originalMainRuleIds = (originalRulesPayload.rules as Array<{ r_id: number; evaluation_lane: string; status: string }>)
        .filter((rule) => rule.evaluation_lane === 'main' && rule.status !== 'archived')
        .map((rule) => rule.r_id);

      const unique = Date.now();
      const ruleOneRid = `E2E_ORDER_RULE_1_${unique}`;
      const ruleTwoRid = `E2E_ORDER_RULE_2_${unique}`;
      const ruleThreeRid = `E2E_ORDER_RULE_3_${unique}`;

      const ruleOneId = await createMainRule(request, authHeaders, ruleOneRid, 'E2E order first', 997);
      const ruleTwoId = await createMainRule(request, authHeaders, ruleTwoRid, 'E2E order second', 998);
      const ruleThreeId = await createMainRule(request, authHeaders, ruleThreeRid, 'E2E order third', 999);
      createdRuleIds.push(ruleOneId, ruleTwoId, ruleThreeId);

      await rulePage.goto();
      await rulePage.waitForRulesToLoad();
      await rulePage.enterReorderMode();

      await expect(rulePage.cancelOrderButton).toBeVisible();
      await expect(rulePage.saveOrderButton).toBeVisible();

      await expect(rulePage.getOrderForRule(ruleOneRid)).resolves.toBe('997');
      await expect(rulePage.getOrderForRule(ruleTwoRid)).resolves.toBe('998');
      await expect(rulePage.getOrderForRule(ruleThreeRid)).resolves.toBe('999');

      const originalRowIndexes = await Promise.all([
        rulePage.getRowIndexForRule(ruleOneRid),
        rulePage.getRowIndexForRule(ruleTwoRid),
        rulePage.getRowIndexForRule(ruleThreeRid),
      ]);

      await rulePage.moveRuleDown(ruleTwoRid);
      const movedRowIndexes = await Promise.all([
        rulePage.getRowIndexForRule(ruleOneRid),
        rulePage.getRowIndexForRule(ruleTwoRid),
        rulePage.getRowIndexForRule(ruleThreeRid),
      ]);
      expect(movedRowIndexes[0]).toBe(originalRowIndexes[0]);
      expect(movedRowIndexes[1]).toBeGreaterThan(movedRowIndexes[2]);
      await expect(page.getByRole('button', { name: 'Done Reordering' })).toBeDisabled();

      await rulePage.cancelOrderButton.click();
      await expect(rulePage.saveOrderButton).toHaveCount(0);
      await expect(rulePage.getOrderForRule(ruleTwoRid)).resolves.toBe('998');

      await rulePage.enterReorderMode();
      await rulePage.rowByRid(ruleThreeRid).getByRole('button', { name: 'Enter exact position' }).click();
      await expect(rulePage.rowByRid(ruleThreeRid).locator('input[type="number"]')).toBeVisible();

      await rulePage.moveRuleUp(ruleThreeRid);
      await rulePage.saveOrderButton.click();
      await expect(rulePage.saveOrderButton).toHaveCount(0);

      await page.reload();
      await rulePage.waitForRulesToLoad();
      const persistedRowIndexes = await Promise.all([
        rulePage.getRowIndexForRule(ruleTwoRid),
        rulePage.getRowIndexForRule(ruleThreeRid),
      ]);
      expect(persistedRowIndexes[1]).toBeLessThan(persistedRowIndexes[0]);
    } finally {
      for (const ruleId of createdRuleIds) {
        const deleteResponse = await request.fetch(`${API_BASE}/api/v2/rules/${ruleId}`, {
          method: 'DELETE',
          headers: authHeaders,
        });
        expect(deleteResponse.ok()).toBeTruthy();
      }
      if (originalMainRuleIds.length > 0) {
        await apiRequest(request, '/api/v2/rules/main-order', 'PUT', { ordered_r_ids: originalMainRuleIds }, authHeaders);
      }
      const restoreResponse = await request.put(`${API_BASE}/api/v2/settings/runtime`, {
        headers: authHeaders,
        data: buildRuntimeSettingsPayload(currentSettings, {}),
      });
      expect(restoreResponse.ok()).toBeTruthy();
    }
  });
});
