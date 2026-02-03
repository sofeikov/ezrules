import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Rule History (diff timeline) page.
 */
export class RuleHistoryPage {
  readonly page: Page;
  readonly breadcrumb: Locator;
  readonly backToRuleLink: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly pageTitle: Locator;
  readonly legend: Locator;
  readonly diffCards: Locator;
  readonly singleVersionMessage: Locator;
  readonly addedHighlights: Locator;
  readonly removedHighlights: Locator;
  readonly descriptionChangeIndicator: Locator;

  constructor(page: Page) {
    this.page = page;
    this.breadcrumb = page.locator('nav.mb-6');
    this.backToRuleLink = page.locator('a:has-text("Back to rule")');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('text=/Failed to load rule history/i');
    this.pageTitle = page.locator('h1:has-text("Revision history for")');
    this.legend = page.locator('text=Added').first();
    this.diffCards = page.locator('.space-y-8 > div');
    this.singleVersionMessage = page.locator('text=only one version');
    this.addedHighlights = page.locator('.bg-green-100');
    this.removedHighlights = page.locator('.bg-red-100');
    this.descriptionChangeIndicator = page.locator('text=Description changed');
  }

  /**
   * Navigate to the history page for a given rule ID
   */
  async goto(ruleId: number) {
    await this.page.goto(`/rules/${ruleId}/history`);
  }

  /**
   * Wait for the history page to finish loading
   */
  async waitForHistoryToLoad() {
    await this.loadingSpinner.waitFor({ state: 'hidden', timeout: 10000 });
  }

  /**
   * Get the number of diff cards (revision transitions) displayed
   */
  async getDiffCardCount(): Promise<number> {
    return await this.diffCards.count();
  }

  /**
   * Click the "Back to rule" link
   */
  async clickBackToRule() {
    await this.backToRuleLink.first().click();
  }

  /**
   * Click the rule link in the breadcrumb
   */
  async clickBreadcrumbRule() {
    // The breadcrumb has: All Rules > <rid> > History
    // Click the rid link (second link in breadcrumb)
    await this.breadcrumb.locator('a').nth(1).click();
  }
}
