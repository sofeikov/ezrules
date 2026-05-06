import { Locator, Page } from '@playwright/test';

export class FeaturesPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly nameInput: Locator;
  readonly entityInput: Locator;
  readonly featureNameInput: Locator;
  readonly entityKeyInput: Locator;
  readonly aggregationSelect: Locator;
  readonly sourceFieldInput: Locator;
  readonly saveButton: Locator;
  readonly loadingSpinner: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.nameInput = page.getByRole('textbox', { name: 'Name', exact: true });
    this.entityInput = page.getByRole('textbox', { name: 'Entity', exact: true });
    this.featureNameInput = page.getByRole('textbox', { name: 'Feature name' });
    this.entityKeyInput = page.locator('label:has-text("Entity key field") input');
    this.aggregationSelect = page.locator('label:has-text("Aggregation") select');
    this.sourceFieldInput = page.locator('label:has-text("Source field") input');
    this.saveButton = page.locator('button:has-text("Save")');
    this.loadingSpinner = page.locator('.animate-spin');
  }

  async goto() {
    await this.page.goto('/features');
  }

  async waitForLoad() {
    await this.loadingSpinner.waitFor({ state: 'hidden' });
  }

  async createFeature(name: string, featureName: string) {
    await this.nameInput.fill(name);
    await this.entityInput.fill('sender');
    await this.featureNameInput.fill(featureName);
    await this.entityKeyInput.fill('sender_id');
    await this.aggregationSelect.selectOption('sum');
    await this.sourceFieldInput.fill('amount');
    await this.saveButton.click();
  }

  async activateFeature(name: string) {
    const row = this.page.locator('tbody tr').filter({ hasText: name }).first();
    await row.locator('button:has-text("Activate")').click();
  }

  featureRow(name: string): Locator {
    return this.page.locator('tbody tr').filter({ hasText: name }).first();
  }
}
