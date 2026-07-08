import { test, expect } from '../support/fixtures';
import { UserManagementPage } from '../pages/user-management.page';
import { testResourceName } from '../support/test-data';
import { STATEFUL_TAG, TEST_DATA_TAG } from '../support/tags';

/**
 * E2E tests for the User Management page.
 */
test.describe(`User Management Page ${STATEFUL_TAG} ${TEST_DATA_TAG}`, () => {
  let userMgmtPage: UserManagementPage;

  test.beforeEach(async ({ page }) => {
    userMgmtPage = new UserManagementPage(page);
  });

  test.describe('Page Structure', () => {
    test('should load the user management page successfully', async ({ page }) => {
      await userMgmtPage.goto();
      await expect(page).toHaveURL(/.*management\/users/);
    });

    test('should display the correct heading', async () => {
      await userMgmtPage.goto();
      await expect(userMgmtPage.heading).toHaveText('User Management');
    });

    test('should display the page description', async ({ page }) => {
      await userMgmtPage.goto();
      const description = page.locator('text=Manage user accounts, roles, and access');
      await expect(description).toBeVisible();
    });

    test('should be reachable from sidebar navigation', async ({ page }) => {
      await page.goto('/rules');
      const securityLink = page.locator('a:has-text("Security")');
      await expect(securityLink).toBeVisible();
      await securityLink.click();
      await expect(page).toHaveURL(/.*management\/users/);
      await expect(userMgmtPage.heading).toHaveText('User Management');
    });
  });

  test.describe('Users Table', () => {
    test('should display the user count summary', async () => {
      await userMgmtPage.goto();
      await userMgmtPage.waitForUsersToLoad();

      await expect(userMgmtPage.userCountText).toBeVisible();
    });

    test('should display at least one user in the table', async () => {
      await userMgmtPage.goto();
      await userMgmtPage.waitForUsersToLoad();

      const rowCount = await userMgmtPage.getUserRowCount();
      expect(rowCount).toBeGreaterThanOrEqual(1);
    });

    test('should display the users table with correct columns', async ({ page }) => {
      await userMgmtPage.goto();
      await userMgmtPage.waitForUsersToLoad();

      await expect(page.locator('th:has-text("ID")')).toBeVisible();
      await expect(page.locator('th:has-text("Email")')).toBeVisible();
      await expect(page.locator('th:has-text("Status")')).toBeVisible();
      await expect(page.locator('th:has-text("Roles")')).toBeVisible();
      await expect(page.locator('th:has-text("Actions")')).toBeVisible();
    });
  });

  test.describe('Create User', () => {
    test('should have the create user form visible', async () => {
      await userMgmtPage.goto();
      await userMgmtPage.waitForUsersToLoad();

      await expect(userMgmtPage.emailInput).toBeVisible();
      await expect(userMgmtPage.passwordInput).toBeVisible();
      await expect(userMgmtPage.createUserButton).toBeVisible();
    });

    test('should create a new user and display it in the table', async ({ page }, testInfo) => {
      await userMgmtPage.goto();
      await userMgmtPage.waitForUsersToLoad();

      const uniqueEmail = `${testResourceName(testInfo, 'e2e_test', { maxLength: 48 }).toLowerCase()}@example.com`;

      await userMgmtPage.createUser(uniqueEmail, 'testpass123');

      // Wait for the user to appear in the table
      await page.waitForFunction(
        (email: string) => {
          const rows = document.querySelectorAll('table tbody tr');
          return Array.from(rows).some(row => row.textContent?.includes(email));
        },
        uniqueEmail,
        { timeout: 5000 }
      );

      expect(await userMgmtPage.hasUserWithEmail(uniqueEmail)).toBe(true);

      // Cleanup: delete the created user
      page.on('dialog', dialog => dialog.accept());
      await userMgmtPage.clickDeleteUser(uniqueEmail);
      await page.waitForFunction(
        (email: string) => {
          const rows = document.querySelectorAll('table tbody tr');
          return !Array.from(rows).some(row => row.textContent?.includes(email));
        },
        uniqueEmail,
        { timeout: 5000 }
      );
    });

    test('should show error for duplicate email', async ({ page }, testInfo) => {
      await userMgmtPage.goto();
      await userMgmtPage.waitForUsersToLoad();

      const uniqueEmail = `${testResourceName(testInfo, 'e2e_dup', { maxLength: 48 }).toLowerCase()}@example.com`;

      // Create user first time
      await userMgmtPage.createUser(uniqueEmail, 'testpass123');

      await page.waitForFunction(
        (email: string) => {
          const rows = document.querySelectorAll('table tbody tr');
          return Array.from(rows).some(row => row.textContent?.includes(email));
        },
        uniqueEmail,
        { timeout: 5000 }
      );

      // Try to create the same user again
      await userMgmtPage.createUser(uniqueEmail, 'testpass123');

      // Should show an error about already exists
      const errorText = page.locator('text=/already exists/i');
      await expect(errorText).toBeVisible();

      // Cleanup
      page.on('dialog', dialog => dialog.accept());
      await userMgmtPage.clickDeleteUser(uniqueEmail);
      await page.waitForFunction(
        (email: string) => {
          const rows = document.querySelectorAll('table tbody tr');
          return !Array.from(rows).some(row => row.textContent?.includes(email));
        },
        uniqueEmail,
        { timeout: 5000 }
      );
    });
  });

  test.describe('Delete User', () => {
    test('should delete a user after confirmation', async ({ page }, testInfo) => {
      await userMgmtPage.goto();
      await userMgmtPage.waitForUsersToLoad();

      // Create a user to delete
      const uniqueEmail = `${testResourceName(testInfo, 'e2e_del', { maxLength: 48 }).toLowerCase()}@example.com`;
      await userMgmtPage.createUser(uniqueEmail, 'testpass123');

      await page.waitForFunction(
        (email: string) => {
          const rows = document.querySelectorAll('table tbody tr');
          return Array.from(rows).some(row => row.textContent?.includes(email));
        },
        uniqueEmail,
        { timeout: 5000 }
      );

      // Accept the confirmation dialog
      page.on('dialog', dialog => dialog.accept());

      const countBefore = await userMgmtPage.getUserRowCount();
      await userMgmtPage.clickDeleteUser(uniqueEmail);

      // Wait for the user to disappear
      await page.waitForFunction(
        (email: string) => {
          const rows = document.querySelectorAll('table tbody tr');
          return !Array.from(rows).some(row => row.textContent?.includes(email));
        },
        uniqueEmail,
        { timeout: 5000 }
      );

      const countAfter = await userMgmtPage.getUserRowCount();
      expect(countAfter).toBe(countBefore - 1);
    });

    test('should not delete a user when confirmation is dismissed', async ({ page }, testInfo) => {
      await userMgmtPage.goto();
      await userMgmtPage.waitForUsersToLoad();

      // Create a user to test with
      const uniqueEmail = `${testResourceName(testInfo, 'e2e_nodel', { maxLength: 48 }).toLowerCase()}@example.com`;
      await userMgmtPage.createUser(uniqueEmail, 'testpass123');

      await page.waitForFunction(
        (email: string) => {
          const rows = document.querySelectorAll('table tbody tr');
          return Array.from(rows).some(row => row.textContent?.includes(email));
        },
        uniqueEmail,
        { timeout: 5000 }
      );

      const countBefore = await userMgmtPage.getUserRowCount();

      const dismissDialogPromise = page.waitForEvent('dialog');
      await userMgmtPage.clickDeleteUser(uniqueEmail);
      const dismissDialog = await dismissDialogPromise;
      await dismissDialog.dismiss();

      await expect(page.locator('table tbody tr')).toHaveCount(countBefore);
      expect(await userMgmtPage.hasUserWithEmail(uniqueEmail)).toBe(true);

      // Cleanup
      const acceptDialogPromise = page.waitForEvent('dialog');
      await userMgmtPage.clickDeleteUser(uniqueEmail);
      const acceptDialog = await acceptDialogPromise;
      await acceptDialog.accept();
      await page.waitForFunction(
        (email: string) => {
          const rows = document.querySelectorAll('table tbody tr');
          return !Array.from(rows).some(row => row.textContent?.includes(email));
        },
        uniqueEmail,
        { timeout: 5000 }
      );
    });
  });
});
