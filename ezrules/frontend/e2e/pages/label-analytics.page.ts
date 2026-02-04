import { Page, Locator } from '@playwright/test';

export class LabelAnalyticsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly totalLabeledValue: Locator;
  readonly totalLabeledLabel: Locator;
  readonly labelsOverTimeHeading: Locator;
  readonly timeRangeSelect: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly noDataMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.totalLabeledValue = page.locator('.text-5xl.font-bold.text-blue-600');
    this.totalLabeledLabel = page.locator('text=Total Labeled Events');
    this.labelsOverTimeHeading = page.locator('h2:has-text("Labels Over Time")');
    this.timeRangeSelect = page.locator('select');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('.bg-red-50.border-red-200');
    this.noDataMessage = page.locator('text=No label data available');
  }

  async goto() {
    await this.page.goto('/label_analytics');
  }

  async waitForPageToLoad() {
    await this.totalLabeledLabel.waitFor({ state: 'visible' });
    await this.totalLabeledValue.waitFor({ state: 'visible' });
  }

  async getTotalLabeled(): Promise<string> {
    await this.waitForPageToLoad();
    return (await this.totalLabeledValue.textContent()) || '';
  }

  async selectTimeRange(value: string) {
    await this.timeRangeSelect.selectOption(value);
  }

  async getChartCount(): Promise<number> {
    return await this.page.locator('canvas[id^="labelChart_"]').count();
  }

  async getChartTitles(): Promise<string[]> {
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
