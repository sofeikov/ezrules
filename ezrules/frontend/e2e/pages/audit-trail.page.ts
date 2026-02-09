import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Audit Trail page.
 * Encapsulates all interactions with the audit trail UI.
 */
export class AuditTrailPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly description: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly ruleHistoryHeading: Locator;
  readonly configHistoryHeading: Locator;
  readonly ruleHistoryTable: Locator;
  readonly configHistoryTable: Locator;
  readonly ruleHistoryRows: Locator;
  readonly configHistoryRows: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.description = page.locator('text=History of rule and configuration changes');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('.bg-red-50.border-red-200');
    this.ruleHistoryHeading = page.locator('h2:has-text("Rule History")');
    this.configHistoryHeading = page.locator('h2:has-text("Configuration History")');
    this.ruleHistoryTable = page.locator('table').first();
    this.configHistoryTable = page.locator('table').last();
    this.ruleHistoryRows = page.locator('table').first().locator('tbody tr');
    this.configHistoryRows = page.locator('table').last().locator('tbody tr');
  }

  async goto() {
    await this.page.goto('/audit');
  }

  async waitForPageToLoad() {
    await this.heading.waitFor({ state: 'visible' });
    // Wait for loading spinner to disappear
    await this.loadingSpinner.waitFor({ state: 'hidden', timeout: 10000 }).catch(() => {});
  }

  async getRuleHistoryRowCount(): Promise<number> {
    return await this.ruleHistoryRows.count();
  }

  async getConfigHistoryRowCount(): Promise<number> {
    return await this.configHistoryRows.count();
  }

  async getRuleHistoryColumnHeaders(): Promise<string[]> {
    const headers = this.ruleHistoryTable.locator('thead th');
    const count = await headers.count();
    const result: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await headers.nth(i).textContent();
      if (text) result.push(text.trim());
    }
    return result;
  }

  async getConfigHistoryColumnHeaders(): Promise<string[]> {
    const headers = this.configHistoryTable.locator('thead th');
    const count = await headers.count();
    const result: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await headers.nth(i).textContent();
      if (text) result.push(text.trim());
    }
    return result;
  }
}
