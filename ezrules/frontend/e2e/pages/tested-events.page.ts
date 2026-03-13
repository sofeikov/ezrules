import { Page, Locator } from '@playwright/test';

export class TestedEventsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly limitSelect: Locator;
  readonly table: Locator;
  readonly rows: Locator;
  readonly emptyState: Locator;
  readonly detailsButtons: Locator;
  readonly detailsPanels: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.limitSelect = page.locator('#tested-events-limit');
    this.table = page.locator('[data-testid="tested-events-table"]');
    this.rows = page.locator('[data-testid="tested-event-row"]');
    this.emptyState = page.locator('[data-testid="tested-events-empty"]');
    this.detailsButtons = page.locator('[data-testid="tested-event-details-button"]');
    this.detailsPanels = page.locator('[data-testid="tested-event-details"]');
  }

  async goto() {
    await this.page.goto('/tested-events');
  }

  async waitForPageToLoad() {
    await this.page.locator('[data-testid="tested-events-table"], [data-testid="tested-events-empty"]').first().waitFor();
  }

  async getEventCount(): Promise<number> {
    await this.waitForPageToLoad();
    if (await this.emptyState.isVisible()) {
      return 0;
    }
    return this.rows.count();
  }

  async expandFirstEvent() {
    await this.detailsButtons.first().click();
  }
}
