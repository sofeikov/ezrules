import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the accept invite page.
 */
export class AcceptInvitePage {
  readonly page: Page;
  readonly heading: Locator;
  readonly passwordInput: Locator;
  readonly confirmPasswordInput: Locator;
  readonly submitButton: Locator;
  readonly successMessage: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.passwordInput = page.locator('input#password');
    this.confirmPasswordInput = page.locator('input#confirmPassword');
    this.submitButton = page.locator('button[type="submit"]');
    this.successMessage = page.locator('.bg-green-50.border-green-200');
    this.errorMessage = page.locator('.bg-red-50.border-red-200');
  }

  async goto(token: string) {
    await this.page.goto(`/accept-invite?token=${encodeURIComponent(token)}`);
  }

  async gotoByUrl(url: string) {
    await this.page.goto(url);
  }

  async accept(password: string) {
    await this.passwordInput.fill(password);
    await this.confirmPasswordInput.fill(password);
    await this.submitButton.click();
  }
}
