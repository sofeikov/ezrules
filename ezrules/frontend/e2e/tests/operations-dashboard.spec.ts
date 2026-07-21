import { expect, Page, test } from '@playwright/test';
import type { OperationsSummaryResponse } from '../../src/app/services/operations-dashboard.service';
import { OperationsDashboardPage } from '../pages/operations-dashboard.page';

async function mockAuth(page: Page, permissions: string[] = ['view_cases']): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.setItem('ezrules_access_token', 'operations-spec-token');
  });
  await page.route('**/api/v2/auth/me', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      id: 1,
      email: 'operations.manager@example.com',
      active: true,
      roles: [{ id: 1, name: 'operations_manager', description: 'Operations manager' }],
      permissions,
      last_login_at: null,
    }),
  }));
  await page.route('**/api/v2/notifications**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(route.request().url().includes('unread-count') ? { unread_count: 0 } : { notifications: [] }),
  }));
}

function summary(days = 30): OperationsSummaryResponse {
  const start = new Date(Date.UTC(2026, 5, 22));
  return {
    days,
    period_start: start.toISOString(),
    period_end: '2026-07-21T14:32:00Z',
    generated_at: '2026-07-21T14:32:00Z',
    summary: {
      active_cases: 184,
      unassigned_cases: 37,
      resolved_cases: 458,
      dispositioned_cases: 459,
      false_positive_cases: 146,
      false_positive_rate: 0.3181,
    },
    case_flow: Array.from({ length: days }, (_, index) => ({
      date: new Date(start.getTime() + index * 86_400_000).toISOString().slice(0, 10),
      opened: index % 5,
      resolved: (index + 2) % 4,
    })),
    attention_cases: [{
      case_id: 2841,
      outcome: 'CANCEL',
      assigned_to_email: null,
      age_seconds: 187200,
    }],
    noisy_rules: [{
      rid: 'beneficiary_velocity_24h',
      description: 'Beneficiary Velocity 24h',
      case_count: 91,
      resolved_count: 72,
      false_positive_count: 35,
      false_positive_rate: 0.4861,
    }],
  };
}

test.describe('Operations dashboard MVP', () => {
  test('shows bounded case metrics and the two action tables', async ({ page }) => {
    await mockAuth(page);
    await page.route('**/api/v2/operations/summary?**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(summary()),
    }));
    const operations = new OperationsDashboardPage(page);

    await operations.goto();

    await expect(operations.heading).toBeVisible();
    await expect(operations.activeCases).toHaveText('184');
    await expect(operations.unassignedCases).toHaveText('37');
    await expect(operations.resolvedCases).toHaveText('458');
    await expect(operations.falsePositiveRate).toHaveText('31.8%');
    await expect(operations.attentionTable).toContainText('#2841');
    await expect(operations.attentionTable).toContainText('Unassigned');
    await expect(operations.rulesTable).toContainText('Beneficiary Velocity 24h');
    await expect(page.getByTestId('operations-case-flow-chart')).toBeVisible();
  });

  test('reloads only when the period changes or the user refreshes', async ({ page }) => {
    await mockAuth(page);
    const requestedDays: string[] = [];
    await page.route('**/api/v2/operations/summary?**', route => {
      const days = new URL(route.request().url()).searchParams.get('days') || '30';
      requestedDays.push(days);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(summary(Number(days))),
      });
    });
    const operations = new OperationsDashboardPage(page);
    await operations.goto();
    await expect(operations.activeCases).toBeVisible();

    await operations.period.selectOption({ label: 'Last 7 days' });
    await expect.poll(() => requestedDays).toEqual(['30', '7']);
    await operations.refresh.click();
    await expect.poll(() => requestedDays).toEqual(['30', '7', '7']);
  });

  test('shows empty states without treating them as errors', async ({ page }) => {
    await mockAuth(page);
    const empty = summary();
    empty.summary.active_cases = 0;
    empty.summary.unassigned_cases = 0;
    empty.summary.resolved_cases = 0;
    empty.summary.dispositioned_cases = 0;
    empty.summary.false_positive_cases = 0;
    empty.summary.false_positive_rate = null;
    empty.attention_cases = [];
    empty.noisy_rules = [];
    await page.route('**/api/v2/operations/summary?**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(empty),
    }));
    const operations = new OperationsDashboardPage(page);

    await operations.goto();

    await expect(operations.falsePositiveRate).toHaveText('—');
    await expect(page.getByTestId('operations-attention-empty')).toBeVisible();
    await expect(page.getByTestId('operations-rules-empty')).toBeVisible();
  });

  test('offers a retry after a summary failure', async ({ page }) => {
    await mockAuth(page);
    let attempt = 0;
    await page.route('**/api/v2/operations/summary?**', route => {
      attempt += 1;
      if (attempt === 1) {
        return route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"failed"}' });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(summary()),
      });
    });
    const operations = new OperationsDashboardPage(page);
    await operations.goto();

    await expect(page.getByText('Failed to load operations data.')).toBeVisible();
    await operations.retry.click();
    await expect(operations.activeCases).toHaveText('184');
  });

  test('requires case-view permission', async ({ page }) => {
    await mockAuth(page, []);
    const operations = new OperationsDashboardPage(page);

    await operations.goto();

    await expect(page).toHaveURL(/access-denied/);
    await expect(page.getByRole('heading', { name: 'Access Denied' })).toBeVisible();
  });

  test('opens the existing Cases workflow', async ({ page }) => {
    await mockAuth(page);
    await page.route('**/api/v2/operations/summary?**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(summary()),
    }));
    await page.route('**/api/v2/cases?**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ cases: [], total: 0 }),
    }));
    await page.route('**/api/v2/cases/assignees', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ users: [] }),
    }));
    await page.route('**/api/v2/integration-events?**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ events: [], next_cursor: null }),
    }));
    const operations = new OperationsDashboardPage(page);
    await operations.goto();
    await expect(operations.activeCases).toBeVisible();

    await operations.openCases.click();

    await expect(page).toHaveURL(/\/cases$/);
    await expect(page.getByRole('heading', { name: 'Cases', exact: true })).toBeVisible();
  });
});
