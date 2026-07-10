import { expect, test } from '../support/fixtures';
import { FieldTypesPage } from '../pages/field-types.page';
import { acceptDialog } from '../support/dialogs';
import { testResourceName } from '../support/test-data';

test.describe('Field Types Required Flag', () => {
  test('should save a required field configuration and show the required badge', async ({ page }, testInfo) => {
    const fieldTypesPage = new FieldTypesPage(page);
    const fieldName = testResourceName(testInfo, 'required_field');

    await fieldTypesPage.goto();
    await fieldTypesPage.waitForLoad();

    await fieldTypesPage.fieldNameInput.fill(fieldName);
    await fieldTypesPage.typeSelect.selectOption('integer');
    await page.getByLabel('Required and non-null').check();
    await fieldTypesPage.saveButton.click();

    const row = page.locator('tbody tr').filter({ hasText: fieldName }).first();
    await expect(row).toBeVisible();
    await expect(row).toContainText('required');

    await acceptDialog(page, () => row.getByRole('button', { name: 'Delete' }).click());
  });
});
