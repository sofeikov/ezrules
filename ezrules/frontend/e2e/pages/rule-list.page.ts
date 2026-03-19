import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Rule List page.
 * Encapsulates all interactions with the rules list UI.
 */
export class RuleListPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly rulesTable: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly emptyStateMessage: Locator;
  readonly howToRunButton: Locator;
  readonly howToRunSection: Locator;
  readonly evaluateEndpointCode: Locator;
  readonly curlExample: Locator;
  readonly evaluateLink: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.rulesTable = page.locator('table');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('text=/Error loading rules/i');
    this.emptyStateMessage = page.locator('text=/No rules found/i');
    this.howToRunButton = page.locator('button', { hasText: 'How to Run' });
    this.howToRunSection = page.locator('.bg-blue-50');
    this.evaluateEndpointCode = page.locator('.bg-blue-50 code').first();
    this.curlExample = page.locator('.bg-gray-900.text-gray-100');
    this.evaluateLink = page.getByRole('link', { name: 'Evaluate' });
  }

  /**
   * Navigate to the rules list page
   */
  async goto() {
    await this.page.goto('/rules');
  }

  /**
   * Wait for the rules table to be loaded and visible
   */
  async waitForRulesToLoad() {
    await this.rulesTable.waitFor({ state: 'visible' });
  }

  /**
   * Get the count of rules displayed in the table
   * @returns Number of rule rows (excluding header)
   */
  async getRuleCount(): Promise<number> {
    await this.waitForRulesToLoad();
    const rows = await this.page.locator('tbody tr').count();
    return rows;
  }

  /**
   * Toggle the "How to Run" section visibility
   */
  async toggleHowToRun() {
    await this.howToRunButton.click();
  }

  /**
   * Check if a specific rule exists in the table by RID
   * @param rid - Rule ID to search for
   */
  async hasRule(rid: string): Promise<boolean> {
    await this.waitForRulesToLoad();
    const ruleCell = this.page.locator(`td:has-text("${rid}")`);
    return await ruleCell.isVisible();
  }

  /**
   * Get the evaluator endpoint displayed on the page
   */
  async getEvaluatorEndpoint(): Promise<string> {
    return ((await this.evaluateEndpointCode.textContent()) || '').trim();
  }
}
