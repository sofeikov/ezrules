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
  readonly reorderRulesButton: Locator;
  readonly saveOrderButton: Locator;
  readonly cancelOrderButton: Locator;

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
    this.reorderRulesButton = page.getByRole('button', { name: 'Reorder Rules' });
    this.saveOrderButton = page.getByRole('button', { name: 'Save Order' });
    this.cancelOrderButton = page.getByRole('button', { name: 'Cancel' });
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

  rowByRid(rid: string): Locator {
    return this.page.locator('tbody tr').filter({ hasText: rid }).first();
  }

  async getOrderForRule(rid: string): Promise<string> {
    const row = this.rowByRid(rid);
    return ((await row.locator('td').nth(1).textContent()) || '').trim();
  }

  async getRowIndexForRule(rid: string): Promise<number> {
    const rows = await this.page.locator('tbody tr').all();
    for (let index = 0; index < rows.length; index += 1) {
      if (await rows[index].filter({ hasText: rid }).count()) {
        return index;
      }
    }
    return -1;
  }

  async enterReorderMode() {
    await this.reorderRulesButton.click();
  }

  async moveRuleDown(rid: string) {
    await this.rowByRid(rid).getByRole('button', { name: 'Move rule down' }).click();
  }

  async moveRuleUp(rid: string) {
    await this.rowByRid(rid).getByRole('button', { name: 'Move rule up' }).click();
  }

  async moveRuleToPosition(rid: string, position: number) {
    const row = this.rowByRid(rid);
    await row.getByRole('button', { name: 'Enter exact position' }).click();
    await row.locator('input[type="number"]').fill(String(position));
    await row.getByRole('button', { name: 'Go' }).click();
  }
}
