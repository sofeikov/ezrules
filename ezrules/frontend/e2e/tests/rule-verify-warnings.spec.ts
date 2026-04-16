import { expect, test } from '@playwright/test';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

test.describe('Rule Verify Warnings', () => {
  test('should show verify warnings on the create rule page for unseen fields', async ({ page }) => {
    await page.goto('/rules/create');

    await page.locator('textarea[placeholder="Enter rule logic"]').fill('return $brand_new_signal > 0');
    await page.waitForResponse(response => response.url().includes('/api/v2/rules/verify'));

    const warningCard = page.locator('.bg-amber-50').filter({ hasText: 'Field warnings' });
    await expect(warningCard).toBeVisible();
    await expect(warningCard).toContainText('brand_new_signal');
  });

  test('should show verify warnings in rule detail edit mode for unseen fields', async ({ page, request }) => {
    const createResponse = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
      data: {
        rid: `E2E_VERIFY_WARN_${Date.now()}`,
        description: 'verify warning detail test',
        logic: "return !HOLD",
      },
    });
    const createData = await createResponse.json();
    const ruleId = createData.rule.r_id as number;

    try {
      await page.goto(`/rules/${ruleId}`);
      await page.getByRole('button', { name: 'Edit Rule' }).click();

      const logicEditor = page.locator('textarea[placeholder="Enter rule logic"]').first();
      await logicEditor.fill('return $detail_only_signal > 0');
      await page.waitForResponse(response => response.url().includes('/api/v2/rules/verify'));

      const warningCard = page.locator('.bg-amber-50').filter({ hasText: 'Field warnings' });
      await expect(warningCard).toBeVisible();
      await expect(warningCard).toContainText('detail_only_signal');
    } finally {
      await request.delete(`${API_BASE}/api/v2/rules/${ruleId}`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
    }
  });
});
