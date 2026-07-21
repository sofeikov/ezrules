import { Locator, Page } from '@playwright/test';

export class OperationsDashboardPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly period: Locator;
  readonly refresh: Locator;
  readonly retry: Locator;
  readonly activeCases: Locator;
  readonly unassignedCases: Locator;
  readonly resolvedCases: Locator;
  readonly falsePositiveRate: Locator;
  readonly attentionTable: Locator;
  readonly rulesTable: Locator;
  readonly openCases: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: 'Operations', exact: true });
    this.period = page.getByTestId('operations-period');
    this.refresh = page.getByTestId('operations-refresh');
    this.retry = page.getByTestId('operations-retry');
    this.activeCases = page.getByTestId('operations-active-cases');
    this.unassignedCases = page.getByTestId('operations-unassigned-cases');
    this.resolvedCases = page.getByTestId('operations-resolved-cases');
    this.falsePositiveRate = page.getByTestId('operations-false-positive-rate');
    this.attentionTable = page.getByTestId('operations-attention-table');
    this.rulesTable = page.getByTestId('operations-rules-table');
    this.openCases = page.getByTestId('operations-open-cases');
  }

  async goto(): Promise<void> {
    await this.page.goto('/operations');
  }
}
