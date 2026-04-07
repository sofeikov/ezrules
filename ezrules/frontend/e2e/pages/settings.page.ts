import { Page, Locator } from '@playwright/test';

export class SettingsPage {
  readonly autoPromoteActiveRuleUpdatesCheckbox: Locator;
  readonly page: Page;
  readonly heading: Locator;
  readonly lookbackDaysInput: Locator;
  readonly neutralOutcomeSelect: Locator;
  readonly saveButton: Locator;
  readonly outcomeHierarchySaveButton: Locator;
  readonly successMessage: Locator;
  readonly invalidAllowlistRulesNotice: Locator;
  readonly pairOutcomeSelect: Locator;
  readonly pairLabelSelect: Locator;
  readonly addPairButton: Locator;
  readonly pairsTable: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.autoPromoteActiveRuleUpdatesCheckbox = page.locator('#settings-autoPromoteActiveRuleUpdates');
    this.lookbackDaysInput = page.locator('#settings-ruleQualityLookbackDays');
    this.neutralOutcomeSelect = page.locator('#settings-neutralOutcome');
    this.saveButton = page.locator('#settings-saveRuntimeSettings');
    this.outcomeHierarchySaveButton = page.locator('#settings-saveOutcomeHierarchy');
    this.successMessage = page.locator('text=Settings saved successfully.');
    this.invalidAllowlistRulesNotice = page.locator('#settings-invalidAllowlistRulesNotice');
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
    await this.autoPromoteActiveRuleUpdatesCheckbox.waitFor({ state: 'visible' });
    await this.lookbackDaysInput.waitFor({ state: 'visible' });
    await this.neutralOutcomeSelect.waitFor({ state: 'visible' });
    await this.outcomeHierarchySaveButton.waitFor({ state: 'visible' });
    await this.pairsTable.waitFor({ state: 'visible' });
  }

  async getLookbackDays(): Promise<number> {
    const value = await this.lookbackDaysInput.inputValue();
    return Number(value);
  }

  async setLookbackDays(value: number) {
    await this.lookbackDaysInput.fill(String(value));
  }

  async getNeutralOutcome(): Promise<string> {
    return this.neutralOutcomeSelect.inputValue();
  }

  async setNeutralOutcome(value: string) {
    await this.neutralOutcomeSelect.selectOption(value);
  }

  async isAutoPromoteActiveRuleUpdatesEnabled(): Promise<boolean> {
    return this.autoPromoteActiveRuleUpdatesCheckbox.isChecked();
  }

  async setAutoPromoteActiveRuleUpdates(value: boolean) {
    const currentValue = await this.autoPromoteActiveRuleUpdatesCheckbox.isChecked();
    if (currentValue !== value) {
      await this.autoPromoteActiveRuleUpdatesCheckbox.click();
    }
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

  async getOutcomeHierarchy(): Promise<string[]> {
    return this.page.locator('[id^="settings-outcome-name-"]').allTextContents();
  }

  async moveOutcomeDownByName(outcomeName: string) {
    const row = this.page.locator('[id^="settings-outcome-row-"]').filter({
      has: this.page.locator('.text-sm.font-medium.text-gray-900', { hasText: outcomeName }),
    }).first();
    await row.locator('button:has-text("Down")').click();
  }

  async saveOutcomeHierarchy() {
    await this.outcomeHierarchySaveButton.click();
  }
}
