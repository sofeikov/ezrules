import { expect, Page, Route, test } from '@playwright/test';
import { FeaturesPage } from '../pages/features.page';

type FeaturePayload = {
  name: string;
  description?: string | null;
  entity: string;
  feature_name: string;
  entity_key: string;
  feature_kind?: 'aggregate' | 'graph';
  aggregation_type: string;
  source_field?: string | null;
  window_seconds: number;
  filters?: unknown[];
  inclusion_policy?: string;
  null_handling?: string;
  graph_config?: {
    target_entity: string;
    allowed_entity_types: string[];
    max_depth: number;
    max_expanded_nodes: number;
  } | null;
};

type MockFeature = FeaturePayload & {
  fd_id: number;
  available_as: string;
  feature_kind: 'aggregate' | 'graph';
  window_label: string;
  filters: unknown[];
  inclusion_policy: string;
  null_handling: string;
  graph_config: FeaturePayload['graph_config'];
  status: 'draft' | 'active' | 'deprecated';
  version: number;
  dependency_count: number;
  created_at: string;
  updated_at: string;
};

const WINDOW_LABELS = new Map<number, string>([
  [600, '10m'],
  [3600, '1h'],
  [86400, '24h'],
  [604800, '7d'],
  [2592000, '30d'],
  [7776000, '90d'],
  [15552000, '180d'],
]);

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

function toFeature(payload: FeaturePayload, fdId: number): MockFeature {
  const now = new Date().toISOString();
  const featureKind = payload.feature_kind ?? 'aggregate';
  return {
    ...payload,
    fd_id: fdId,
    available_as: `stat[${payload.entity}.${payload.feature_name}]`,
    feature_kind: featureKind,
    source_field: payload.source_field ?? null,
    window_label: WINDOW_LABELS.get(payload.window_seconds) ?? `${payload.window_seconds}s`,
    filters: payload.filters ?? [],
    inclusion_policy: payload.inclusion_policy ?? 'previous_events',
    null_handling: payload.null_handling ?? 'exclude',
    graph_config: payload.graph_config ?? null,
    status: 'draft',
    version: 1,
    dependency_count: 0,
    created_at: now,
    updated_at: now,
  };
}

test.describe('Features Page', () => {
  let featuresPage: FeaturesPage;
  let features: MockFeature[];
  let nextFeatureId: number;
  let lastCreatePayload: FeaturePayload | null;

  test.beforeEach(async ({ page }) => {
    features = [];
    nextFeatureId = 1000;
    lastCreatePayload = null;
    featuresPage = new FeaturesPage(page);

    await page.addInitScript(() => {
      localStorage.setItem('ezrules_access_token', 'ui-test-access-token');
    });

    await mockFeaturePageApi(page, {
      getFeatures: () => features,
      createFeature: (payload) => {
        lastCreatePayload = payload;
        const feature = toFeature(payload, nextFeatureId++);
        features = [feature, ...features];
        return feature;
      },
      activateFeature: (featureId) => {
        const feature = features.find((item) => item.fd_id === featureId);
        if (!feature) {
          return null;
        }
        feature.status = 'active';
        feature.version += 1;
        feature.updated_at = new Date().toISOString();
        return feature;
      },
    });
  });

  test('loads from sidebar navigation', async ({ page }) => {
    await page.goto('/dashboard');
    const link = page.locator('a:has-text("Features")');
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/.*features/);
    await expect(featuresPage.heading).toHaveText('Features');
  });

  test('creates and activates a feature definition', async () => {
    await featuresPage.goto();
    await featuresPage.waitForLoad();

    const suffix = Date.now();
    const name = `Sender velocity ${suffix}`;
    const featureName = `sent_amount_sum_24h_${suffix}`;

    await featuresPage.createFeature(name, featureName);
    await expect(featuresPage.featureRow(name)).toContainText(`stat[sender.${featureName}]`);
    await expect(featuresPage.featureRow(name)).toContainText('draft');

    await featuresPage.activateFeature(name);
    await expect(featuresPage.featureRow(name)).toContainText('active');
  });

  test('creates and activates a graph feature definition', async () => {
    await featuresPage.goto();
    await featuresPage.waitForLoad();

    const suffix = Date.now();
    const name = `User card graph ${suffix}`;
    const featureName = `unique_cards_graph_90d_${suffix}`;

    await featuresPage.createGraphFeature(name, featureName);
    await expect(featuresPage.featureRow(name)).toContainText(`stat[user.${featureName}]`);
    expect(lastCreatePayload).toMatchObject({
      feature_kind: 'graph',
      entity: 'user',
      feature_name: featureName,
      entity_key: 'user_id',
      aggregation_type: 'graph_distinct_count',
      source_field: null,
      window_seconds: 7776000,
      graph_config: {
        target_entity: 'card',
        allowed_entity_types: ['user', 'account', 'card', 'device'],
        max_depth: 4,
        max_expanded_nodes: 10000,
      },
    });
    await expect(featuresPage.featureRow(name)).toContainText('graph_distinct_count(card) / 90d / depth 4');
    await expect(featuresPage.featureRow(name)).toContainText('draft');

    await featuresPage.activateFeature(name);
    await expect(featuresPage.featureRow(name)).toContainText('active');
  });
});

async function mockFeaturePageApi(
  page: Page,
  handlers: {
    getFeatures: () => MockFeature[];
    createFeature: (payload: FeaturePayload) => MockFeature;
    activateFeature: (featureId: number) => MockFeature | null;
  }
) {
  await page.route('**/api/v2/auth/me', async (route) => {
    await json(route, {
      id: 1,
      email: 'admin@test_org.com',
      active: true,
      roles: [{ id: 1, name: 'admin', description: null }],
      permissions: ['view_rules', 'view_outcomes', 'view_features', 'modify_features'],
      last_login_at: null,
    });
  });

  await page.route('**/api/v2/notifications**', async (route) => {
    if (route.request().url().includes('/unread-count')) {
      await json(route, { unread_count: 0 });
      return;
    }
    await json(route, { notifications: [] });
  });

  await page.route('**/api/v2/rules', async (route) => {
    await json(route, { rules: [], evaluator_endpoint: '/api/v2/evaluate' });
  });

  await page.route('**/api/v2/analytics/transaction-volume**', async (route) => {
    await json(route, { labels: [], data: [], aggregation: '6h' });
  });

  await page.route('**/api/v2/analytics/outcomes-distribution**', async (route) => {
    await json(route, { labels: [], datasets: [], aggregation: '6h' });
  });

  await page.route('**/api/v2/analytics/rule-activity**', async (route) => {
    await json(route, { aggregation: '6h', limit: 5, most_firing: [], least_firing: [] });
  });

  await page.route('**/api/v2/features/*/activate', async (route) => {
    const match = route.request().url().match(/\/api\/v2\/features\/(\d+)\/activate/);
    const feature = match ? handlers.activateFeature(Number(match[1])) : null;
    if (!feature) {
      await json(route, { detail: 'Feature not found' }, 404);
      return;
    }
    await json(route, { success: true, message: 'Feature activated', feature });
  });

  await page.route('**/api/v2/features', async (route) => {
    if (route.request().method() === 'GET') {
      await json(route, { features: handlers.getFeatures() });
      return;
    }
    if (route.request().method() === 'POST') {
      const feature = handlers.createFeature(route.request().postDataJSON() as FeaturePayload);
      await json(route, { success: true, message: 'Feature created', feature }, 201);
      return;
    }
    await route.fallback();
  });
}
