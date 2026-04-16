import { APIRequestContext, expect, test } from '@playwright/test';
import { RuleCreatePage } from '../pages/rule-create.page';
import { RuleDetailPage } from '../pages/rule-detail.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

test.describe('Rule Test JSON Prefill', () => {
  let ruleCreatePage: RuleCreatePage;
  let ruleDetailPage: RuleDetailPage;
  let createdRuleIds: number[] = [];
  let createdConfigFields: string[] = [];

  test.beforeEach(async ({ page }) => {
    ruleCreatePage = new RuleCreatePage(page);
    ruleDetailPage = new RuleDetailPage(page);
    createdRuleIds = [];
    createdConfigFields = [];
  });

  test.afterEach(async ({ request }) => {
    for (const ruleId of createdRuleIds) {
      await request.delete(`${API_BASE}/api/v2/rules/${ruleId}`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
    }

    for (const fieldName of createdConfigFields) {
      await request.delete(`${API_BASE}/api/v2/field-types/${fieldName}`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
    }
  });

  test('should prefill create-page JSON using configured field types', async ({ page, request }) => {
    const amountField = `demo_amount_${Date.now()}`;
    const flagField = `demo_flag_${Date.now()}`;
    const timeField = `demo_seen_at_${Date.now()}`;

    await upsertFieldType(request, amountField, 'float');
    await upsertFieldType(request, flagField, 'boolean');
    await upsertFieldType(request, timeField, 'datetime');
    createdConfigFields.push(amountField, flagField, timeField);

    await ruleCreatePage.goto();
    await ruleCreatePage.fillLogic(
      `if $${amountField} > 100 and $${flagField} == False and $${timeField}:\n\treturn !HOLD`
    );

    await page.waitForResponse((response) => response.url().includes('/api/v2/rules/verify'));
    await expect.poll(async () => {
      const rawValue = await ruleCreatePage.getTestJsonValue();
      return rawValue.trim() ? JSON.parse(rawValue) : null;
    }).toMatchObject({
      [amountField]: expect.any(Number),
      [flagField]: expect.any(Boolean),
      [timeField]: expect.any(String),
    });

    const payload = JSON.parse(await ruleCreatePage.getTestJsonValue());
    expect(typeof payload[amountField]).toBe('number');
    expect(typeof payload[flagField]).toBe('boolean');
    expect(payload[timeField]).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  test('should prefill detail-page JSON from observed field types when no config exists', async ({ request }) => {
    const observedField = `shadowfox_${Date.now()}`;

    await request.post(`${API_BASE}/api/v2/rules/test`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
      data: {
        rule_source: "return !RELEASE",
        test_json: JSON.stringify({ [observedField]: 7 }),
      },
    });

    const createResponse = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
      data: {
        rid: `E2E_PREFILL_${Date.now()}`,
        description: 'Rule used to verify observed field-type prefill',
        logic: `if $${observedField} > 3:\n\treturn !HOLD`,
      },
    });
    expect(createResponse.ok()).toBeTruthy();
    const createPayload = await createResponse.json();
    createdRuleIds.push(createPayload.rule.r_id);

    await ruleDetailPage.goto(createPayload.rule.r_id);
    await ruleDetailPage.waitForRuleToLoad();

    await expect.poll(async () => {
      const rawValue = await ruleDetailPage.testJsonTextarea.inputValue();
      return rawValue.trim() ? JSON.parse(rawValue) : null;
    }).toMatchObject({
      [observedField]: expect.any(Number),
    });

    const payload = JSON.parse(await ruleDetailPage.testJsonTextarea.inputValue());
    expect(typeof payload[observedField]).toBe('number');
  });
});

async function upsertFieldType(
  request: APIRequestContext,
  fieldName: string,
  configuredType: string
) {
  const response = await request.post(`${API_BASE}/api/v2/field-types`, {
    headers: { Authorization: `Bearer ${getAuthToken()}` },
    data: {
      field_name: fieldName,
      configured_type: configuredType,
      datetime_format: null,
    },
  });

  expect(response.ok()).toBeTruthy();
}
