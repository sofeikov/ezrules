import { Locator, Page } from '@playwright/test';

export class RolloutsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly emptyState: Locator;
  readonly rolloutsTable: Locator;
  readonly promoteDialog: Locator;
  readonly removeDialog: Locator;
  readonly cancelPromoteButton: Locator;
  readonly cancelRemoveButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.emptyState = page.locator('[data-testid="rollouts-empty-state"]');
    this.rolloutsTable = page.locator('[data-testid="rollouts-table"]');
    this.promoteDialog = page.locator('[data-testid="promote-rollout-dialog"]');
    this.removeDialog = page.locator('[data-testid="remove-rollout-dialog"]');
    this.cancelPromoteButton = page.locator('[data-testid="cancel-promote-rollout-button"]');
    this.cancelRemoveButton = page.locator('[data-testid="cancel-remove-rollout-button"]');
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
    await this.cancelPromoteButton.click();
  }

  async clickRemoveButton(index: number = 0) {
    await this.page.locator('[data-testid="remove-rollout-button"]').nth(index).click();
  }

  async clickCancelRemoveButton() {
    await this.cancelRemoveButton.click();
  }
}
