import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Rule Detail page.
 * Encapsulates all interactions with the rule detail UI.
 */
export class RuleDetailPage {
  readonly page: Page;
  readonly breadcrumb: Locator;
  readonly backToRulesLink: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly ruleIdField: Locator;
  readonly descriptionField: Locator;
  readonly logicTextarea: Locator;
  readonly createdDateField: Locator;
  readonly testJsonTextarea: Locator;
  readonly testRuleButton: Locator;
  readonly testResultSuccess: Locator;
  readonly testResultError: Locator;
  readonly backButton: Locator;
  readonly revisionsSection: Locator;

  constructor(page: Page) {
    this.page = page;
    this.breadcrumb = page.locator('nav.mb-6');
    this.backToRulesLink = page.locator('nav.mb-6 a:has-text("All Rules")');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('text=/Failed to load rule/i');
    this.ruleIdField = page.locator('label:has-text("Rule ID") + div');
    this.descriptionField = page.locator('label:has-text("Description") + div');
    this.logicTextarea = page.locator('textarea[readonly]').first();
    this.createdDateField = page.locator('label:has-text("Created") + div');
    this.testJsonTextarea = page.locator('textarea:not([readonly])');
    this.testRuleButton = page.locator('button:has-text("Test Rule")');
    this.testResultSuccess = page.locator('.bg-green-50');
    this.testResultError = page.locator('.bg-red-50').or(page.locator('text=/Failed to load rule/i'));
    this.backButton = page.locator('button:has-text("Back to Rules")');
    this.revisionsSection = page.locator('text=Other Rule Versions');
  }

  /**
   * Navigate to the rule detail page by rule ID
   */
  async goto(ruleId: number) {
    await this.page.goto(`/rules/${ruleId}`);
  }

  /**
   * Wait for the rule detail page to be loaded
   */
  async waitForRuleToLoad() {
    await this.ruleIdField.waitFor({ state: 'visible' });
  }

  /**
   * Get the rule ID displayed on the page
   */
  async getRuleId(): Promise<string> {
    await this.waitForRuleToLoad();
    return ((await this.ruleIdField.textContent()) || '').trim();
  }

  /**
   * Get the rule description
   */
  async getDescription(): Promise<string> {
    await this.waitForRuleToLoad();
    return ((await this.descriptionField.textContent()) || '').trim();
  }

  /**
   * Get the rule logic
   */
  async getLogic(): Promise<string> {
    await this.waitForRuleToLoad();
    return (await this.logicTextarea.inputValue()) || '';
  }

  /**
   * Set test JSON in the test textarea
   */
  async setTestJson(json: string) {
    await this.testJsonTextarea.click();
    await this.testJsonTextarea.clear();
    await this.testJsonTextarea.fill(json);
  }

  /**
   * Click the test rule button
   */
  async clickTestRule() {
    await this.testRuleButton.click();
  }

  /**
   * Click the back button
   */
  async clickBack() {
    await this.backButton.click();
  }

  /**
   * Navigate back via breadcrumb
   */
  async clickBreadcrumbBack() {
    await this.backToRulesLink.click();
  }

  /**
   * Test TAB key functionality in textarea
   */
  async testTabInTextarea(textarea: Locator): Promise<boolean> {
    await textarea.click();
    const valueBefore = await textarea.inputValue();
    await textarea.press('Tab');
    const valueAfter = await textarea.inputValue();
    // If Tab was captured, value should have changed (tab character added)
    // If Tab wasn't captured, focus would move and value stays the same
    return valueAfter !== valueBefore || valueAfter.includes('\t');
  }
}
