import { Locator, Page } from '@playwright/test';

export class FeaturesPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly nameInput: Locator;
  readonly kindSelect: Locator;
  readonly entityInput: Locator;
  readonly featureNameInput: Locator;
  readonly windowSelect: Locator;
  readonly entityKeyInput: Locator;
  readonly aggregationSelect: Locator;
  readonly sourceFieldInput: Locator;
  readonly targetEntityInput: Locator;
  readonly allowedEntityTypesInput: Locator;
  readonly maxDepthInput: Locator;
  readonly expansionCapInput: Locator;
  readonly saveButton: Locator;
  readonly loadingSpinner: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.nameInput = page.getByRole('textbox', { name: 'Name', exact: true });
    this.kindSelect = page.locator('label:has-text("Kind") select');
    this.entityInput = page.getByRole('textbox', { name: 'Entity', exact: true });
    this.featureNameInput = page.getByRole('textbox', { name: 'Feature name' });
    this.windowSelect = page.locator('label:has-text("Window") select');
    this.entityKeyInput = page.locator('label:has-text("Entity key field") input');
    this.aggregationSelect = page.locator('label:has-text("Aggregation") select');
    this.sourceFieldInput = page.locator('label:has-text("Source field") input');
    this.targetEntityInput = page.locator('label:has-text("Target entity") input');
    this.allowedEntityTypesInput = page.locator('label:has-text("Allowed entity types") input');
    this.maxDepthInput = page.locator('label:has-text("Max depth") input');
    this.expansionCapInput = page.locator('label:has-text("Expansion cap") input');
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

  async createGraphFeature(name: string, featureName: string) {
    await this.nameInput.fill(name);
    await this.kindSelect.selectOption('graph');
    await this.entityInput.fill('user');
    await this.featureNameInput.fill(featureName);
    await this.windowSelect.selectOption({ label: '90d' });
    await this.entityKeyInput.fill('user_id');
    await this.targetEntityInput.fill('card');
    await this.allowedEntityTypesInput.fill('user, account, card, device');
    await this.maxDepthInput.fill('4');
    await this.expansionCapInput.fill('10000');
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
