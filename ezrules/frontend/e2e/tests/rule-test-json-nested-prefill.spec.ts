import { APIRequestContext, expect, test } from '@playwright/test';
import { RuleCreatePage } from '../pages/rule-create.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

test.describe('Rule Test JSON Nested Prefill', () => {
  let ruleCreatePage: RuleCreatePage;
  let createdConfigFields: string[] = [];

  test.beforeEach(async ({ page }) => {
    ruleCreatePage = new RuleCreatePage(page);
    createdConfigFields = [];
  });

  test.afterEach(async ({ request }) => {
    for (const fieldName of createdConfigFields) {
      await request.delete(`${API_BASE}/api/v2/field-types/${encodeURIComponent(fieldName)}`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
    }
  });

  test('prefills nested JSON using canonical dotted field paths', async ({ page, request }) => {
    const suffix = Date.now();
    const ageLeaf = `age_${suffix}`;
    const countryLeaf = `country_${suffix}`;
    const ageField = `customer.profile.${ageLeaf}`;
    const countryField = `customer.profile.${countryLeaf}`;

    await upsertFieldType(request, ageField, 'integer');
    await upsertFieldType(request, countryField, 'string');
    createdConfigFields.push(ageField, countryField);

    await ruleCreatePage.goto();
    await ruleCreatePage.fillLogic(
      `if $${ageField} > 21 and $${countryField} == "US":\n\treturn !HOLD`
    );

    await page.waitForResponse((response) => response.url().includes('/api/v2/rules/verify'));

    await expect.poll(async () => {
      const rawValue = await ruleCreatePage.getTestJsonValue();
      return rawValue.trim() ? JSON.parse(rawValue) : null;
    }).toMatchObject({
      customer: {
        profile: {
          [ageLeaf]: expect.any(Number),
          [countryLeaf]: expect.any(String),
        },
      },
    });

    const payload = JSON.parse(await ruleCreatePage.getTestJsonValue());
    expect(typeof payload.customer.profile[ageLeaf]).toBe('number');
    expect(typeof payload.customer.profile[countryLeaf]).toBe('string');
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
