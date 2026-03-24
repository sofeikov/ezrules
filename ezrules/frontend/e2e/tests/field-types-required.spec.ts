import { expect, test } from '@playwright/test';
import { FieldTypesPage } from '../pages/field-types.page';

test.describe('Field Types Required Flag', () => {
  test('should save a required field configuration and show the required badge', async ({ page }) => {
    const fieldTypesPage = new FieldTypesPage(page);
    const fieldName = `required_field_${Date.now()}`;

    await fieldTypesPage.goto();
    await fieldTypesPage.waitForLoad();

    await fieldTypesPage.fieldNameInput.fill(fieldName);
    await fieldTypesPage.typeSelect.selectOption('integer');
    await page.getByLabel('Required and non-null').check();
    await fieldTypesPage.saveButton.click();

    const row = page.locator('tbody tr').filter({ hasText: fieldName }).first();
    await expect(row).toBeVisible();
    await expect(row).toContainText('required');

    page.on('dialog', dialog => dialog.accept());
    await row.getByRole('button', { name: 'Delete' }).click();
  });
});
