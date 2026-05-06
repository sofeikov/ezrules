import { expect, Page, test } from '@playwright/test';
import { AccessDeniedPage } from '../pages/access-denied.page';
import { SettingsPage } from '../pages/settings.page';
import { UserManagementPage } from '../pages/user-management.page';

interface PermissionGrant {
  name: string;
  resource_id?: number | null;
}

function mockAuthMe(page: Page, permissions: string[], permissionGrants?: PermissionGrant[]) {
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
        permission_grants: permissionGrants ?? permissions.map(name => ({ name, resource_id: null })),
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

  test('does not treat scoped-only grants as global route access', async ({ page }) => {
    const accessDeniedPage = new AccessDeniedPage(page);

    await mockAuthMe(page, [], [{ name: 'view_rules', resource_id: 42 }]);

    await page.goto('/rules');

    await expect(page).toHaveURL(/\/access-denied/);
    await expect(accessDeniedPage.heading).toHaveText('Access denied');
    await expect(page.locator('text=View rules')).toBeVisible();
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

  test('hides user role selectors when create-user access lacks role-management access', async ({ page }) => {
    const userManagementPage = new UserManagementPage(page);

    await mockAuthMe(page, ['view_users', 'create_user', 'view_roles']);
    await page.route('**/api/v2/users', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          users: [
            {
              id: 1,
              email: 'creator@example.com',
              active: true,
              roles: [{ id: 1, name: 'creator', description: 'Creator role' }],
            },
            {
              id: 2,
              email: 'target@example.com',
              active: true,
              roles: [],
            },
          ],
        }),
      });
    });
    await page.route('**/api/v2/roles', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          roles: [
            {
              id: 1,
              name: 'creator',
              description: 'Creator role',
              user_count: 1,
              permissions: [{ id: 1, name: 'create_user', description: null, resource_type: 'user' }],
            },
            {
              id: 2,
              name: 'admin',
              description: 'Admin role',
              user_count: 0,
              permissions: [{ id: 2, name: 'manage_permissions', description: null, resource_type: 'permission' }],
            },
          ],
        }),
      });
    });

    await userManagementPage.goto();

    await expect(userManagementPage.createUserButton).toBeVisible();
    await expect(userManagementPage.roleSelect).toHaveCount(0);
    await expect(userManagementPage.inviteRoleSelect).toHaveCount(0);
    await expect(page.locator('text=+ Add role')).toHaveCount(0);
  });

  test('hides role removal for roles above the current user privilege ceiling', async ({ page }) => {
    const userManagementPage = new UserManagementPage(page);

    await mockAuthMe(page, ['view_users', 'view_roles', 'view_rules', 'manage_user_roles']);
    await page.route('**/api/v2/users', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          users: [
            {
              id: 1,
              email: 'manager@example.com',
              active: true,
              roles: [{ id: 1, name: 'manager', description: 'Manager role' }],
            },
            {
              id: 2,
              email: 'target@example.com',
              active: true,
              roles: [
                { id: 2, name: 'viewer', description: 'Viewer role' },
                { id: 3, name: 'admin', description: 'Admin role' },
              ],
            },
          ],
        }),
      });
    });
    await page.route('**/api/v2/roles', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          roles: [
            {
              id: 2,
              name: 'viewer',
              description: 'Viewer role',
              user_count: 1,
              permissions: [{ id: 1, name: 'view_rules', description: null, resource_type: 'rule' }],
            },
            {
              id: 3,
              name: 'admin',
              description: 'Admin role',
              user_count: 1,
              permissions: [{ id: 2, name: 'manage_permissions', description: null, resource_type: 'permission' }],
            },
          ],
        }),
      });
    });

    await userManagementPage.goto();

    const targetRow = page.locator('table tbody tr').filter({ hasText: 'target@example.com' });
    const viewerRole = targetRow.locator('.bg-blue-100.text-blue-800').filter({ hasText: 'viewer' });
    const adminRole = targetRow.locator('.bg-blue-100.text-blue-800').filter({ hasText: 'admin' });

    await expect(viewerRole.locator('button[title="Remove role"]')).toHaveCount(1);
    await expect(adminRole.locator('button[title="Remove role"]')).toHaveCount(0);
  });

  test('keeps scoped roles outside the current user resource ceiling hidden', async ({ page }) => {
    const userManagementPage = new UserManagementPage(page);

    await mockAuthMe(
      page,
      ['view_users', 'view_roles', 'view_rules', 'manage_user_roles'],
      [
        { name: 'view_users', resource_id: null },
        { name: 'view_roles', resource_id: null },
        { name: 'manage_user_roles', resource_id: null },
        { name: 'view_rules', resource_id: 7 },
      ]
    );
    await page.route('**/api/v2/users', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          users: [
            {
              id: 1,
              email: 'manager@example.com',
              active: true,
              roles: [{ id: 1, name: 'manager', description: 'Manager role' }],
            },
            {
              id: 2,
              email: 'target@example.com',
              active: true,
              roles: [
                { id: 2, name: 'same-scope', description: 'Same scope role' },
                { id: 3, name: 'different-scope', description: 'Different scope role' },
                { id: 4, name: 'global-viewer', description: 'Global viewer role' },
              ],
            },
            {
              id: 3,
              email: 'empty@example.com',
              active: true,
              roles: [],
            },
          ],
        }),
      });
    });
    await page.route('**/api/v2/roles', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          roles: [
            {
              id: 2,
              name: 'same-scope',
              description: 'Same scope role',
              user_count: 1,
              permissions: [{ id: 1, name: 'view_rules', description: null, resource_type: 'rule', resource_id: 7 }],
            },
            {
              id: 3,
              name: 'different-scope',
              description: 'Different scope role',
              user_count: 1,
              permissions: [{ id: 1, name: 'view_rules', description: null, resource_type: 'rule', resource_id: 8 }],
            },
            {
              id: 4,
              name: 'global-viewer',
              description: 'Global viewer role',
              user_count: 1,
              permissions: [{ id: 1, name: 'view_rules', description: null, resource_type: 'rule', resource_id: null }],
            },
          ],
        }),
      });
    });

    await userManagementPage.goto();

    const targetRow = page.locator('table tbody tr').filter({ hasText: 'target@example.com' });
    const sameScopeRole = targetRow.locator('.bg-blue-100.text-blue-800').filter({ hasText: 'same-scope' });
    const differentScopeRole = targetRow.locator('.bg-blue-100.text-blue-800').filter({ hasText: 'different-scope' });
    const globalViewerRole = targetRow.locator('.bg-blue-100.text-blue-800').filter({ hasText: 'global-viewer' });
    await expect(sameScopeRole.locator('button[title="Remove role"]')).toHaveCount(1);
    await expect(differentScopeRole.locator('button[title="Remove role"]')).toHaveCount(0);
    await expect(globalViewerRole.locator('button[title="Remove role"]')).toHaveCount(0);

    const emptyRow = page.locator('table tbody tr').filter({ hasText: 'empty@example.com' });
    const addRoleSelect = emptyRow.locator('select');
    await expect(addRoleSelect).toBeVisible();
    await expect(addRoleSelect.locator('option', { hasText: '+ Add role' })).toHaveCount(1);
    await expect(addRoleSelect.locator('option', { hasText: 'same-scope' })).toHaveCount(1);
    await expect(addRoleSelect.locator('option', { hasText: 'different-scope' })).toHaveCount(0);
    await expect(addRoleSelect.locator('option', { hasText: 'global-viewer' })).toHaveCount(0);
  });

  test('filters role management assignment choices by scoped grants', async ({ page }) => {
    await mockAuthMe(
      page,
      ['view_users', 'view_roles', 'view_rules', 'manage_user_roles'],
      [
        { name: 'view_users', resource_id: null },
        { name: 'view_roles', resource_id: null },
        { name: 'manage_user_roles', resource_id: null },
        { name: 'view_rules', resource_id: 7 },
      ]
    );
    await page.route('**/api/v2/users', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          users: [
            {
              id: 1,
              email: 'manager@example.com',
              active: true,
              roles: [{ id: 1, name: 'manager', description: 'Manager role' }],
            },
            {
              id: 2,
              email: 'target@example.com',
              active: true,
              roles: [],
            },
          ],
        }),
      });
    });
    await page.route('**/api/v2/roles', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          roles: [
            {
              id: 2,
              name: 'same-scope',
              description: 'Same scope role',
              user_count: 0,
              permissions: [{ id: 1, name: 'view_rules', description: null, resource_type: 'rule', resource_id: 7 }],
            },
            {
              id: 3,
              name: 'different-scope',
              description: 'Different scope role',
              user_count: 0,
              permissions: [{ id: 1, name: 'view_rules', description: null, resource_type: 'rule', resource_id: 8 }],
            },
            {
              id: 4,
              name: 'global-viewer',
              description: 'Global viewer role',
              user_count: 0,
              permissions: [{ id: 1, name: 'view_rules', description: null, resource_type: 'rule', resource_id: null }],
            },
          ],
        }),
      });
    });

    await page.goto('/role_management');

    const assignForm = page.getByRole('heading', { name: 'Assign Role to User' }).locator('..');
    const roleSelect = assignForm.locator('select').nth(1);
    await expect(roleSelect.locator('option', { hasText: 'Select a role...' })).toHaveCount(1);
    await expect(roleSelect.locator('option', { hasText: 'same-scope' })).toHaveCount(1);
    await expect(roleSelect.locator('option', { hasText: 'different-scope' })).toHaveCount(0);
    await expect(roleSelect.locator('option', { hasText: 'global-viewer' })).toHaveCount(0);
  });

  test('shows saved-version deployment actions without rule edit permission', async ({ page }) => {
    let shadowDeployBody: Record<string, unknown> | null = null;
    let rolloutDeployBody: Record<string, unknown> | null = null;

    await mockAuthMe(page, ['view_rules', 'manage_shadow_deployments', 'manage_rollouts']);
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
    await page.route('**/api/v2/notifications/unread-count', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ unread_count: 0 }),
      });
    });
    await page.route('**/api/v2/rules/42', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          r_id: 42,
          rid: 'saved_deploy_rule',
          description: 'Saved deployment rule',
          logic: 'return !HOLD',
          execution_order: 1,
          evaluation_lane: 'main',
          status: 'active',
          effective_from: null,
          approved_by: null,
          approved_at: null,
          created_at: null,
          in_shadow: false,
          in_rollout: false,
          rollout_percent: null,
          revisions: [],
        }),
      });
    });
    await page.route('**/api/v2/shadow', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ rules: [], version: 1 }),
      });
    });
    await page.route('**/api/v2/rollouts', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ rules: [], version: 1 }),
      });
    });
    await page.route('**/api/v2/backtesting/42**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ results: [] }),
      });
    });
    await page.route('**/api/v2/analytics/rules/42/outcomes-distribution**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ labels: [], datasets: [], aggregation: '1h' }),
      });
    });
    await page.route('**/api/v2/rules/42/shadow', async (route) => {
      shadowDeployBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, message: 'Rule deployed to shadow' }),
      });
    });
    await page.route('**/api/v2/rules/42/rollout', async (route) => {
      rolloutDeployBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, message: 'Rule rollout started' }),
      });
    });

    await page.goto('/rules/42');

    await expect(page.getByRole('button', { name: 'Edit Rule' })).toHaveCount(0);
    await expect(page.getByTestId('deploy-saved-to-shadow-button')).toBeVisible();
    await expect(page.getByTestId('deploy-saved-to-rollout-button')).toBeVisible();

    await page.getByTestId('deploy-saved-to-shadow-button').click();
    await page.getByTestId('confirm-deploy-shadow-button').click();
    await expect.poll(() => shadowDeployBody).not.toBeNull();
    expect(shadowDeployBody).toEqual({});

    await page.getByTestId('deploy-saved-to-rollout-button').click();
    await page.getByTestId('confirm-deploy-rollout-button').click();
    await expect.poll(() => rolloutDeployBody).not.toBeNull();
    expect(rolloutDeployBody).toEqual({ traffic_percent: 10 });
  });

  test('renders settings without strict mode controls for a read-only settings viewer', async ({ page }) => {
    const settingsPage = new SettingsPage(page);

    await mockAuthMe(page, ['view_settings']);
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
