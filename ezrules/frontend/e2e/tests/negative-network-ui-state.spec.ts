import { expect, Page, Route, test } from '@playwright/test';
import { RuleDetailPage } from '../pages/rule-detail.page';
import { RuleListPage } from '../pages/rule-list.page';
import { SettingsPage } from '../pages/settings.page';

test.use({ storageState: { cookies: [], origins: [] } });

const RULE_MANAGER_PERMISSIONS = [
  'view_rules',
  'modify_rule',
  'pause_rules',
  'promote_rules',
];

const SETTINGS_MANAGER_PERMISSIONS = [
  'view_roles',
  'manage_permissions',
  'manage_neutral_outcome',
];

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function seedAuthTokens(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem('ezrules_access_token', 'e2e-access-token');
    window.localStorage.setItem('ezrules_refresh_token', 'e2e-refresh-token');
  });
}

async function mockAuthenticatedUser(page: Page, permissions: string[]) {
  await seedAuthTokens(page);
  await page.route('**/api/v2/auth/me', async route => {
    await fulfillJson(route, {
      id: 1,
      email: 'negative-state@example.com',
      active: true,
      roles: [{ id: 1, name: 'manager', description: 'Negative state test manager' }],
      permissions,
      last_login_at: null,
    });
  });
}

function runtimeSettingsBody(overrides: Record<string, unknown> = {}) {
  return {
    auto_promote_active_rule_updates: false,
    default_auto_promote_active_rule_updates: false,
    main_rule_execution_mode: 'all_matches',
    default_main_rule_execution_mode: 'all_matches',
    rule_quality_lookback_days: 30,
    default_rule_quality_lookback_days: 30,
    neutral_outcome: 'RELEASE',
    default_neutral_outcome: 'RELEASE',
    invalid_allowlist_rules: [],
    ...overrides,
  };
}

async function mockRuntimeSettings(page: Page, body: Record<string, unknown> = runtimeSettingsBody()) {
  await page.route('**/api/v2/settings/runtime', async route => {
    await fulfillJson(route, body);
  });
}

async function mockRulesList(
  page: Page,
  body: unknown,
  beforeFulfill?: () => Promise<void>,
) {
  await page.route('**/api/v2/rules', async route => {
    if (route.request().method() !== 'GET') {
      await fulfillJson(route, { success: false, error: 'Unexpected method' }, 405);
      return;
    }
    await beforeFulfill?.();
    await fulfillJson(route, body);
  });
}

async function mockSettingsApis(
  page: Page,
  options: {
    runtimeBody?: Record<string, unknown>;
    runtimePutStatus?: number;
    runtimePutBody?: unknown;
    aiAuthoringBody?: Record<string, unknown>;
    hierarchyBody?: Record<string, unknown>;
    optionsBody?: Record<string, unknown>;
    pairsBody?: Record<string, unknown>;
  } = {},
) {
  await page.route('**/api/v2/settings/runtime', async route => {
    if (route.request().method() === 'PUT' && options.runtimePutStatus) {
      await fulfillJson(route, options.runtimePutBody ?? { detail: 'Forbidden' }, options.runtimePutStatus);
      return;
    }
    await fulfillJson(route, options.runtimeBody ?? runtimeSettingsBody());
  });
  await page.route('**/api/v2/settings/ai-authoring', async route => {
    await fulfillJson(route, options.aiAuthoringBody ?? {
      provider: 'openai',
      supported_providers: ['openai'],
      enabled: false,
      model: 'gpt-4.1-mini',
      api_key_configured: false,
    });
  });
  await page.route('**/api/v2/settings/outcome-hierarchy', async route => {
    await fulfillJson(route, options.hierarchyBody ?? {
      outcomes: [
        { ao_id: 1, outcome_name: 'HOLD', severity_rank: 1 },
        { ao_id: 2, outcome_name: 'RELEASE', severity_rank: 2 },
      ],
    });
  });
  await page.route('**/api/v2/settings/rule-quality-pairs/options', async route => {
    await fulfillJson(route, options.optionsBody ?? {
      outcomes: ['HOLD', 'RELEASE'],
      labels: ['fraud'],
    });
  });
  await page.route('**/api/v2/settings/rule-quality-pairs', async route => {
    await fulfillJson(route, options.pairsBody ?? { pairs: [] });
  });
}

