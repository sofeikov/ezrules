import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Backtesting UI on the Rule Detail page.
 * Encapsulates interactions with the backtest button, results card, and accordion.
 */
export class BacktestingPage {
  readonly page: Page;
  readonly backtestButton: Locator;
  readonly backtestResultsCard: Locator;
  readonly backtestItems: Locator;
  readonly backtestError: Locator;

  constructor(page: Page) {
    this.page = page;
    this.backtestButton = page.locator('[data-testid="backtest-button"]');
    this.backtestResultsCard = page.locator('[data-testid="backtest-results-card"]');
    this.backtestItems = page.locator('[data-testid^="backtest-item-"]');
    this.backtestError = page.locator('[data-testid="backtest-button"]').locator('..').locator('.bg-red-50');
  }

  async clickBacktest() {
    await this.backtestButton.click();
  }

  async waitForBacktestResults() {
    await this.backtestResultsCard.waitFor({ state: 'visible', timeout: 15000 });
  }

  async getResultCount(): Promise<number> {
    return await this.backtestItems.count();
  }

  async expandResult(index: number) {
    const item = this.backtestItems.nth(index);
    const header = item.locator('button').first();
    await header.click();
  }

  async getResultStatus(index: number): Promise<string> {
    const badge = this.page.locator(`[data-testid="backtest-status-${index}"]`);
    return ((await badge.textContent()) || '').trim();
  }

  async waitForExpandedContent() {
    await this.page.locator('[data-testid="backtest-expanded-content"]').first().waitFor({ state: 'visible', timeout: 15000 });
  }

  async getDiffSection(): Promise<Locator> {
    return this.page.locator('[data-testid="backtest-diff"]').first();
  }

  async getOutcomeTable(): Promise<Locator> {
    return this.page.locator('[data-testid="backtest-outcome-table"]').first();
  }
}
