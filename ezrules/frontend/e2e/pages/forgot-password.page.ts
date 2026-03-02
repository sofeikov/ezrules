import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the forgot password page.
 */
export class ForgotPasswordPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly emailInput: Locator;
  readonly submitButton: Locator;
  readonly successMessage: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.emailInput = page.locator('input#email');
    this.submitButton = page.locator('button[type="submit"]');
    this.successMessage = page.locator('.bg-green-50.border-green-200');
    this.errorMessage = page.locator('.bg-red-50.border-red-200');
  }

  async goto() {
    await this.page.goto('/forgot-password');
  }

  async requestReset(email: string) {
    await this.emailInput.fill(email);
    await this.submitButton.click();
  }
}
