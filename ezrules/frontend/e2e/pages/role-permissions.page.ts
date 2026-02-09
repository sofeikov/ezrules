import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Role Permissions page.
 * Encapsulates all interactions with the role permissions UI.
 */
export class RolePermissionsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly backLink: Locator;
  readonly saveButton: Locator;
  readonly cancelLink: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly successMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.backLink = page.locator('a:has-text("Back to Role Management")');
    this.saveButton = page.locator('button:has-text("Save Permissions")');
    this.cancelLink = page.locator('a:has-text("Cancel")');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('.bg-red-50.border-red-200');
    this.successMessage = page.locator('text=Changes saved.');
  }

  async goto(roleId: number) {
    await this.page.goto(`/role_management/${roleId}/permissions`);
  }

  async waitForPageToLoad() {
    await this.saveButton.waitFor({ state: 'visible' });
  }

  async getPermissionGroupCount(): Promise<number> {
    return await this.page.locator('.border-l-blue-500').count();
  }

  async getCheckboxCount(): Promise<number> {
    return await this.page.locator('input[type="checkbox"]').count();
  }

  async getCheckedCount(): Promise<number> {
    return await this.page.locator('input[type="checkbox"]:checked').count();
  }

  async getSummaryBadgeCount(): Promise<number> {
    return await this.page.locator('.bg-green-100.text-green-800').count();
  }

  async toggleCheckbox(index: number) {
    const checkbox = this.page.locator('input[type="checkbox"]').nth(index);
    await checkbox.click();
  }

  async save() {
    await this.saveButton.click();
  }
}
