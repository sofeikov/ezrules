import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Shadow Rules page.
 */
export class ShadowRulesPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly emptyState: Locator;
  readonly shadowRulesTable: Locator;
  readonly loadingSpinner: Locator;
  readonly promoteDialog: Locator;
  readonly confirmPromoteButton: Locator;
  readonly cancelPromoteButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.emptyState = page.locator('[data-testid="empty-state"]');
    this.shadowRulesTable = page.locator('[data-testid="shadow-rules-table"]');
    this.loadingSpinner = page.locator('.animate-spin');
    this.promoteDialog = page.locator('[data-testid="promote-dialog"]');
    this.confirmPromoteButton = page.locator('[data-testid="confirm-promote-button"]');
    this.cancelPromoteButton = page.locator('[data-testid="cancel-promote-button"]');
  }

  async goto() {
    await this.page.goto('/shadow-rules');
  }

  async waitForLoad() {
    await this.page.waitForSelector('h1', { state: 'visible' });
    // Wait for loading spinner to disappear
    await this.page.waitForFunction(() => {
      const spinners = document.querySelectorAll('.animate-spin');
      return spinners.length === 0;
    }, { timeout: 10000 }).catch(() => {});
  }

  async clickPromoteButton(index: number = 0) {
    const buttons = this.page.locator('[data-testid="promote-button"]');
    await buttons.nth(index).click();
  }

  async clickRemoveButton(index: number = 0) {
    const buttons = this.page.locator('[data-testid="remove-shadow-button"]');
    await buttons.nth(index).click();
  }

  async getShadowRuleCount(): Promise<number> {
    const rows = this.page.locator('[data-testid="shadow-rules-table"] tbody tr');
    return rows.count();
  }
}
