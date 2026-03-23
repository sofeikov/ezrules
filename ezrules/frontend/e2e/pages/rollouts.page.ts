import { Locator, Page } from '@playwright/test';

export class RolloutsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly emptyState: Locator;
  readonly rolloutsTable: Locator;
  readonly promoteDialog: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.emptyState = page.locator('[data-testid="rollouts-empty-state"]');
    this.rolloutsTable = page.locator('[data-testid="rollouts-table"]');
    this.promoteDialog = page.locator('[data-testid="promote-rollout-dialog"]');
  }

  async goto() {
    await this.page.goto('/rule-rollouts');
  }

  async waitForLoad() {
    await this.page.waitForSelector('h1', { state: 'visible' });
    await this.page.waitForFunction(() => {
      const spinners = document.querySelectorAll('.animate-spin');
      return spinners.length === 0;
    }, { timeout: 10000 }).catch(() => {});
  }

  async getRolloutCount(): Promise<number> {
    return this.page.locator('[data-testid="rollouts-table"] > div').count();
  }

  async clickPromoteButton(index: number = 0) {
    await this.page.locator('[data-testid="promote-rollout-button"]').nth(index).click();
  }

  async clickCancelPromoteButton() {
    await this.page.getByRole('button', { name: 'Cancel' }).click();
  }
}
