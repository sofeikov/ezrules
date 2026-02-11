import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/login.page';

/**
 * E2E tests for the Login page.
 * These tests run WITHOUT the shared auth state (no storageState).
 */
test.describe('Login Page', () => {
  // Override storageState to run unauthenticated
  test.use({ storageState: { cookies: [], origins: [] } });

  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
  });

  test.describe('Page Structure', () => {
    test('should display the login page', async () => {
      await loginPage.goto();
      await expect(loginPage.heading).toHaveText('ezrules');
    });

    test('should display email and password inputs', async () => {
      await loginPage.goto();
      await expect(loginPage.emailInput).toBeVisible();
      await expect(loginPage.passwordInput).toBeVisible();
    });

    test('should display sign in button', async () => {
      await loginPage.goto();
      await expect(loginPage.submitButton).toBeVisible();
      await expect(loginPage.submitButton).toHaveText('Sign In');
    });
  });

  test.describe('Authentication', () => {
    test('should redirect unauthenticated users to login', async ({ page }) => {
      await page.goto('/dashboard');
      await expect(page).toHaveURL(/.*login/);
    });

    test('should show error on invalid credentials', async () => {
      await loginPage.goto();
      await loginPage.login('wrong@example.com', 'wrongpassword');
      await expect(loginPage.errorMessage).toBeVisible();
      await expect(loginPage.errorMessage).toContainText('Invalid email or password');
    });

    test('should redirect to dashboard on successful login', async ({ page }) => {
      await loginPage.goto();
      await loginPage.login('admin@test_org.com', '12345678');
      await page.waitForURL(/.*dashboard/, { timeout: 10000 });
      await expect(page).toHaveURL(/.*dashboard/);
    });
  });

  test.describe('Sign Out', () => {
    test('should sign out and redirect to login', async ({ page }) => {
      // Login first
      await loginPage.goto();
      await loginPage.login('admin@test_org.com', '12345678');
      await page.waitForURL(/.*dashboard/, { timeout: 10000 });

      // Click Sign Out in sidebar
      const signOutButton = page.locator('button:has-text("Sign Out")');
      await expect(signOutButton).toBeVisible();
      await signOutButton.click();

      await expect(page).toHaveURL(/.*login/);
    });
  });
});