function ruleDetailBody() {
  return {
    r_id: 42,
    rid: 'NEGATIVE_STATE_RULE',
    description: 'Original negative-state rule description',
    logic: 'if $amount > 100:\n\treturn !HOLD',
    execution_order: 1,
    evaluation_lane: 'main',
    status: 'draft',
    effective_from: null,
    approved_by: null,
    approved_at: null,
    created_at: '2026-01-01T00:00:00Z',
    revisions: [],
    in_shadow: false,
    in_rollout: false,
    rollout_percent: null,
  };
}

async function mockRuleDetailApis(
  page: Page,
  options: {
    saveStatus?: number;
    saveBody?: unknown;
    triggeredEventsBody?: unknown;
    backtestResultsBody?: unknown;
    backtestTaskBody?: unknown;
  } = {},
) {
  await page.route('**/api/v2/**', async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === '/api/v2/auth/me') {
      await fulfillJson(route, {
        id: 1,
        email: 'negative-state@example.com',
        active: true,
        roles: [{ id: 1, name: 'manager', description: 'Negative state test manager' }],
        permissions: RULE_MANAGER_PERMISSIONS,
        last_login_at: null,
      });
      return;
    }

    if (path === '/api/v2/auth/refresh') {
      await fulfillJson(route, {
        access_token: 'refreshed-e2e-access-token',
        refresh_token: 'refreshed-e2e-refresh-token',
        token_type: 'bearer',
        expires_in: 3600,
      });
      return;
    }

    if (path === '/api/v2/auth/logout') {
      await fulfillJson(route, { message: 'Logged out' });
      return;
    }

    if (path === '/api/v2/settings/runtime') {
      await fulfillJson(route, runtimeSettingsBody());
      return;
    }

    if (path === '/api/v2/field-types/observations') {
      await fulfillJson(route, { observations: [] });
      return;
    }

    if (path === '/api/v2/features') {
      await fulfillJson(route, { features: [] });
      return;
    }

    if (path === '/api/v2/outcomes') {
      await fulfillJson(route, { outcomes: [] });
      return;
    }

    if (path === '/api/v2/user-lists') {
      await fulfillJson(route, { lists: [] });
      return;
    }

    if (path === '/api/v2/rules/verify') {
      await fulfillJson(route, {
        valid: true,
        params: ['amount'],
        referenced_lists: [],
        referenced_outcomes: ['HOLD'],
        referenced_features: [],
        warnings: [],
        errors: [],
      });
      return;
    }

    if (path === '/api/v2/rules/42/triggered-events') {
      await fulfillJson(route, options.triggeredEventsBody ?? {
        events: [],
        total: 0,
        limit: 10,
        offset: 0,
      });
      return;
    }

    if (path === '/api/v2/rules/42' && method === 'PUT') {
      await fulfillJson(
        route,
        options.saveBody ?? { detail: 'Rule save failed.' },
        options.saveStatus ?? 500,
      );
      return;
    }

    if (path === '/api/v2/rules/42' && method === 'GET') {
      await fulfillJson(route, ruleDetailBody());
      return;
    }

    if (path === '/api/v2/shadow') {
      await fulfillJson(route, { rules: [], version: 1 });
      return;
    }

    if (path === '/api/v2/rollouts') {
      await fulfillJson(route, { rules: [], version: 1 });
      return;
    }

    if (path === '/api/v2/backtesting/42') {
      await fulfillJson(route, options.backtestResultsBody ?? { results: [] });
      return;
    }

    if (path.startsWith('/api/v2/backtesting/task/')) {
      await fulfillJson(route, options.backtestTaskBody ?? {
        status: 'SUCCESS',
        queue_status: 'done',
        stored_result: {},
        proposed_result: {},
        total_records: 0,
      });
      return;
    }

    if (path === '/api/v2/analytics/rules/42/outcomes-distribution') {
      await fulfillJson(route, { labels: [], datasets: [], aggregation: '6h' });
      return;
    }

    await fulfillJson(route, { detail: `Unhandled rule detail path: ${path}` }, 404);
  });
}

