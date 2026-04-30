import { Locator, Page } from '@playwright/test';

export class AlertsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly nameInput: Locator;
  readonly outcomeSelect: Locator;
  readonly thresholdInput: Locator;
  readonly createButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.nameInput = page.locator('[data-testid="alert-rule-name-input"]');
    this.outcomeSelect = page.locator('[data-testid="alert-rule-outcome-select"]');
    this.thresholdInput = page.locator('[data-testid="alert-rule-threshold-input"]');
    this.createButton = page.locator('[data-testid="create-alert-rule-button"]');
  }

  async goto() {
    await this.page.goto('/alerts');
  }

  async waitForLoad() {
    await this.heading.waitFor({ state: 'visible', timeout: 10000 });
  }

  async createRule(name: string, outcome: string, threshold: number) {
    await this.nameInput.fill(name);
    await this.outcomeSelect.selectOption(outcome);
    await this.thresholdInput.fill(String(threshold));
    await this.createButton.click();
  }
}
