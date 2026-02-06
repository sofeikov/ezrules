import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the User Management page.
 * Encapsulates all interactions with the user management UI.
 */
export class UserManagementPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly roleSelect: Locator;
  readonly createUserButton: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly userCountText: Locator;
  readonly usersTable: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.emailInput = page.locator('input[type="email"]');
    this.passwordInput = page.locator('input[type="password"]');
    this.roleSelect = page.locator('select').first();
    this.createUserButton = page.locator('button:has-text("Create User")');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('.bg-red-50.border-red-200');
    this.userCountText = page.locator('text=/\\d+ users? total/');
    this.usersTable = page.locator('table');
  }

  async goto() {
    await this.page.goto('/management/users');
  }

  async waitForUsersToLoad() {
    await this.userCountText.waitFor({ state: 'visible' });
  }

  async getUserRowCount(): Promise<number> {
    await this.waitForUsersToLoad();
    return await this.page.locator('table tbody tr').count();
  }

  async hasUserWithEmail(email: string): Promise<boolean> {
    await this.waitForUsersToLoad();
    return await this.page.locator(`table tbody tr:has-text("${email}")`).isVisible();
  }

  async createUser(email: string, password: string) {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.createUserButton.click();
  }

  async clickDeleteUser(email: string) {
    const row = this.page.locator(`table tbody tr:has-text("${email}")`);
    await row.locator('button:has-text("Delete")').click();
  }

  async getUserRoleBadges(email: string): Promise<string[]> {
    const row = this.page.locator(`table tbody tr:has-text("${email}")`);
    const badges = row.locator('.bg-blue-100.text-blue-800');
    const count = await badges.count();
    const result: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await badges.nth(i).textContent();
      if (text) result.push(text.trim().replace(/\s*×\s*$/, ''));
    }
    return result;
  }

  async getUserStatus(email: string): Promise<string> {
    const row = this.page.locator(`table tbody tr:has-text("${email}")`);
    const badge = row.locator('.rounded-full');
    return (await badge.textContent())?.trim() ?? '';
  }
}
