import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Outcomes management page.
 * Encapsulates all interactions with the outcomes UI.
 */
export class OutcomesPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly outcomeInput: Locator;
  readonly addOutcomeButton: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly outcomeCountText: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.outcomeInput = page.locator('input[placeholder="Enter outcome name"]');
    this.addOutcomeButton = page.locator('button:has-text("Add Outcome")');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('.bg-red-50.border-red-200');
    this.outcomeCountText = page.locator('text=/\\d+ outcomes? total/');
  }

  /**
   * Navigate to the outcomes page
   */
  async goto() {
    await this.page.goto('/outcomes');
  }

  /**
   * Wait for outcomes list to be rendered (count text visible)
   */
  async waitForOutcomesToLoad() {
    await this.outcomeCountText.waitFor({ state: 'visible' });
  }

  /**
   * Get the number of outcome items displayed
   */
  async getOutcomeCount(): Promise<number> {
    await this.waitForOutcomesToLoad();
    return await this.page.locator('ul li').count();
  }

  /**
   * Check whether an outcome with the given name is visible in the list
   */
  async hasOutcome(outcomeName: string): Promise<boolean> {
    await this.waitForOutcomesToLoad();
    return await this.page.locator('li:has-text("' + outcomeName + '")').isVisible();
  }

  /**
   * Type an outcome name and click Add Outcome
   */
  async addOutcome(name: string) {
    await this.outcomeInput.fill(name);
    await this.addOutcomeButton.click();
  }

  /**
   * Click the Delete button for a specific outcome
   */
  async clickDelete(outcomeName: string) {
    const row = this.page.locator('li', { hasText: outcomeName });
    await row.locator('button:has-text("Delete")').click();
  }
}
