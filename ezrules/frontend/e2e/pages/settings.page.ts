import { Page, Locator } from '@playwright/test';

export class SettingsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly lookbackDaysInput: Locator;
  readonly saveButton: Locator;
  readonly successMessage: Locator;
  readonly pairOutcomeSelect: Locator;
  readonly pairLabelSelect: Locator;
  readonly addPairButton: Locator;
  readonly pairsTable: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.lookbackDaysInput = page.locator('#settings-ruleQualityLookbackDays');
    this.saveButton = page.locator('#settings-saveRuntimeSettings');
    this.successMessage = page.locator('text=Settings saved successfully.');
    this.pairOutcomeSelect = page.locator('#settings-pairOutcome');
    this.pairLabelSelect = page.locator('#settings-pairLabel');
    this.addPairButton = page.locator('#settings-addPair');
    this.pairsTable = page.locator('#settings-pairsTable');
  }

  async goto() {
    await this.page.goto('/settings');
  }

  async waitForPageToLoad() {
    await this.heading.waitFor({ state: 'visible' });
    await this.lookbackDaysInput.waitFor({ state: 'visible' });
    await this.pairsTable.waitFor({ state: 'visible' });
  }

  async getLookbackDays(): Promise<number> {
    const value = await this.lookbackDaysInput.inputValue();
    return Number(value);
  }

  async setLookbackDays(value: number) {
    await this.lookbackDaysInput.fill(String(value));
  }

  async save() {
    await this.saveButton.click();
  }

  async addPair(outcome: string, label: string) {
    await this.pairOutcomeSelect.selectOption(outcome);
    await this.pairLabelSelect.selectOption(label);
    await this.addPairButton.click();
  }

  async getPairRowCount(): Promise<number> {
    return this.page.locator('#settings-pairsTable tbody tr').count();
  }
}
