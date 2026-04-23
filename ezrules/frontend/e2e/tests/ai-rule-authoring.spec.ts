import { expect, test } from '@playwright/test';

import { AiRuleAuthoringPanel } from '../pages/ai-rule-authoring.panel';
import { RuleCreatePage } from '../pages/rule-create.page';
import { RuleDetailPage } from '../pages/rule-detail.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

test.describe('AI Rule Authoring', () => {
  let ruleCreatePage: RuleCreatePage;
  let ruleDetailPage: RuleDetailPage;
  let aiPanel: AiRuleAuthoringPanel;
  let testRuleId = 0;

  test.beforeEach(async ({ page }) => {
    ruleCreatePage = new RuleCreatePage(page);
    ruleDetailPage = new RuleDetailPage(page);
    aiPanel = new AiRuleAuthoringPanel(page);
    testRuleId = 0;
  });

  test.afterEach(async ({ request }) => {
    if (testRuleId) {
      await request.delete(`${API_BASE}/api/v2/rules/${testRuleId}`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      testRuleId = 0;
    }
  });

  test('shows a generated draft in create flow and applies it only after explicit approval', async ({ page }) => {
    await page.route('**/api/v2/rules/ai/draft', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generation_id: 'gen-create-flow',
          draft_logic: "if $amount > 10000:\n\treturn !HOLD",
          line_explanations: [
            {
              line_number: 1,
              source: 'if $amount > 10000:',
              explanation: 'Checks whether the event amount exceeds the threshold.',
            },
            {
              line_number: 2,
              source: '\treturn !HOLD',
              explanation: 'Returns HOLD when the threshold condition matches.',
            },
          ],
          validation: {
            valid: true,
            params: ['amount'],
            referenced_lists: [],
            referenced_outcomes: ['HOLD'],
            warnings: [],
            errors: [],
          },
          repair_attempted: false,
          applyable: true,
          provider: 'openai',
        }),
      });
    });

    await page.route('**/api/v2/rules/ai/apply', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, message: 'AI draft applied to the editor' }),
      });
    });

    await ruleCreatePage.goto();
    await expect(aiPanel.panel).toBeVisible();
    await expect(aiPanel.toggleButton).toHaveCount(0);

    await aiPanel.fillPrompt('Flag high value transfers above 10,000.');
    await aiPanel.clickGenerate();

    await expect(aiPanel.result).toBeVisible();
    await expect(aiPanel.statusBadge).toHaveText('Validated draft');
    await aiPanel.toggleExplanations();
    await expect(aiPanel.explanations).toHaveCount(2);
    await expect(ruleCreatePage.logicTextarea).toHaveValue('');

    await aiPanel.clickApply();

    await expect(aiPanel.appliedBanner).toBeVisible();
    await expect(ruleCreatePage.logicTextarea).toHaveValue("if $amount > 10000:\n\treturn !HOLD");
    await expect(page).toHaveURL(/\/rules\/create/);
  });

  test('keeps invalid drafts in review-only mode on create flow', async ({ page }) => {
    await page.route('**/api/v2/rules/ai/draft', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generation_id: 'gen-invalid-flow',
          draft_logic: "if $amount > 10000:\n\treturn !UNKNOWN",
          line_explanations: [],
          validation: {
            valid: false,
            params: [],
            referenced_lists: [],
            referenced_outcomes: ['UNKNOWN'],
            warnings: [],
            errors: [{ message: "Outcome '!UNKNOWN' is not configured in Outcomes.", line: 2, column: 9, end_line: 2, end_column: 17 }],
          },
          repair_attempted: true,
          applyable: false,
          provider: 'openai',
        }),
      });
    });

    await ruleCreatePage.goto();
    await aiPanel.fillPrompt('Flag high value transfers above 10,000.');
    await aiPanel.clickGenerate();

    await expect(aiPanel.result).toBeVisible();
    await expect(aiPanel.statusBadge).toHaveText('Review required');
    await expect(aiPanel.applyButton).toBeDisabled();
    await expect(page.getByText("Outcome '!UNKNOWN' is not configured in Outcomes.")).toBeVisible();
  });

  test('uses current rule context in edit flow and applies the approved draft', async ({ page, request }) => {
    const createResponse = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
      data: {
        rid: `AI_EDIT_${Date.now()}`,
        description: 'Existing AI edit test rule',
        logic: "if $amount > 100:\n\treturn !HOLD",
      },
    });
    const createData = await createResponse.json();
    testRuleId = createData.rule.r_id;

    await page.route('**/api/v2/rules/ai/draft', async route => {
      const body = route.request().postDataJSON();
      expect(body.mode).toBe('edit');
      expect(body.rule_id).toBe(testRuleId);
      expect(body.current_logic).toContain('$amount > 100');
      expect(body.current_description).toBe('Existing AI edit test rule');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generation_id: 'gen-edit-flow',
          draft_logic: "if $amount > 500:\n\treturn !HOLD",
          line_explanations: [
            {
              line_number: 1,
              source: 'if $amount > 500:',
              explanation: 'Raises the threshold for the hold decision.',
            },
          ],
          validation: {
            valid: true,
            params: ['amount'],
            referenced_lists: [],
            referenced_outcomes: ['HOLD'],
            warnings: [],
            errors: [],
          },
          repair_attempted: false,
          applyable: true,
          provider: 'openai',
        }),
      });
    });

    await page.route('**/api/v2/rules/ai/apply', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, message: 'AI draft applied to the editor' }),
      });
    });

    await ruleDetailPage.goto(testRuleId);
    await ruleDetailPage.waitForRuleToLoad();
    await ruleDetailPage.clickEdit();

    await expect(aiPanel.panel).toBeVisible();
    await expect(aiPanel.toggleButton).toBeVisible();
    await expect(aiPanel.promptTextarea).toHaveCount(0);
    await aiPanel.toggle();
    await expect(aiPanel.promptTextarea).toBeVisible();
    await aiPanel.fillPrompt('Tighten the rule so only amounts above 500 are held.');
    await aiPanel.clickGenerate();

    await expect(aiPanel.result).toBeVisible();
    await aiPanel.clickApply();

    await expect(aiPanel.appliedBanner).toBeVisible();
    await expect(ruleDetailPage.editableLogicTextarea).toHaveValue("if $amount > 500:\n\treturn !HOLD");
  });
});
