import { test as setup } from '@playwright/test';

/**
 * Global setup that logs in once and saves the auth state (localStorage tokens)
 * to a file. All test projects depend on this setup so they start authenticated.
 */
setup('authenticate', async ({ page }) => {
  // Navigate to login page
  await page.goto('/login');

  // Fill in credentials (uses the default test user created by test_cli.sh)
  await page.fill('input#email', 'admin@test_org.com');
  await page.fill('input#password', '12345678');
  await page.click('button[type="submit"]');

  // Wait for redirect to dashboard after login
  await page.waitForURL(/.*dashboard/, { timeout: 10000 });

  // Save the authenticated state (localStorage with tokens)
  await page.context().storageState({ path: 'e2e/.auth/user.json' });
});
