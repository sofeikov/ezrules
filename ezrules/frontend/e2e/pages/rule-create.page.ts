import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Create Rule page.
 * Encapsulates all interactions with the rule creation UI.
 */
export class RuleCreatePage {
  readonly page: Page;
  readonly heading: Locator;
  readonly breadcrumb: Locator;
  readonly backToRulesLink: Locator;
  readonly ruleIdInput: Locator;
  readonly descriptionTextarea: Locator;
  readonly logicTextarea: Locator;
  readonly submitButton: Locator;
  readonly backButton: Locator;
  readonly testJsonTextarea: Locator;
  readonly testRuleButton: Locator;
  readonly testResultSuccess: Locator;
  readonly testResultError: Locator;
  readonly saveErrorMessage: Locator;
  readonly loadingSpinner: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.breadcrumb = page.locator('nav.mb-6');
    this.backToRulesLink = page.locator('nav.mb-6 a:has-text("All Rules")');
    this.ruleIdInput = page.locator('input[placeholder="Enter rule ID"]');
    this.descriptionTextarea = page.locator('label:has-text("Description") + textarea');
    this.logicTextarea = page.locator('label:has-text("Logic") + textarea');
    this.submitButton = page.locator('button:has-text("Create Rule")');
    this.backButton = page.locator('button:has-text("Back to Rules")');
    this.testJsonTextarea = page.locator('label:has-text("Test JSON") + textarea');
    this.testRuleButton = page.locator('button:has-text("Test Rule")');
    this.testResultSuccess = page.locator('.bg-green-50.border-green-200');
    this.testResultError = page.locator('.bg-red-50.border-red-200');
    this.saveErrorMessage = page.locator('.bg-red-50.border-red-200');
    this.loadingSpinner = page.locator('.animate-spin');
  }

  /**
   * Navigate to the create rule page
   */
  async goto() {
    await this.page.goto('/rules/create');
  }

  /**
   * Fill in the Rule ID field
   */
  async fillRuleId(value: string) {
    await this.ruleIdInput.fill(value);
  }

  /**
   * Fill in the Description field
   */
  async fillDescription(value: string) {
    await this.descriptionTextarea.fill(value);
  }

  /**
   * Fill in the Logic field
   */
  async fillLogic(value: string) {
    await this.logicTextarea.fill(value);
  }

  /**
   * Fill in the Test JSON field
   */
  async fillTestJson(value: string) {
    await this.testJsonTextarea.clear();
    await this.testJsonTextarea.fill(value);
  }

  /**
   * Click the Create Rule submit button
   */
  async clickSubmit() {
    await this.submitButton.click();
  }

  /**
   * Click the Back to Rules button
   */
  async clickBack() {
    await this.backButton.click();
  }

  /**
   * Click the Test Rule button
   */
  async clickTestRule() {
    await this.testRuleButton.click();
  }

  /**
   * Click the breadcrumb "All Rules" link
   */
  async clickBreadcrumbBack() {
    await this.backToRulesLink.click();
  }

  /**
   * Get the current value of the Test JSON textarea
   */
  async getTestJsonValue(): Promise<string> {
    return await this.testJsonTextarea.inputValue();
  }
}
