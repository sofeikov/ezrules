import { test, expect } from '@playwright/test';

test.describe('Promotion Permissions', () => {
  test('hides pause button when current user lacks pause_rules', async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('ezrules_access_token', 'test-token');
    });

    await page.route('**/api/v2/auth/me', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          email: 'editor@example.com',
          active: true,
          roles: [{ id: 1, name: 'editor', description: 'Editor role' }],
          permissions: ['view_rules', 'modify_rule'],
          last_login_at: null,
        }),
      });
    });

    await page.route('**/api/v2/rules', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rules: [
            {
              r_id: 42,
              rid: 'active_rule_hidden_pause',
              description: 'Active rule',
              logic: 'event.amount > 100',
              evaluation_lane: 'main',
              status: 'active',
              effective_from: null,
              approved_by: null,
              approved_at: null,
              created_at: null,
              in_shadow: false,
              in_rollout: false,
              rollout_percent: null,
            },
          ],
          evaluator_endpoint: 'http://localhost:9999',
        }),
      });
    });

    await page.goto('/rules');
    await expect(page.locator('tbody tr')).toHaveCount(1);
    await expect(page.locator('button:has-text("Pause")')).toHaveCount(0);
  });

  test('hides draft promote button when current user lacks promote_rules', async ({ page }) => {
    await page.route('**/api/v2/auth/me', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          email: 'viewer@example.com',
          active: true,
          roles: [{ id: 1, name: 'viewer', description: 'Viewer role' }],
          permissions: ['view_rules'],
          last_login_at: null,
        }),
      });
    });

    await page.route('**/api/v2/rules', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rules: [
            {
              r_id: 42,
              rid: 'draft_rule_hidden_promote',
              description: 'Draft rule',
              logic: 'event.amount > 100',
              status: 'draft',
              effective_from: null,
              approved_by: null,
              approved_at: null,
              created_at: null,
              in_shadow: false,
            },
          ],
          evaluator_endpoint: 'http://localhost:9999',
        }),
      });
    });

    await page.goto('/rules');
    await expect(page.locator('tbody tr')).toHaveCount(1);
    await expect(page.locator('button:has-text("Promote")')).toHaveCount(0);
  });

  test('hides shadow promote button when current user lacks promote_rules', async ({ page }) => {
    await page.route('**/api/v2/auth/me', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          email: 'viewer@example.com',
          active: true,
          roles: [{ id: 1, name: 'viewer', description: 'Viewer role' }],
          permissions: ['view_rules', 'modify_rule'],
          last_login_at: null,
        }),
      });
    });

    await page.route('**/api/v2/shadow', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rules: [
            {
              r_id: 42,
              rid: 'shadow_rule_hidden_promote',
              description: 'Shadow rule',
              logic: 'return !HOLD',
            },
          ],
          version: 1,
        }),
      });
    });

    await page.route('**/api/v2/shadow/stats', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rules: [
            {
              r_id: 42,
              total: 0,
              shadow_outcomes: [],
              prod_outcomes: [],
            },
          ],
        }),
      });
    });

    await page.goto('/shadow-rules');
    await expect(page.locator('[data-testid="shadow-rules-table"]')).toBeVisible();
    await expect(page.locator('[data-testid="promote-button"]')).toHaveCount(0);
  });
});
