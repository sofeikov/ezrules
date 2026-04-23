import { Page, Locator } from '@playwright/test';

export class SettingsPage {
  readonly autoPromoteActiveRuleUpdatesCheckbox: Locator;
  readonly page: Page;
  readonly heading: Locator;
  readonly lookbackDaysInput: Locator;
  readonly neutralOutcomeSelect: Locator;
  readonly strictModeCard: Locator;
  readonly strictModeStatus: Locator;
  readonly strictModeCheckbox: Locator;
  readonly strictModeSaveButton: Locator;
  readonly strictModeAuditLink: Locator;
  readonly strictModeDisableDialog: Locator;
  readonly strictModeDisableConfirmationInput: Locator;
  readonly strictModeDisableConfirmButton: Locator;
  readonly saveButton: Locator;
  readonly outcomeHierarchySaveButton: Locator;
  readonly successMessage: Locator;
  readonly invalidAllowlistRulesNotice: Locator;
  readonly pairOutcomeSelect: Locator;
  readonly pairLabelSelect: Locator;
  readonly addPairButton: Locator;
  readonly pairsTable: Locator;
  readonly aiProviderSelect: Locator;
  readonly aiModelInput: Locator;
  readonly aiApiKeyInput: Locator;
  readonly aiEnabledCheckbox: Locator;
  readonly saveAiSettingsButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.autoPromoteActiveRuleUpdatesCheckbox = page.locator('#settings-autoPromoteActiveRuleUpdates');
    this.lookbackDaysInput = page.locator('#settings-ruleQualityLookbackDays');
    this.neutralOutcomeSelect = page.locator('#settings-neutralOutcome');
    this.strictModeCard = page.locator('#settings-strictModeCard');
    this.strictModeStatus = page.locator('#settings-strictModeStatus');
    this.strictModeCheckbox = page.locator('#settings-strictModeEnabled');
    this.strictModeSaveButton = page.locator('#settings-saveStrictMode');
    this.strictModeAuditLink = page.locator('#settings-strictModeAuditLink');
    this.strictModeDisableDialog = page.locator('[data-testid="strict-mode-disable-dialog"]');
    this.strictModeDisableConfirmationInput = page.locator('#settings-strictModeDisableConfirmation');
    this.strictModeDisableConfirmButton = page.locator('#settings-confirmDisableStrictMode');
    this.saveButton = page.locator('#settings-saveRuntimeSettings');
    this.outcomeHierarchySaveButton = page.locator('#settings-saveOutcomeHierarchy');
    this.successMessage = page.locator('text=Settings saved successfully.');
    this.invalidAllowlistRulesNotice = page.locator('#settings-invalidAllowlistRulesNotice');
    this.pairOutcomeSelect = page.locator('#settings-pairOutcome');
    this.pairLabelSelect = page.locator('#settings-pairLabel');
    this.addPairButton = page.locator('#settings-addPair');
    this.pairsTable = page.locator('#settings-pairsTable');
    this.aiProviderSelect = page.locator('#settings-aiProvider');
    this.aiModelInput = page.locator('#settings-aiModel');
    this.aiApiKeyInput = page.locator('#settings-aiApiKey');
    this.aiEnabledCheckbox = page.locator('#settings-aiEnabled');
    this.saveAiSettingsButton = page.locator('#settings-saveAiAuthoring');
  }

  async goto() {
    await this.page.goto('/settings');
  }

  async waitForPageToLoad() {
    await this.heading.waitFor({ state: 'visible' });
    await this.strictModeCard.waitFor({ state: 'visible' });
    await this.autoPromoteActiveRuleUpdatesCheckbox.waitFor({ state: 'visible' });
    await this.lookbackDaysInput.waitFor({ state: 'visible' });
    await this.neutralOutcomeSelect.waitFor({ state: 'visible' });
    await this.page.locator('[id^="settings-outcome-row-"]').first().waitFor({ state: 'visible' });
    await this.pairsTable.waitFor({ state: 'visible' });
    await this.aiProviderSelect.waitFor({ state: 'visible' });
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

  async setAiProvider(value: string) {
    await this.aiProviderSelect.selectOption(value);
  }

  async getAiProvider(): Promise<string> {
    return this.aiProviderSelect.inputValue();
  }

  async setAiModel(value: string) {
    await this.aiModelInput.fill(value);
  }

  async getAiModel(): Promise<string> {
    return this.aiModelInput.inputValue();
  }

  async setAiApiKey(value: string) {
    await this.aiApiKeyInput.fill(value);
  }

  async setAiEnabled(value: boolean) {
    const currentValue = await this.aiEnabledCheckbox.isChecked();
    if (currentValue !== value) {
      await this.aiEnabledCheckbox.click();
    }
  }

  async saveAiSettings() {
    await this.saveAiSettingsButton.click();
  }

  async isStrictModeEnabled(): Promise<boolean> {
    return this.strictModeCheckbox.isChecked();
  }

  async setStrictModeEnabled(value: boolean) {
    const currentValue = await this.strictModeCheckbox.isChecked();
    if (currentValue !== value) {
      await this.strictModeCheckbox.click();
    }
  }

  async saveStrictMode() {
    await this.strictModeSaveButton.click();
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
