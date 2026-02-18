import { test, expect } from '@playwright/test';
import { FieldTypesPage } from '../pages/field-types.page';

test.describe('Field Types Page', () => {
  let fieldTypesPage: FieldTypesPage;

  test.beforeEach(async ({ page }) => {
    fieldTypesPage = new FieldTypesPage(page);
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
    test('should save a new field type configuration and show it in the table', async ({ page }) => {
      await fieldTypesPage.goto();
      await fieldTypesPage.waitForLoad();

      const fieldName = `e2e_field_${Date.now()}`;

      await fieldTypesPage.saveFieldType(fieldName, 'integer');

      // Wait for the row to appear in the table
      await page.waitForFunction(
        (name: string) => {
          const cells = document.querySelectorAll('tbody tr td:first-child');
          return Array.from(cells).some(c => c.textContent?.trim() === name);
        },
        fieldName,
        { timeout: 5000 }
      );

      expect(await fieldTypesPage.hasConfiguredField(fieldName)).toBe(true);

      // Cleanup
      page.on('dialog', d => d.accept());
      await fieldTypesPage.deleteFieldType(fieldName);
      await page.waitForFunction(
        (name: string) => {
          const cells = document.querySelectorAll('tbody tr td:first-child');
          return !Array.from(cells).some(c => c.textContent?.trim() === name);
        },
        fieldName,
        { timeout: 5000 }
      );
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
    test('should delete a configuration after confirmation', async ({ page }) => {
      await fieldTypesPage.goto();
      await fieldTypesPage.waitForLoad();

      const fieldName = `del_e2e_${Date.now()}`;
      await fieldTypesPage.saveFieldType(fieldName, 'float');

      await page.waitForFunction(
        (name: string) => {
          const cells = document.querySelectorAll('tbody tr td:first-child');
          return Array.from(cells).some(c => c.textContent?.trim() === name);
        },
        fieldName,
        { timeout: 5000 }
      );

      page.on('dialog', d => d.accept());
      await fieldTypesPage.deleteFieldType(fieldName);

      await page.waitForFunction(
        (name: string) => {
          const cells = document.querySelectorAll('tbody tr td:first-child');
          return !Array.from(cells).some(c => c.textContent?.trim() === name);
        },
        fieldName,
        { timeout: 5000 }
      );

      expect(await fieldTypesPage.hasConfiguredField(fieldName)).toBe(false);
    });

    test('should not delete when confirmation is dismissed', async ({ page }) => {
      await fieldTypesPage.goto();
      await fieldTypesPage.waitForLoad();

      const fieldName = `nodelete_e2e_${Date.now()}`;
      await fieldTypesPage.saveFieldType(fieldName, 'string');

      await page.waitForFunction(
        (name: string) => {
          const cells = document.querySelectorAll('tbody tr td:first-child');
          return Array.from(cells).some(c => c.textContent?.trim() === name);
        },
        fieldName,
        { timeout: 5000 }
      );

      page.on('dialog', d => d.dismiss());
      await fieldTypesPage.deleteFieldType(fieldName);

      await page.waitForTimeout(500);
      expect(await fieldTypesPage.hasConfiguredField(fieldName)).toBe(true);

      // Cleanup
      page.removeAllListeners('dialog');
      page.on('dialog', d => d.accept());
      await fieldTypesPage.deleteFieldType(fieldName);
      await page.waitForFunction(
        (name: string) => {
          const cells = document.querySelectorAll('tbody tr td:first-child');
          return !Array.from(cells).some(c => c.textContent?.trim() === name);
        },
        fieldName,
        { timeout: 5000 }
      );
    });
  });
});
