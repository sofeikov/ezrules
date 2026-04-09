import { test, expect } from '@playwright/test';
import { RuleListPage } from '../pages/rule-list.page';
import { getApiBaseUrl } from '../support/config';

const API_BASE = getApiBaseUrl();

/**
 * E2E tests for the Rule List page.
 * Tests only implemented features - displaying rules from the /api/v2/rules endpoint.
 */

test.describe('Rule List Page', () => {
  let rulePage: RuleListPage;

  test.beforeEach(async ({ page }) => {
    rulePage = new RuleListPage(page);
  });

  test.describe('Page Structure', () => {
    test('should load the rules page successfully', async ({ page }) => {
      await rulePage.goto();
      await expect(page).toHaveURL(/.*rules/);
      await expect(page).toHaveTitle(/ezrules/);
    });

    test('should display the correct page heading', async () => {
      await rulePage.goto();
      await expect(rulePage.heading).toHaveText('Rules');
    });

    test('should display the page description', async ({ page }) => {
      await rulePage.goto();
      const description = page.locator('text=Manage and monitor your business rules');
      await expect(description).toBeVisible();
    });

    test('should not display a broken Evaluate header link', async () => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      await expect(rulePage.evaluateLink).toHaveCount(0);
    });
  });

  test.describe('Loading States', () => {
    test('should show loading spinner initially', async ({ page }) => {
      await page.goto('/rules', { waitUntil: 'domcontentloaded' });

      // The spinner should appear briefly during loading
      // We check if it exists in the DOM (it may disappear quickly)
      const spinner = rulePage.loadingSpinner;
      const spinnerExists = await spinner.count() > 0 || await rulePage.rulesTable.isVisible();
      expect(spinnerExists).toBeTruthy();
    });

    test('should hide loading spinner after data loads', async () => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      // After loading completes, spinner should be gone
      await expect(rulePage.loadingSpinner).not.toBeVisible();
    });
  });

  test.describe('Rules Table Display', () => {
    test('should display the rules table', async () => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      await expect(rulePage.rulesTable).toBeVisible();
    });

    test('should display table headers', async ({ page }) => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      const headers = ['Rule ID', 'Description', 'Created', 'Actions'];

      for (const header of headers) {
        const headerCell = page.locator(`th:has-text("${header}")`);
        await expect(headerCell).toBeVisible();
      }
    });

    test('should display rule count', async ({ page }) => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      const ruleCount = await rulePage.getRuleCount();
      const summaryText = page.locator('text=/\\d+ rules total/');
      await expect(summaryText).toBeVisible();
      await expect(summaryText).toContainText(`${ruleCount} rules total`);
    });

    test('should display rule data in table rows', async ({ page }) => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      const ruleCount = await rulePage.getRuleCount();

      if (ruleCount > 0) {
        // Check first rule has required columns
        const firstRow = page.locator('tbody tr').first();
        await expect(firstRow.locator('td').nth(0)).toBeVisible(); // Rule ID
        await expect(firstRow.locator('td').nth(1)).toBeVisible(); // Description
        await expect(firstRow.locator('td').nth(2)).toBeVisible(); // Created
        await expect(firstRow.locator('td').nth(3)).toBeVisible(); // Actions
      }
    });

    test('should have View and Edit links for each rule', async ({ page }) => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      const ruleCount = await rulePage.getRuleCount();

      if (ruleCount > 0) {
        const firstRow = page.locator('tbody tr').first();
        const viewLink = firstRow.locator('a:has-text("View")');
        const editLink = firstRow.locator('a:has-text("Edit")');

        await expect(viewLink).toBeVisible();
        await expect(editLink).toBeVisible();
      }
    });

    test('should pause an active rule and refresh its status badge', async ({ page }) => {
      let paused = false;

      await page.addInitScript(() => {
        window.localStorage.setItem('ezrules_access_token', 'test-token');
      });

      await page.route('**/api/v2/auth/me', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 1,
            email: 'manager@example.com',
            active: true,
            roles: [{ id: 1, name: 'manager', description: 'Rule manager' }],
            permissions: ['view_rules', 'modify_rule', 'pause_rules', 'promote_rules', 'reorder_rules'],
            last_login_at: null,
          }),
        });
      });

      await page.route('**/api/v2/settings/runtime', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            auto_promote_active_rule_updates: false,
            default_auto_promote_active_rule_updates: false,
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

      await page.route('**/api/v2/rules/42/pause', async route => {
        paused = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            message: 'Rule paused',
            rule: {
              r_id: 42,
              rid: 'pause_me',
              description: 'Pauseable rule',
              logic: 'event.amount > 100',
              execution_order: 1,
              evaluation_lane: 'main',
              status: 'paused',
              effective_from: null,
              approved_by: null,
              approved_at: null,
              created_at: null,
              revisions: [],
            },
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
                rid: 'pause_me',
                description: 'Pauseable rule',
                logic: 'event.amount > 100',
                execution_order: 1,
                evaluation_lane: 'main',
                status: paused ? 'paused' : 'active',
                effective_from: null,
                approved_by: null,
                approved_at: null,
                created_at: null,
                in_shadow: false,
                in_rollout: false,
                rollout_percent: null,
              },
            ],
            evaluator_endpoint: `${API_BASE}/api/v2/evaluate`,
          }),
        });
      });

      page.once('dialog', async dialog => {
        await dialog.accept();
      });

      await rulePage.goto();
      await rulePage.waitForRulesToLoad();
      await page.getByRole('button', { name: 'Pause' }).click();

      await expect(page.locator('tbody tr').first()).toContainText('PAUSED');
      await expect(page.getByRole('button', { name: 'Resume' })).toBeVisible();
    });
  });

  test.describe('How to Run Section', () => {
    test('should toggle How to Run section when button is clicked', async ({ page }) => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      await expect(rulePage.howToRunSection).not.toBeVisible();

      // Click to show
      await rulePage.toggleHowToRun();
      await expect(rulePage.howToRunSection).toBeVisible();

      // Click to hide
      await rulePage.toggleHowToRun();
      await expect(rulePage.howToRunSection).not.toBeVisible();
    });

    test('should display the runtime evaluate endpoint in How to Run section', async () => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      await rulePage.toggleHowToRun();

      await expect(rulePage.evaluateEndpointCode).toBeVisible();
      await expect(rulePage.evaluateEndpointCode).toHaveText(`${API_BASE}/api/v2/evaluate`);
    });

    test('should display curl example with the runtime evaluate endpoint', async () => {
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      await rulePage.toggleHowToRun();

      await expect(rulePage.curlExample).toBeVisible();
      await expect(rulePage.curlExample).toContainText('curl');
      await expect(rulePage.curlExample).toContainText('-X POST');
      await expect(rulePage.curlExample).toContainText('Content-Type: application/json');
      await expect(rulePage.curlExample).toContainText(`${API_BASE}/api/v2/evaluate`);
      await expect(rulePage.curlExample).not.toContainText('localhost:9999');
    });
  });

  test.describe('Responsive Design', () => {
    test('should display correctly on desktop viewport', async ({ page }) => {
      await page.setViewportSize({ width: 1920, height: 1080 });
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      await expect(rulePage.rulesTable).toBeVisible();
      await expect(rulePage.heading).toBeVisible();
    });

    test('should maintain layout on smaller desktop viewport', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 720 });
      await rulePage.goto();
      await rulePage.waitForRulesToLoad();

      await expect(rulePage.rulesTable).toBeVisible();
      await expect(rulePage.heading).toBeVisible();
    });
  });

  test.describe('Future Features (Skipped)', () => {
    test.skip('should display empty state when no rules exist', async ({ page }) => {
      // This test is skipped - requires empty database
      // Will be enabled when we have proper test data management
    });
  });
});
