import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Field Types management page.
 */
export class FieldTypesPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly fieldNameInput: Locator;
  readonly typeSelect: Locator;
  readonly saveButton: Locator;
  readonly loadingSpinner: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.fieldNameInput = page.locator('input[placeholder="e.g. amount"]');
    this.typeSelect = page.locator('select');
    this.saveButton = page.locator('button:has-text("Save")');
    this.loadingSpinner = page.locator('.animate-spin');
  }

  async goto() {
    await this.page.goto('/field-types');
  }

  async waitForLoad() {
    await this.loadingSpinner.waitFor({ state: 'hidden' });
  }

  async getConfiguredCount(): Promise<number> {
    // Count rows in the Configured Fields table
    const section = this.page.locator('h2:has-text("Configured Fields")').locator('../..');
    const rows = section.locator('tbody tr');
    const count = await rows.count();
    return count;
  }

  async hasConfiguredField(fieldName: string): Promise<boolean> {
    await this.waitForLoad();
    return await this.page
      .locator('tbody tr td:first-child')
      .filter({ hasText: fieldName })
      .isVisible()
      .catch(() => false);
  }

  async saveFieldType(fieldName: string, type: string) {
    await this.fieldNameInput.fill(fieldName);
    await this.typeSelect.selectOption(type);
    await this.saveButton.click();
  }

  async deleteFieldType(fieldName: string) {
    const row = this.page.locator('tbody tr').filter({ hasText: fieldName }).first();
    await row.locator('button:has-text("Delete")').click();
  }
}
