import { Page, Locator } from '@playwright/test';

export class RuleQualityPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly minSupportInput: Locator;
  readonly lookbackDaysInput: Locator;
  readonly refreshReportButton: Locator;
  readonly labeledEventsCardLabel: Locator;
  readonly rulesAnalyzedCardLabel: Locator;
  readonly pairMetricsHeading: Locator;
  readonly noDataMessage: Locator;
  readonly ruleLinks: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.minSupportInput = page.locator('#rule-quality-minSupport');
    this.lookbackDaysInput = page.locator('#rule-quality-lookbackDays');
    this.refreshReportButton = page.locator('#rule-quality-refreshReport');
    this.labeledEventsCardLabel = page.getByText('Labeled Events', { exact: true });
    this.rulesAnalyzedCardLabel = page.getByText('Rules Analyzed', { exact: true });
    this.pairMetricsHeading = page.locator('h2:has-text("Pair Metrics")');
    this.noDataMessage = page.locator('text=No rule-quality pairs available');
    this.ruleLinks = page.locator('[data-testid=\"rule-quality-rule-link\"]');
  }

  async goto() {
    await this.page.goto('/rule-quality');
  }

  async waitForPageToLoad() {
    await this.heading.waitFor({ state: 'visible' });
    await this.pairMetricsHeading.waitFor({ state: 'visible' });
  }

  async setMinSupport(value: number) {
    await this.minSupportInput.fill(String(value));
    await this.minSupportInput.press('Tab');
  }

  async setLookbackDays(value: number) {
    await this.lookbackDaysInput.fill(String(value));
    await this.lookbackDaysInput.press('Tab');
  }

  async refreshReport() {
    await this.refreshReportButton.click();
  }

  async getPairMetricRowCount(): Promise<number> {
    const rows = this.page.locator('table:has(th:has-text("Outcome")) tbody tr');
    return rows.count();
  }
}
