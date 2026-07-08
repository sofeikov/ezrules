import { test, expect } from '../support/fixtures';
import { FieldTypesPage } from '../pages/field-types.page';
import { deleteFieldTypeByName } from '../support/api-helpers';
import { acceptDialog, dismissDialog } from '../support/dialogs';
import { testResourceName } from '../support/test-data';
import { STATEFUL_TAG, TEST_DATA_TAG } from '../support/tags';

test.describe(`Field Types Page ${STATEFUL_TAG} ${TEST_DATA_TAG}`, () => {
  let fieldTypesPage: FieldTypesPage;
  let createdFieldNames: string[];

  test.beforeEach(async ({ page }) => {
    fieldTypesPage = new FieldTypesPage(page);
    createdFieldNames = [];
  });

  test.afterEach(async ({ request }) => {
    for (const fieldName of createdFieldNames) {
      await deleteFieldTypeByName(request, fieldName);
    }
  });

  test.describe('Page Structure', () => {
    test('should load the field types page successfully', async ({ page }) => {
      await fieldTypesPage.goto();
      await expect(page).toHaveURL(/.*field-types/);
    });

    test('should display the correct heading', async () => {
      await fieldTypesPage.goto();
      await expect(fieldTypesPage.heading).toHaveText('Field Types');
    });

    test('should display the page description', async ({ page }) => {
      await fieldTypesPage.goto();
      const description = page.locator('text=Configure how event fields are cast before rule evaluation');
      await expect(description).toBeVisible();
    });

    test('should be reachable from sidebar navigation', async ({ page }) => {
      await page.goto('/dashboard');
      const link = page.locator('a:has-text("Field Types")');
      await expect(link).toBeVisible();
      await link.click();
      await expect(page).toHaveURL(/.*field-types/);
      await expect(fieldTypesPage.heading).toHaveText('Field Types');
    });

    test('should show the configure form', async () => {
      await fieldTypesPage.goto();
      await fieldTypesPage.waitForLoad();
      await expect(fieldTypesPage.fieldNameInput).toBeVisible();
      await expect(fieldTypesPage.typeSelect).toBeVisible();
      await expect(fieldTypesPage.saveButton).toBeVisible();
    });

    test('should show Configured Fields section', async ({ page }) => {
      await fieldTypesPage.goto();
      await fieldTypesPage.waitForLoad();
      await expect(page.locator('h2:has-text("Configured Fields")')).toBeVisible();
    });

    test('should show Observed Fields section', async ({ page }) => {
      await fieldTypesPage.goto();
      await fieldTypesPage.waitForLoad();
      await expect(page.locator('h2:has-text("Observed Fields")')).toBeVisible();
    });
  });

  test.describe('Configure Field Type', () => {
    test('should save a new field type configuration and show it in the table', async ({ page }, testInfo) => {
      await fieldTypesPage.goto();
      await fieldTypesPage.waitForLoad();

      const fieldName = testResourceName(testInfo, 'e2e_field');
      createdFieldNames.push(fieldName);

      await fieldTypesPage.saveFieldType(fieldName, 'integer');
      await fieldTypesPage.waitForConfiguredField(fieldName);

      expect(await fieldTypesPage.hasConfiguredField(fieldName)).toBe(true);

      // Cleanup
      await acceptDialog(page, () => fieldTypesPage.deleteFieldType(fieldName));
      await fieldTypesPage.waitForConfiguredFieldRemoved(fieldName);
    });

    test('should show all type options in the select', async ({ page }) => {
      await fieldTypesPage.goto();
      await fieldTypesPage.waitForLoad();

      const options = await fieldTypesPage.typeSelect.locator('option').allTextContents();
      expect(options).toContain('integer');
      expect(options).toContain('float');
      expect(options).toContain('string');
      expect(options).toContain('boolean');
      expect(options).toContain('datetime');
      expect(options).toContain('compare_as_is');
    });

    test('should show datetime format input only when datetime type is selected', async ({ page }) => {
      await fieldTypesPage.goto();
      await fieldTypesPage.waitForLoad();

      const dtInput = page.locator('input[placeholder="%Y-%m-%d"]');

      // Initially hidden (default type is string)
      await expect(dtInput).not.toBeVisible();

      // Select datetime
      await fieldTypesPage.typeSelect.selectOption('datetime');
      await expect(dtInput).toBeVisible();

      // Switch back
      await fieldTypesPage.typeSelect.selectOption('integer');
      await expect(dtInput).not.toBeVisible();
    });
  });

  test.describe('Delete Field Type', () => {
    test('should delete a configuration after confirmation', async ({ page }, testInfo) => {
      await fieldTypesPage.goto();
      await fieldTypesPage.waitForLoad();

      const fieldName = testResourceName(testInfo, 'del_e2e');
      createdFieldNames.push(fieldName);
      await fieldTypesPage.saveFieldType(fieldName, 'float');

      await fieldTypesPage.waitForConfiguredField(fieldName);

      await acceptDialog(page, () => fieldTypesPage.deleteFieldType(fieldName));

      await fieldTypesPage.waitForConfiguredFieldRemoved(fieldName);

      expect(await fieldTypesPage.hasConfiguredField(fieldName)).toBe(false);
    });

    test('should not delete when confirmation is dismissed', async ({ page }, testInfo) => {
      await fieldTypesPage.goto();
      await fieldTypesPage.waitForLoad();

      const fieldName = testResourceName(testInfo, 'nodelete_e2e');
      createdFieldNames.push(fieldName);
      await fieldTypesPage.saveFieldType(fieldName, 'string');

      await fieldTypesPage.waitForConfiguredField(fieldName);

      await dismissDialog(page, () => fieldTypesPage.deleteFieldType(fieldName));

      await expect(fieldTypesPage.configuredFieldRow(fieldName)).toHaveCount(1);
      expect(await fieldTypesPage.hasConfiguredField(fieldName)).toBe(true);

      // Cleanup
      await acceptDialog(page, () => fieldTypesPage.deleteFieldType(fieldName));
      await fieldTypesPage.waitForConfiguredFieldRemoved(fieldName);
    });
  });
});
