import { expect, Page, test } from '@playwright/test';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

async function replaceEditorContent(page: Page, text: string): Promise<void> {
  const editor = page.locator('.cm-content[contenteditable="true"]').first();
  await editor.click();
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await page.keyboard.press('Backspace');
  await page.keyboard.type(text);
}

test.describe('Rule Logic Editor', () => {
  test('should surface autocomplete and detected references on the create page', async ({ page, request }) => {
    const authHeaders = { Authorization: `Bearer ${getAuthToken()}` };
    const listName = `EditorHints_${Date.now()}`;

    const createListResponse = await request.post(`${API_BASE}/api/v2/user-lists`, {
      headers: authHeaders,
      data: { name: listName },
    });
    expect(createListResponse.ok()).toBeTruthy();

    await request.post(`${API_BASE}/api/v2/rules/test`, {
      headers: authHeaders,
      data: {
        rule_source: 'return True',
        test_json: '{"editor_amount_signal": 1250}',
      },
    });

    try {
      await page.goto('/rules/create');

      const editor = page.locator('.cm-content[contenteditable="true"]').first();
      await expect(page.locator('.cm-editor')).toBeVisible();

      await editor.click();
      await page.keyboard.type('return $ed');
      await page.keyboard.press('Control+Space');
      await expect(page.locator('.cm-tooltip-autocomplete')).toContainText('$editor_amount_signal');

      await replaceEditorContent(page, 'return !HO');
      await page.keyboard.press('Control+Space');
      await expect(page.locator('.cm-tooltip-autocomplete')).toContainText('!HOLD');

      await replaceEditorContent(page, `if $editor_amount_signal > 0 and "GB" in @${listName}:\n\treturn !HOLD`);
      await page.waitForResponse((response) => response.url().includes('/api/v2/rules/verify'));

      const detectedReferences = page.locator('.bg-slate-50').filter({ hasText: 'Detected references' });
      await expect(detectedReferences).toContainText('$editor_amount_signal');
      await expect(detectedReferences).toContainText(`@${listName}`);
      await expect(detectedReferences).toContainText('!HOLD');
    } finally {
      const listsResponse = await request.get(`${API_BASE}/api/v2/user-lists`, {
        headers: authHeaders,
      });
      const listsPayload = await listsResponse.json();
      const createdList = (listsPayload.lists as Array<{ id: number; name: string }>).find((list) => list.name === listName);
      if (createdList) {
        await request.delete(`${API_BASE}/api/v2/user-lists/${createdList.id}`, {
          headers: authHeaders,
        });
      }
    }
  });

  test('should show structured validation errors in rule detail edit mode', async ({ page, request }) => {
    const authHeaders = { Authorization: `Bearer ${getAuthToken()}` };
    const createResponse = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: authHeaders,
      data: {
        rid: `EDITOR_DETAIL_${Date.now()}`,
        description: 'rule editor detail validation test',
        logic: 'return True',
      },
    });
    expect(createResponse.ok()).toBeTruthy();

    const createPayload = await createResponse.json();
    const ruleId = createPayload.rule.r_id as number;

    try {
      await page.goto(`/rules/${ruleId}`);
      await page.getByRole('button', { name: 'Edit Rule' }).click();

      await replaceEditorContent(page, 'return 1 +');
      await page.waitForResponse((response) => response.url().includes('/api/v2/rules/verify'));

      const validationCard = page.locator('.bg-red-50').filter({ hasText: 'Validation errors' });
      await expect(validationCard).toBeVisible();
      await expect(validationCard).toContainText(/line 1, column \d+/);
    } finally {
      await request.delete(`${API_BASE}/api/v2/rules/${ruleId}`, {
        headers: authHeaders,
      });
    }
  });
});