test.describe('Negative network and UI states', () => {
  test('redirects to login when auth/me rejects the stored session', async ({ page }) => {
    await seedAuthTokens(page);
    await page.route('**/api/v2/auth/me', async route => {
      await fulfillJson(route, { detail: 'Session expired' }, 401);
    });

    let refreshRequests = 0;
    await page.route('**/api/v2/auth/refresh', async route => {
      refreshRequests += 1;
      await fulfillJson(route, { detail: 'Refresh should not run for auth/me' }, 401);
    });

    await page.goto('/rules');

    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator('h1')).toHaveText('ezrules');
    expect(refreshRequests).toBe(0);
  });

  test('stops after one refresh attempt when a protected request returns 401', async ({ page }) => {
    await mockAuthenticatedUser(page, ['view_rules']);
    await mockRuntimeSettings(page);

    let rulesRequests = 0;
    let refreshRequests = 0;
    await page.route('**/api/v2/rules', async route => {
      rulesRequests += 1;
      await fulfillJson(route, { detail: 'Access token expired' }, 401);
    });
    await page.route('**/api/v2/auth/refresh', async route => {
      refreshRequests += 1;
      await fulfillJson(route, { detail: 'Refresh token expired' }, 401);
    });
    await page.route('**/api/v2/auth/logout', async route => {
      await fulfillJson(route, { message: 'Logged out' });
    });

    await page.goto('/rules');

    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator('h1')).toHaveText('ezrules');
    await page.waitForTimeout(300);
    expect(rulesRequests).toBe(1);
    expect(refreshRequests).toBe(1);
  });

  test('keeps edited rule input visible when save returns 500', async ({ page }) => {
    const ruleDetailPage = new RuleDetailPage(page);
    const editedDescription = 'Keep this description after the failed save';
    const editedLogic = 'if $amount > 999:\n\treturn !HOLD';

    await mockAuthenticatedUser(page, RULE_MANAGER_PERMISSIONS);
    await mockRuleDetailApis(page, {
      saveStatus: 500,
      saveBody: { detail: 'Database unavailable while saving the rule.' },
      triggeredEventsBody: {
        events: null,
        total: null,
        limit: null,
        offset: null,
      },
    });

    await ruleDetailPage.goto(42);
    await ruleDetailPage.waitForRuleToLoad();
    await expect(ruleDetailPage.triggeredEventsEmptyState).toBeVisible();

    await ruleDetailPage.clickEdit();
    await ruleDetailPage.setDescription(editedDescription);
    await ruleDetailPage.setLogic(editedLogic);
    await ruleDetailPage.clickSave();

    await expect(page.getByText('Database unavailable while saving the rule.')).toBeVisible();
    await expect(ruleDetailPage.saveButton).toBeVisible();
    await expect(ruleDetailPage.descriptionTextarea).toHaveValue(editedDescription);
    await expect(ruleDetailPage.editableLogicTextarea).toHaveValue(editedLogic);
    await expect(ruleDetailPage.saveSuccessMessage).toHaveCount(0);
  });

  test('shows a retry state for failed backtest polling results', async ({ page }) => {
    await mockAuthenticatedUser(page, RULE_MANAGER_PERMISSIONS);
    await mockRuleDetailApis(page, {
      backtestResultsBody: {
        results: [{
          task_id: 'bt-failed',
          created_at: '2026-01-01T00:00:00Z',
          completed_at: '2026-01-01T00:00:10Z',
          stored_logic: 'if $amount > 100:\n\treturn !HOLD',
          proposed_logic: 'if $amount > 999:\n\treturn !HOLD',
          status: 'FAILURE',
          queue_status: 'failed',
        }],
      },
      backtestTaskBody: {
        status: 'FAILURE',
        queue_status: 'failed',
        error: 'Worker lost the backtest job.',
      },
    });

    await page.goto('/rules/42');

    await expect(page.getByTestId('backtest-results-card')).toBeVisible();
    await expect(page.getByTestId('backtest-status-0')).toHaveText('Failed');
    await expect(page.getByTestId('backtest-retry-button')).toBeVisible();
    await page.getByTestId('backtest-toggle-button').click();
    await expect(page.getByTestId('backtest-expanded-content')).toContainText('Worker lost the backtest job.');
  });

  test('does not show a fake settings success message when update returns 403', async ({ page }) => {
    const settingsPage = new SettingsPage(page);

    await mockAuthenticatedUser(page, SETTINGS_MANAGER_PERMISSIONS);
    await mockSettingsApis(page, {
      runtimePutStatus: 403,
      runtimePutBody: { detail: 'You do not have permission to update runtime settings.' },
    });

    await settingsPage.goto();
    await settingsPage.waitForPageToLoad();
    await settingsPage.setLookbackDays(45);
    await settingsPage.save();

    await expect(page.locator('.bg-red-50')).toContainText('You do not have permission to update runtime settings.');
    await expect(settingsPage.successMessage).toHaveCount(0);
    await expect(settingsPage.lookbackDaysInput).toHaveValue('45');
  });

  test('renders empty settings sections when optional API arrays are null', async ({ page }) => {
    await mockAuthenticatedUser(page, SETTINGS_MANAGER_PERMISSIONS);
    await mockSettingsApis(page, {
      runtimeBody: runtimeSettingsBody({ invalid_allowlist_rules: null }),
      aiAuthoringBody: {
        provider: null,
        supported_providers: null,
        enabled: null,
        model: null,
        api_key_configured: null,
      },
      hierarchyBody: { outcomes: null },
      optionsBody: { outcomes: null, labels: null },
      pairsBody: { pairs: null },
    });

    await page.goto('/settings');

    await expect(page.locator('h1')).toHaveText('Settings');
    await expect(page.getByText('No outcomes exist yet. Add outcomes on the Outcomes page first.')).toBeVisible();
    await expect(page.getByText('No curated pairs configured yet. Add at least one pair to enable Rule Quality reporting.')).toBeVisible();
    await expect(page.getByText('Failed to load settings data.')).toHaveCount(0);
  });

  test('shows stable loading and empty states for a slow rules response', async ({ page }) => {
    const rulePage = new RuleListPage(page);
    let releaseRules!: () => void;
    const rulesGate = new Promise<void>(resolve => {
      releaseRules = resolve;
    });

    await mockAuthenticatedUser(page, ['view_rules']);
    await mockRuntimeSettings(page);
    await mockRulesList(page, { rules: [], evaluator_endpoint: 'http://localhost:8888/api/v2/evaluate' }, () => rulesGate);

    await rulePage.goto();

    await expect(rulePage.heading).toHaveText('Rules');
    await expect(rulePage.loadingSpinner.first()).toBeVisible();
    await expect(rulePage.emptyStateMessage).toHaveCount(0);

    releaseRules();

    await expect(rulePage.emptyStateMessage).toBeVisible();
    await expect(page.getByText('0 rules total')).toBeVisible();
  });

  test('shows a useful rules error when the API is unreachable', async ({ page }) => {
    const rulePage = new RuleListPage(page);

    await mockAuthenticatedUser(page, ['view_rules']);
    await mockRuntimeSettings(page);
    await page.route('**/api/v2/rules', async route => {
      await route.abort('failed');
    });

    await rulePage.goto();

    await expect(page.getByText('Failed to load rules. Please try again.')).toBeVisible();
  });

  test('shows an understandable login error when the auth API is unreachable', async ({ page }) => {
    await page.route('**/api/v2/auth/login', async route => {
      await route.abort('failed');
    });

    await page.goto('/login');
    await page.locator('input#email').fill('admin@test_org.com');
    await page.locator('input#password').fill('12345678');
    await page.locator('button[type="submit"]').click();

    await expect(page.locator('.bg-red-50.border-red-200')).toContainText('An error occurred. Please try again.');
  });

  test('renders tested-events empty state when list payload fields are null', async ({ page }) => {
    await mockAuthenticatedUser(page, ['view_rules']);
    await page.route('**/api/v2/tested-events**', async route => {
      await fulfillJson(route, {
        events: null,
        total: null,
        limit: null,
      });
    });

    await page.goto('/tested-events');

    await expect(page.getByTestId('tested-events-empty')).toBeVisible();
    await expect(page.getByText('No tested events yet')).toBeVisible();
    await expect(page.getByText('Failed to load tested events. Please try again.')).toHaveCount(0);
  });
});
