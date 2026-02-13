import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Dashboard page.
 * Encapsulates all interactions with the dashboard UI.
 */
export class DashboardPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly activeRulesValue: Locator;
  readonly activeRulesLabel: Locator;
  readonly transactionVolumeHeading: Locator;
  readonly outcomesHeading: Locator;
  readonly timeRangeSelect: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.activeRulesValue = page.locator('.text-5xl.font-bold.text-blue-600');
    this.activeRulesLabel = page.locator('text=Active Rules');
    this.transactionVolumeHeading = page.locator('h2:has-text("Transaction Volume")');
    this.outcomesHeading = page.locator('h2:has-text("Rule Outcomes Over Time")');
    this.timeRangeSelect = page.locator('select');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('.bg-red-50.border-red-200');
  }

  async goto() {
    await this.page.goto('/dashboard');
  }

  async waitForPageToLoad() {
    await this.activeRulesLabel.waitFor({ state: 'visible' });
    await this.activeRulesValue.waitFor({ state: 'visible' });
  }

  async getActiveRulesCount(): Promise<string> {
    await this.waitForPageToLoad();
    return (await this.activeRulesValue.textContent()) || '';
  }

  async selectTimeRange(value: string) {
    await this.timeRangeSelect.selectOption(value);
  }

  async getTransactionVolumeChartCount(): Promise<number> {
    return await this.page.locator('canvas#transactionVolumeChart').count();
  }

  async getOutcomeChartCount(): Promise<number> {
    return await this.page.locator('canvas[id^="outcomeChart_"]').count();
  }

  async getOutcomeChartTitles(): Promise<string[]> {
    const titles = this.page.locator('h3');
    const count = await titles.count();
    const result: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await titles.nth(i).textContent();
      if (text) result.push(text.trim());
    }
    return result;
  }
}
