import { expect, Page, Route, test } from '@playwright/test';
import { TestedEventsPage } from '../pages/tested-events.page';

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function mockTestedEventGraphApi(page: Page, onGraphRequest: () => void) {
  await page.addInitScript(() => {
    localStorage.setItem('ezrules_access_token', 'ui-test-access-token');
  });

  await page.route('**/api/v2/auth/me', async (route) => {
    await json(route, {
      id: 1,
      email: 'admin@test_org.com',
      active: true,
      roles: [{ id: 1, name: 'admin', description: null }],
      permissions: ['view_rules', 'view_outcomes'],
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

  await page.route('**/api/v2/tested-events/101/graph**', async (route) => {
    onGraphRequest();
    await json(route, {
      nodes: [
        {
          id: 'event:501',
          kind: 'event',
          label: 'txn-graph-root',
          transaction_id: 'txn-graph-root',
          event_version: 1,
          effective_at: '2026-06-01T12:00:00Z',
          root: true,
          expandable: false,
          entity_type: null,
          entity_value: null,
          entity_value_hash: null,
        },
        {
          id: 'entity:user:hash-user-1',
          kind: 'entity',
          label: 'user: user-1',
          transaction_id: null,
          event_version: null,
          effective_at: null,
          root: false,
          expandable: true,
          entity_type: 'user',
          entity_value: 'user-1',
          entity_value_hash: 'hash-user-1',
        },
      ],
      edges: [
        {
          id: 'event:501->entity:user:hash-user-1:user_id',
          source: 'event:501',
          target: 'entity:user:hash-user-1',
          label: 'user_id',
          field_path: 'user_id',
        },
      ],
      root_event_node_id: 'event:501',
      max_events: 25,
      max_hops: 3,
      event_count: 1,
      truncated: false,
    });
  });

  await page.route('**/api/v2/tested-events**', async (route) => {
    if (route.request().url().includes('/graph')) {
      await route.fallback();
      return;
    }
    await json(route, {
      events: [
        {
          evaluation_decision_id: 101,
          transaction_id: 'txn-graph-root',
          effective_at: '2026-06-01T12:00:00Z',
          observed_at: '2026-06-01T12:00:00Z',
          first_effective_at: '2026-06-01T12:00:00Z',
          first_observed_at: '2026-06-01T12:00:00Z',
          event_version: 1,
          is_current: true,
          resolved_outcome: 'HOLD',
          label_name: null,
          outcome_counters: { HOLD: 1 },
          event_data: {
            user_id: 'user-1',
            card_fingerprint: 'card-1',
            amount: 250,
          },
          triggered_rules: [],
        },
      ],
      total: 1,
      limit: 50,
    });
  });
}

test.describe('Tested Events Graph', () => {
  test('shows an interactive graph panel for a tested event', async ({ page }) => {
    let graphRequests = 0;
    await mockTestedEventGraphApi(page, () => {
      graphRequests += 1;
    });

    const testedEventsPage = new TestedEventsPage(page);
    await testedEventsPage.goto();
    await testedEventsPage.waitForPageToLoad();

    await testedEventsPage.showFirstEventGraph();

    await expect(testedEventsPage.detailsPanels.first()).toBeVisible();
    await expect(testedEventsPage.graphPanels.first()).toBeVisible();
    await expect(page.locator('[data-testid="tested-event-graph-canvas"]')).toBeVisible();
    await expect(page.getByLabel('Hops')).toHaveValue('3');
    await expect.poll(() => graphRequests).toBe(1);
  });
});
