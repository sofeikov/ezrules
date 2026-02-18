import { test, expect } from '@playwright/test';
import { RoleManagementPage } from '../pages/role-management.page';

/**
 * E2E tests for the Role Management page.
 */
test.describe('Role Management Page', () => {
  let roleManagementPage: RoleManagementPage;

  test.beforeEach(async ({ page }) => {
    roleManagementPage = new RoleManagementPage(page);
  });

  test.describe('Page Structure', () => {
    test('should load the role management page successfully', async ({ page }) => {
      await roleManagementPage.goto();
      await expect(page).toHaveURL(/.*role_management/);
    });

    test('should display the correct heading', async () => {
      await roleManagementPage.goto();
      await expect(roleManagementPage.heading).toHaveText('Role Management');
    });

    test('should display the page description', async ({ page }) => {
      await roleManagementPage.goto();
      const description = page.locator('text=Manage roles, assign them to users, and configure permissions');
      await expect(description).toBeVisible();
    });

    test('should be reachable from sidebar navigation', async ({ page }) => {
      await page.goto('/rules');
      const settingsLink = page.locator('a:has-text("Role Management")');
      await expect(settingsLink).toBeVisible();
      await settingsLink.click();
      await expect(page).toHaveURL(/.*role_management/);
      await expect(roleManagementPage.heading).toHaveText('Role Management');
    });
  });

  test.describe('Roles Table', () => {
    test('should display the roles count summary', async () => {
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      const countText = roleManagementPage.page.locator('text=/\\d+ roles? total/');
      await expect(countText).toBeVisible();
    });

    test('should display at least one role in the table', async () => {
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      const rowCount = await roleManagementPage.getRoleRowCount();
      expect(rowCount).toBeGreaterThanOrEqual(1);
    });

    test('should display the roles table with correct columns', async ({ page }) => {
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      const rolesTable = page.locator('table').first();
      await expect(rolesTable.locator('th:has-text("ID")')).toBeVisible();
      await expect(rolesTable.locator('th:has-text("Name")')).toBeVisible();
      await expect(rolesTable.locator('th:has-text("Description")')).toBeVisible();
      await expect(rolesTable.locator('th:has-text("Users")')).toBeVisible();
      await expect(rolesTable.locator('th:has-text("Actions")')).toBeVisible();
    });
  });

  test.describe('Create Role', () => {
    test('should have the create role form visible', async () => {
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      await expect(roleManagementPage.roleNameInput).toBeVisible();
      await expect(roleManagementPage.roleDescriptionInput).toBeVisible();
      await expect(roleManagementPage.createRoleButton).toBeVisible();
    });

    test('should create a new role and display it in the table', async ({ page }) => {
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      const uniqueName = `e2e_role_${Date.now()}`;

      await roleManagementPage.createRole(uniqueName, 'Test role description');

      // Wait for the role to appear in the table
      const rolesTable = page.locator('table').first();
      await page.waitForFunction(
        (name: string) => {
          const tables = document.querySelectorAll('table');
          if (tables.length === 0) return false;
          const rows = tables[0].querySelectorAll('tbody tr');
          return Array.from(rows).some(row => row.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );

      expect(await roleManagementPage.hasRoleWithName(uniqueName)).toBe(true);

      // Cleanup: delete the created role
      page.on('dialog', dialog => dialog.accept());
      await roleManagementPage.clickDeleteRole(uniqueName);
      await page.waitForFunction(
        (name: string) => {
          const tables = document.querySelectorAll('table');
          if (tables.length === 0) return true;
          const rows = tables[0].querySelectorAll('tbody tr');
          return !Array.from(rows).some(row => row.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );
    });

    test('should show error for duplicate role name', async ({ page }) => {
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      const uniqueName = `e2e_duprole_${Date.now()}`;

      // Create role first time
      await roleManagementPage.createRole(uniqueName);

      await page.waitForFunction(
        (name: string) => {
          const tables = document.querySelectorAll('table');
          if (tables.length === 0) return false;
          const rows = tables[0].querySelectorAll('tbody tr');
          return Array.from(rows).some(row => row.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );

      // Try to create the same role again
      await roleManagementPage.createRole(uniqueName);

      // Should show an error about already exists
      const errorText = page.locator('text=/already exists/i');
      await expect(errorText).toBeVisible();

      // Cleanup
      page.on('dialog', dialog => dialog.accept());
      await roleManagementPage.clickDeleteRole(uniqueName);
      await page.waitForFunction(
        (name: string) => {
          const tables = document.querySelectorAll('table');
          if (tables.length === 0) return true;
          const rows = tables[0].querySelectorAll('tbody tr');
          return !Array.from(rows).some(row => row.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );
    });
  });

  test.describe('Delete Role', () => {
    test('should delete a role after confirmation', async ({ page }) => {
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      // Create a role to delete
      const uniqueName = `e2e_delrole_${Date.now()}`;
      await roleManagementPage.createRole(uniqueName);

      await page.waitForFunction(
        (name: string) => {
          const tables = document.querySelectorAll('table');
          if (tables.length === 0) return false;
          const rows = tables[0].querySelectorAll('tbody tr');
          return Array.from(rows).some(row => row.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );

      // Accept the confirmation dialog
      page.on('dialog', dialog => dialog.accept());

      const countBefore = await roleManagementPage.getRoleRowCount();
      await roleManagementPage.clickDeleteRole(uniqueName);

      // Wait for the role to disappear
      await page.waitForFunction(
        (name: string) => {
          const tables = document.querySelectorAll('table');
          if (tables.length === 0) return true;
          const rows = tables[0].querySelectorAll('tbody tr');
          return !Array.from(rows).some(row => row.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );

      const countAfter = await roleManagementPage.getRoleRowCount();
      expect(countAfter).toBe(countBefore - 1);
    });

    test('should not delete a role when confirmation is dismissed', async ({ page }) => {
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      // Create a role
      const uniqueName = `e2e_nodelrole_${Date.now()}`;
      await roleManagementPage.createRole(uniqueName);

      await page.waitForFunction(
        (name: string) => {
          const tables = document.querySelectorAll('table');
          if (tables.length === 0) return false;
          const rows = tables[0].querySelectorAll('tbody tr');
          return Array.from(rows).some(row => row.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );

      const countBefore = await roleManagementPage.getRoleRowCount();

      // Dismiss the confirmation dialog
      page.on('dialog', dialog => dialog.dismiss());

      await roleManagementPage.clickDeleteRole(uniqueName);

      // Wait briefly and check count is unchanged
      await page.waitForTimeout(500);
      const countAfter = await roleManagementPage.getRoleRowCount();
      expect(countAfter).toBe(countBefore);

      // Cleanup
      page.removeAllListeners('dialog');
      page.on('dialog', dialog => dialog.accept());
      await roleManagementPage.clickDeleteRole(uniqueName);
      await page.waitForFunction(
        (name: string) => {
          const tables = document.querySelectorAll('table');
          if (tables.length === 0) return true;
          const rows = tables[0].querySelectorAll('tbody tr');
          return !Array.from(rows).some(row => row.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );
    });
  });

  test.describe('Assign Role Form', () => {
    test('should have the assign role form visible', async () => {
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      await expect(roleManagementPage.assignUserSelect).toBeVisible();
      await expect(roleManagementPage.assignRoleSelect).toBeVisible();
      await expect(roleManagementPage.assignRoleButton).toBeVisible();
    });

    test('should have Manage Permissions link for each role', async ({ page }) => {
      await roleManagementPage.goto();
      await roleManagementPage.waitForPageToLoad();

      const permissionsLinks = page.locator('table').first().locator('a:has-text("Manage Permissions")');
      const count = await permissionsLinks.count();
      expect(count).toBeGreaterThanOrEqual(1);
    });
  });
});
