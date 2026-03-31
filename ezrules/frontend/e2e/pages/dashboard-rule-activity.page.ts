import { Locator, Page, Response } from '@playwright/test';

export class DashboardRuleActivityPage {
  readonly page: Page;
  readonly timeRangeSelect: Locator;
  readonly mostFiringCard: Locator;
  readonly leastFiringCard: Locator;
  readonly mostFiringHeading: Locator;
  readonly leastFiringHeading: Locator;
  readonly explanatoryNote: Locator;
  readonly mostFiringState: Locator;
  readonly leastFiringState: Locator;
  readonly mostFiringLinks: Locator;
  readonly leastFiringLinks: Locator;

  constructor(page: Page) {
    this.page = page;
    this.timeRangeSelect = page.getByTestId('dashboard-time-range');
    this.mostFiringCard = page.getByTestId('most-firing-rules-card');
    this.leastFiringCard = page.getByTestId('least-firing-rules-card');
    this.mostFiringHeading = page.getByRole('heading', { name: 'Most Firing Rules' });
    this.leastFiringHeading = page.getByRole('heading', { name: 'Least Firing Rules' });
    this.explanatoryNote = page.getByText('Fire counts reflect stored non-null rule outcomes.');
    this.mostFiringState = page.locator('[data-testid="most-firing-rules"], [data-testid="most-firing-rules-empty"]');
    this.leastFiringState = page.locator('[data-testid="least-firing-rules"], [data-testid="least-firing-rules-empty"]');
    this.mostFiringLinks = page.getByTestId('most-firing-rule-link');
    this.leastFiringLinks = page.getByTestId('least-firing-rule-link');
  }

  async goto() {
    await this.page.goto('/dashboard');
  }

  waitForRuleActivityResponse(aggregation: string): Promise<Response> {
    return this.page.waitForResponse(response =>
      response.url().includes('/api/v2/analytics/rule-activity') &&
      response.url().includes(`aggregation=${aggregation}`) &&
      response.request().method() === 'GET'
    );
  }

  async selectTimeRange(value: string) {
    await this.timeRangeSelect.selectOption(value);
  }
}
