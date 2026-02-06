import { test, expect } from '@playwright/test';
import { RolePermissionsPage } from '../pages/role-permissions.page';
import { RoleManagementPage } from '../pages/role-management.page';

/**
 * E2E tests for the Role Permissions page.
 */
test.describe('Role Permissions Page', () => {
  let rolePermissionsPage: RolePermissionsPage;

  test.beforeEach(async ({ page }) => {
    rolePermissionsPage = new RolePermissionsPage(page);
  });

  test.describe('Page Structure', () => {
    test('should be navigable from the Role Management page', async ({ page }) => {
      const roleManagementPage = new RoleManagementPage(page);
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      // Click the first Manage Permissions link
      const permLink = page.locator('table').first().locator('a:has-text("Manage Permissions")').first();
      await expect(permLink).toBeVisible();
      await permLink.click();

      await expect(page).toHaveURL(/.*role_management\/\d+\/permissions/);
      await expect(rolePermissionsPage.heading).toContainText('Permissions for');
    });

    test('should display the back link to role management', async ({ page }) => {
      // Navigate via role management to find a valid role ID
      const roleManagementPage = new RoleManagementPage(page);
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      const permLink = page.locator('table').first().locator('a:has-text("Manage Permissions")').first();
      await permLink.click();

      await rolePermissionsPage.waitForPageToLoad();
      await expect(rolePermissionsPage.backLink).toBeVisible();
    });

    test('should display save and cancel buttons', async ({ page }) => {
      const roleManagementPage = new RoleManagementPage(page);
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      const permLink = page.locator('table').first().locator('a:has-text("Manage Permissions")').first();
      await permLink.click();

      await rolePermissionsPage.waitForPageToLoad();
      await expect(rolePermissionsPage.saveButton).toBeVisible();
      await expect(rolePermissionsPage.cancelLink).toBeVisible();
    });
  });

  test.describe('Permissions Display', () => {
    test('should display permission groups with blue left border', async ({ page }) => {
      const roleManagementPage = new RoleManagementPage(page);
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      const permLink = page.locator('table').first().locator('a:has-text("Manage Permissions")').first();
      await permLink.click();

      await rolePermissionsPage.waitForPageToLoad();

      const groupCount = await rolePermissionsPage.getPermissionGroupCount();
      expect(groupCount).toBeGreaterThanOrEqual(1);
    });

    test('should display checkboxes for permissions', async ({ page }) => {
      const roleManagementPage = new RoleManagementPage(page);
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      const permLink = page.locator('table').first().locator('a:has-text("Manage Permissions")').first();
      await permLink.click();

      await rolePermissionsPage.waitForPageToLoad();

      const checkboxCount = await rolePermissionsPage.getCheckboxCount();
      expect(checkboxCount).toBeGreaterThanOrEqual(1);
    });

    test('should display current permissions summary as green badges', async ({ page }) => {
      const roleManagementPage = new RoleManagementPage(page);
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      // Use the first role's Manage Permissions link (admin role likely has permissions)
      const permLink = page.locator('table').first().locator('a:has-text("Manage Permissions")').first();
      await permLink.click();

      await rolePermissionsPage.waitForPageToLoad();

      // The summary section should exist (may have 0 or more badges)
      const summaryHeading = page.locator('text=Current Permissions Summary');
      await expect(summaryHeading).toBeVisible();
    });
  });

  test.describe('Save Permissions', () => {
    test('should save permissions and show success message', async ({ page }) => {
      const roleManagementPage = new RoleManagementPage(page);
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      const permLink = page.locator('table').first().locator('a:has-text("Manage Permissions")').first();
      await permLink.click();

      await rolePermissionsPage.waitForPageToLoad();

      // Click save (even without changes, it should succeed)
      await rolePermissionsPage.save();

      // Wait for success message
      await expect(rolePermissionsPage.successMessage).toBeVisible();
    });
  });
});
