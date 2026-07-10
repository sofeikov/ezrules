import type { APIRequestContext } from '@playwright/test';
import { test, expect } from '../support/fixtures';
import { RuleListPage } from '../pages/rule-list.page';
import { SettingsPage } from '../pages/settings.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';
import {
  createRule,
  deleteRuleById,
  expectApiOk,
  expectRuntimeSettingsRestored,
  getRuntimeSettings,
  promoteRule,
  restoreRuntimeSettings,
} from '../support/api-helpers';
import { testResourceName } from '../support/test-data';
import { SETTINGS_TAG, STATEFUL_TAG } from '../support/tags';

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
  await expectApiOk(response, `${method} ${path}`);
  return response;
}

async function createMainRule(
  request: APIRequestContext,
  rid: string,
  description: string,
  executionOrder: number,
) {
  const rule = await createRule(request, {
    rid,
    description,
    logic: 'if $amount > 0:\n\treturn !HOLD',
    evaluation_lane: 'main',
    execution_order: executionOrder,
  });
  const ruleId = rule.r_id;
  await promoteRule(request, ruleId);
  return ruleId;
}

async function getActiveMainRuleIds(request: APIRequestContext, authHeaders: Record<string, string>) {
  const rulesResponse = await request.get(`${API_BASE}/api/v2/rules`, { headers: authHeaders });
  await expectApiOk(rulesResponse, 'List rules for order restore check');
  const rulesPayload = await rulesResponse.json();
  return (rulesPayload.rules as Array<{ r_id: number; evaluation_lane: string; status: string }>)
    .filter((rule) => rule.evaluation_lane === 'main' && rule.status !== 'archived')
    .map((rule) => rule.r_id);
}

test.describe(`Main Rule Execution Mode ${STATEFUL_TAG} ${SETTINGS_TAG} @global-order`, () => {
  test('should allow changing the main rule execution mode', async ({ page, request }) => {
    const settingsPage = new SettingsPage(page);
    const currentSettings = await getRuntimeSettings(request);

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
      await restoreRuntimeSettings(request, currentSettings);
      await expectRuntimeSettingsRestored(request, currentSettings);
    }
  });

  test('should show rule-order controls only when first-match mode is enabled', async ({ page, request }, testInfo) => {
    test.setTimeout(120000);
    const rulePage = new RuleListPage(page);
    const authHeaders = { Authorization: `Bearer ${getAuthToken()}` };
    const currentSettings = await getRuntimeSettings(request);
    const createdRuleIds: number[] = [];
    let originalMainRuleIds: number[] = [];

    try {
      await restoreRuntimeSettings(request, {
        ...currentSettings,
        main_rule_execution_mode: 'all_matches',
      });

      await page.goto('/rules');
      await expect(page.locator('th:has-text("Order")')).toHaveCount(0);
      await expect(page.getByRole('button', { name: 'Reorder Rules' })).toHaveCount(0);

      await restoreRuntimeSettings(request, {
        ...currentSettings,
        main_rule_execution_mode: 'first_match',
      });

      await page.goto('/rules');
      await expect(page.locator('th:has-text("Order")')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Reorder Rules' })).toBeVisible();

      originalMainRuleIds = await getActiveMainRuleIds(request, authHeaders);

      const unique = testResourceName(testInfo, 'E2E_ORDER', { maxLength: 48, uppercase: true });
      const ruleOneRid = `${unique}_RULE_1`;
      const ruleTwoRid = `${unique}_RULE_2`;
      const ruleThreeRid = `${unique}_RULE_3`;

      const ruleOneId = await createMainRule(request, ruleOneRid, 'E2E order first', 997);
      const ruleTwoId = await createMainRule(request, ruleTwoRid, 'E2E order second', 998);
      const ruleThreeId = await createMainRule(request, ruleThreeRid, 'E2E order third', 999);
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
      const ruleThreeRow = rulePage.rowByRid(ruleThreeRid);
      await ruleThreeRow.getByRole('button', { name: 'Enter exact position' }).click();
      const directPositionInput = ruleThreeRow.locator('input[type="number"]');
      await expect(directPositionInput).toBeVisible();
      const targetPosition = await rulePage.getReorderPositionForRule(ruleTwoRid);
      expect(targetPosition).toBeGreaterThan(0);
      await directPositionInput.fill(String(targetPosition));
      await ruleThreeRow.getByRole('button', { name: 'Go' }).click();
      await expect(rulePage.saveOrderButton).toBeEnabled();

      const reorderedRowIndexes = await Promise.all([
        rulePage.getRowIndexForRule(ruleTwoRid),
        rulePage.getRowIndexForRule(ruleThreeRid),
      ]);
      expect(reorderedRowIndexes[1]).toBeLessThan(reorderedRowIndexes[0]);

      const saveResponsePromise = page.waitForResponse(
        resp => resp.url().endsWith('/api/v2/rules/main-order') && resp.request().method() === 'PUT'
      );
      await rulePage.saveOrderButton.click();
      const saveResponse = await saveResponsePromise;
      expect(saveResponse.ok()).toBeTruthy();
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
        await deleteRuleById(request, ruleId);
      }
      let restoredMainRuleIds: number[] | null = null;
      if (originalMainRuleIds.length > 0) {
        try {
          await apiRequest(request, '/api/v2/rules/main-order', 'PUT', { ordered_r_ids: originalMainRuleIds }, authHeaders);
          restoredMainRuleIds = await getActiveMainRuleIds(request, authHeaders);
        } finally {
          await restoreRuntimeSettings(request, currentSettings);
          await expectRuntimeSettingsRestored(request, currentSettings);
        }
      } else {
        await restoreRuntimeSettings(request, currentSettings);
        await expectRuntimeSettingsRestored(request, currentSettings);
      }
      if (restoredMainRuleIds) {
        expect(restoredMainRuleIds).toEqual(originalMainRuleIds);
      }
    }
  });
});
