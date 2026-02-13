import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Labels management page.
 * Encapsulates all interactions with the labels UI.
 */
export class LabelsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly labelInput: Locator;
  readonly addLabelButton: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly labelCountText: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.labelInput = page.locator('input[placeholder="Enter label name"]');
    this.addLabelButton = page.locator('button:has-text("Add Label")');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('.bg-red-50.border-red-200');
    this.labelCountText = page.locator('text=/\\d+ labels? total/');
  }

  /**
   * Navigate to the labels page
   */
  async goto() {
    await this.page.goto('/labels');
  }

  /**
   * Wait for labels list to be rendered (count text visible)
   */
  async waitForLabelsToLoad() {
    await this.labelCountText.waitFor({ state: 'visible' });
  }

  /**
   * Get the number of label items displayed
   */
  async getLabelCount(): Promise<number> {
    await this.waitForLabelsToLoad();
    return await this.page.locator('ul li').count();
  }

  /**
   * Check whether a label with the given name is visible in the list
   */
  async hasLabel(labelName: string): Promise<boolean> {
    await this.waitForLabelsToLoad();
    return await this.page.locator('li:has-text("' + labelName + '")').isVisible();
  }

  /**
   * Type a label name and click Add Label
   */
  async addLabel(name: string) {
    await this.labelInput.fill(name);
    await this.addLabelButton.click();
  }

  /**
   * Click the Delete button for a specific label
   */
  async clickDelete(labelName: string) {
    const row = this.page.locator('li', { hasText: labelName });
    await row.locator('button:has-text("Delete")').click();
  }
}
