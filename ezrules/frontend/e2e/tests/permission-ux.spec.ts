import { expect, Page, test } from '@playwright/test';
import { AccessDeniedPage } from '../pages/access-denied.page';
import { SettingsPage } from '../pages/settings.page';
import { UserManagementPage } from '../pages/user-management.page';

function mockAuthMe(page: Page, permissions: string[]) {
  return page.route('**/api/v2/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        email: 'viewer@example.com',
        active: true,
        roles: [{ id: 1, name: 'viewer', description: 'Viewer role' }],
        permissions,
        last_login_at: null,
      }),
    });
  });
}

test.describe('Permission-Aware UX', () => {
  test('hides restricted sidebar navigation for a low-privilege user', async ({ page }) => {
    await mockAuthMe(page, ['view_rules']);
    await page.route('**/api/v2/rules', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rules: [],
          evaluator_endpoint: 'http://localhost:9999',
        }),
      });
    });

    await page.goto('/rules');

    await expect(page.locator('a[href="/rules"]')).toBeVisible();
    await expect(page.locator('a[href="/management/users"]')).toHaveCount(0);
    await expect(page.locator('a[href="/audit"]')).toHaveCount(0);
    await expect(page.locator('a[href="/api-keys"]')).toHaveCount(0);
    await expect(page.locator('a[href="/role_management"]')).toHaveCount(0);
  });

  test('redirects direct access to a restricted route into the access-denied page', async ({ page }) => {
    const accessDeniedPage = new AccessDeniedPage(page);

    await mockAuthMe(page, ['view_rules']);

    await page.goto('/api-keys');

    await expect(page).toHaveURL(/\/access-denied/);
    await expect(accessDeniedPage.heading).toHaveText('Access denied');
    await expect(page.locator('text=Manage API keys')).toBeVisible();
    await expect(page.locator('text=/api-keys')).toBeVisible();
  });

  test('renders user management in read-only mode when write permissions are missing', async ({ page }) => {
    const userManagementPage = new UserManagementPage(page);

    await mockAuthMe(page, ['view_users']);
    await page.route('**/api/v2/users', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          users: [
            {
              id: 1,
              email: 'readonly@example.com',
              active: true,
              roles: [{ id: 1, name: 'viewer', description: 'Viewer role' }],
            },
          ],
        }),
      });
    });

    await userManagementPage.goto();
    await expect(userManagementPage.heading).toHaveText('User Management');
    await expect(page.locator('text=Read-only mode. User creation, account changes, and role assignment controls are hidden for your current permissions.')).toBeVisible();
    await expect(userManagementPage.createUserButton).toHaveCount(0);
    await expect(userManagementPage.sendInviteButton).toHaveCount(0);
    await expect(page.locator('button:has-text("Reset Password")')).toHaveCount(0);
    await expect(page.locator('button:has-text("Delete")')).toHaveCount(0);
    await expect(page.locator('text=+ Add role')).toHaveCount(0);
  });

  test('renders settings without strict mode controls for a read-only settings viewer', async ({ page }) => {
    const settingsPage = new SettingsPage(page);

    await mockAuthMe(page, ['view_roles']);
    await page.route('**/api/v2/settings/runtime', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          auto_promote_active_rule_updates: false,
          default_auto_promote_active_rule_updates: false,
          strict_mode_enabled: false,
          default_strict_mode_enabled: false,
          main_rule_execution_mode: 'all_matches',
          default_main_rule_execution_mode: 'all_matches',
          rule_quality_lookback_days: 30,
          default_rule_quality_lookback_days: 30,
          neutral_outcome: 'RELEASE',
          default_neutral_outcome: 'RELEASE',
          invalid_allowlist_rules: [],
        }),
      });
    });
    await page.route('**/api/v2/settings/outcome-hierarchy', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          outcomes: [
            { ao_id: 1, outcome_name: 'HOLD', severity_rank: 1 },
            { ao_id: 2, outcome_name: 'RELEASE', severity_rank: 2 },
          ],
        }),
      });
    });
    await page.route('**/api/v2/settings/rule-quality-pairs/options', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          outcomes: ['HOLD', 'RELEASE'],
          labels: ['fraud'],
        }),
      });
    });
    await page.route('**/api/v2/settings/rule-quality-pairs', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          pairs: [],
        }),
      });
    });

    await settingsPage.goto();
    await settingsPage.waitForPageToLoad();

    await expect(page.locator('#settings-strictModeCard')).toHaveCount(0);
    await expect(page.locator('#settings-strictModeEnabled')).toHaveCount(0);
    await expect(page.locator('#settings-saveStrictMode')).toHaveCount(0);
  });
});
