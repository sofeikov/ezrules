import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Role Management page.
 * Encapsulates all interactions with the role management UI.
 */
export class RoleManagementPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly roleNameInput: Locator;
  readonly roleDescriptionInput: Locator;
  readonly createRoleButton: Locator;
  readonly assignUserSelect: Locator;
  readonly assignRoleSelect: Locator;
  readonly assignRoleButton: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly rolesTable: Locator;
  readonly usersTable: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.roleNameInput = page.locator('input[placeholder="e.g. auditor"]');
    this.roleDescriptionInput = page.locator('input[placeholder="e.g. Can view audit trails"]');
    this.createRoleButton = page.locator('button:has-text("Create Role")');
    this.assignUserSelect = page.locator('select').nth(0);
    this.assignRoleSelect = page.locator('select').nth(1);
    this.assignRoleButton = page.locator('button:has-text("Assign Role")');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('.bg-red-50.border-red-200');
    this.rolesTable = page.locator('table').first();
    this.usersTable = page.locator('table').nth(1);
  }

  async goto() {
    await this.page.goto('/role_management');
  }

  async waitForPageToLoad() {
    await this.page.locator('text=/\\d+ roles? total/').waitFor({ state: 'visible' });
  }

  async getRoleRowCount(): Promise<number> {
    await this.waitForPageToLoad();
    return await this.rolesTable.locator('tbody tr').count();
  }

  async hasRoleWithName(name: string): Promise<boolean> {
    await this.waitForPageToLoad();
    return await this.rolesTable.locator(`tbody tr:has-text("${name}")`).isVisible();
  }

  async createRole(name: string, description?: string) {
    await this.roleNameInput.fill(name);
    if (description) {
      await this.roleDescriptionInput.fill(description);
    }
    await this.createRoleButton.click();
  }

  async clickDeleteRole(name: string) {
    const row = this.rolesTable.locator(`tbody tr:has-text("${name}")`);
    await row.locator('button:has-text("Delete")').click();
  }

  async assignRoleToUser(userEmail: string, roleName: string) {
    await this.assignUserSelect.selectOption({ label: userEmail });
    await this.assignRoleSelect.selectOption({ label: roleName });
    await this.assignRoleButton.click();
  }

  async hasUserWithRole(email: string): Promise<boolean> {
    if (await this.usersTable.count() === 0) return false;
    return await this.usersTable.locator(`tbody tr:has-text("${email}")`).isVisible();
  }

  async getUserRoleBadges(email: string): Promise<string[]> {
    const row = this.usersTable.locator(`tbody tr:has-text("${email}")`);
    const badges = row.locator('.bg-blue-100.text-blue-800');
    const count = await badges.count();
    const result: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await badges.nth(i).textContent();
      if (text) result.push(text.trim().replace(/\s*×\s*$/, ''));
    }
    return result;
  }

  async clickRemoveRoleFromUser(email: string, roleName: string) {
    const row = this.usersTable.locator(`tbody tr:has-text("${email}")`);
    const badge = row.locator(`.bg-blue-100:has-text("${roleName}")`);
    await badge.locator('button').click();
  }
}
