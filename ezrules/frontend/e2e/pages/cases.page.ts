import { Locator, Page } from '@playwright/test';

export class CasesPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly casesTable: Locator;
  readonly caseRows: Locator;
  readonly detail: Locator;
  readonly resolutionNote: Locator;
  readonly resolveButton: Locator;
  readonly eventsList: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.casesTable = page.locator('[data-testid="cases-table"]');
    this.caseRows = page.locator('[data-testid="case-row"]');
    this.detail = page.locator('[data-testid="case-detail"]');
    this.resolutionNote = page.locator('[data-testid="case-resolution-note"]');
    this.resolveButton = page.locator('[data-testid="case-resolve-button"]');
    this.eventsList = page.locator('[data-testid="case-events"]');
  }

  async goto() {
    await this.page.goto('/cases');
  }

  async waitForLoad() {
    await this.heading.waitFor({ state: 'visible', timeout: 10000 });
  }
}
