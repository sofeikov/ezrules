import { expect, Page, test } from '@playwright/test';
import { CasesPage } from '../pages/cases.page';

function mockAuthMe(page: Page, permissions: string[]) {
  page.addInitScript(() => {
    window.localStorage.setItem('ezrules_access_token', 'case-spec-token');
  });
  return page.route('**/api/v2/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        email: 'case.manager@example.com',
        active: true,
        roles: [{ id: 1, name: 'case_manager', description: 'Case manager' }],
        permissions,
        last_login_at: null,
      }),
    });
  });
}

const caseItem = {
  id: 42,
  transaction_id: 'txn-premium-review-001',
  current_event_version_id: 100,
  current_evaluation_decision_id: 200,
  opened_by_evaluation_decision_id: 200,
  previous_evaluation_decision_id: null,
  resolved_outcome: 'HOLD',
  previous_resolved_outcome: null,
  status: 'open',
  decision_state: 'current',
  priority: 2,
  assigned_to_user_id: null,
  assigned_to_email: null,
  resolved_by_user_id: null,
  resolved_by_email: null,
  resolution_disposition: null,
  resolution_action: null,
  resolution_note: null,
  resolution_label_id: null,
  reopened_from_case_id: null,
  created_at: '2026-07-05T10:00:00Z',
  updated_at: '2026-07-05T10:00:00Z',
  resolved_at: null,
};

test.describe('Cases', () => {
  test('lists and resolves a case while showing integration events', async ({ page }) => {
    const casesPage = new CasesPage(page);
    await mockAuthMe(page, ['view_cases', 'manage_cases', 'view_integrations']);
    const caseListUrls: string[] = [];

    await page.route('**/api/v2/cases?**', async (route) => {
      caseListUrls.push(route.request().url());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ cases: [caseItem], total: 1 }),
      });
    });
    await page.route('**/api/v2/cases/assignees', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ users: [{ id: 1, email: 'case.manager@example.com' }] }),
      });
    });
    await page.route('**/api/v2/cases/42', async (route) => {
      if (route.request().method() === 'PATCH') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            message: 'Case updated',
            case: {
              ...caseItem,
              status: 'in_review',
              assigned_to_user_id: 1,
              assigned_to_email: 'case.manager@example.com',
            },
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          case: caseItem,
          evaluation: {
            evaluation_decision_id: 200,
            transaction_id: 'txn-premium-review-001',
            event_version_id: 100,
            event_version: 1,
            effective_at: '2026-07-05T09:58:00Z',
            observed_at: '2026-07-05T10:00:00Z',
            evaluated_at: '2026-07-05T10:00:00Z',
            is_current: true,
            resolved_outcome: 'HOLD',
            outcome_counters: { HOLD: 1 },
            event_data: {
              transaction_id: 'txn-premium-review-001',
              amount: 12500,
              sender_id: 'premium-customer-884',
            },
            triggered_rules: [
              {
                r_id: 7,
                rid: 'premium_amount_hold',
                description: 'Premium transfer requires manual review',
                outcome: 'HOLD',
                metadata_source: 'evaluation_snapshot',
                referenced_fields: ['amount', 'sender_id'],
              },
            ],
          },
          events: [
            {
              id: 1,
              case_id: 42,
              event_type: 'created',
              actor_user_id: null,
              source_ed_id: 200,
              external_event_id: 'case_evt_created',
              occurred_at: '2026-07-05T10:00:00Z',
              details: {},
              created_at: '2026-07-05T10:00:00Z',
            },
          ],
        }),
      });
    });
    await page.route('**/api/v2/cases/42/notes', async (route) => {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          message: 'Case note added',
          event: {
            id: 2,
            case_id: 42,
            event_type: 'note',
            actor_user_id: 1,
            source_ed_id: 200,
            external_event_id: 'case_evt_note',
            occurred_at: '2026-07-05T10:03:00Z',
            details: { note: 'Customer confirmed this transfer was expected.' },
            created_at: '2026-07-05T10:03:00Z',
          },
        }),
      });
    });
    await page.route('**/api/v2/integration-events?**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          events: [
            {
              id: 10,
              external_event_id: 'evt_evaluation_completed_200',
              source_type: 'evaluation_decision',
              source_id: 200,
              event_type: 'evaluation.completed',
              event_version: 1,
              occurred_at: '2026-07-05T10:00:00Z',
              payload: {},
              created_at: '2026-07-05T10:00:00Z',
            },
          ],
          next_cursor: null,
        }),
      });
    });
    await page.route('**/api/v2/cases/42/resolve', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          message: 'Case resolved',
          case: {
            ...caseItem,
            status: 'resolved',
            resolved_by_user_id: 1,
            resolved_by_email: 'case.manager@example.com',
            resolution_disposition: 'false_positive',
            resolution_action: 'release_transaction',
            resolution_note: 'Verified customer profile and cleared case.',
            resolved_at: '2026-07-05T10:05:00Z',
          },
        }),
      });
    });

    await casesPage.goto();
    await casesPage.waitForLoad();

    await expect(casesPage.casesTable).toBeVisible();
    await expect(casesPage.caseRows.first()).toContainText('txn-premium-review-001');
    await expect(casesPage.detail).toContainText('HOLD');
    await expect(casesPage.detail).toContainText('txn-premium-review-001');
    await expect(page.locator('[data-testid="case-evaluation-context"]')).toContainText('Event version');
    await expect(page.locator('[data-testid="case-triggered-rules"]')).toContainText('premium_amount_hold');
    await expect(page.locator('[data-testid="case-triggered-rules"]')).toContainText('Premium transfer requires manual review');
    await expect(page.locator('[data-testid="case-event-payload"]')).toContainText('premium-customer-884');
    await expect(casesPage.eventsList).toContainText('created');
    await expect(page.locator('text=evaluation.completed')).toBeVisible();

    await page.locator('[data-testid="case-queue-me"]').click();
    await page.locator('[data-testid="case-priority-min-filter"]').selectOption({ label: '2+' });
    await page.locator('[data-testid="case-decision-state-filter"]').selectOption('rescored_neutral');
    await page.locator('[data-testid="case-created-from-filter"]').fill('2026-07-05');
    await page.locator('[data-testid="case-created-from-filter"]').dispatchEvent('change');
    await page.locator('[data-testid="case-updated-to-filter"]').fill('2026-07-06');
    await page.locator('[data-testid="case-updated-to-filter"]').dispatchEvent('change');
    await expect.poll(() => {
      const lastUrl = caseListUrls.at(-1);
      if (!lastUrl) {
        return false;
      }
      const params = new URL(lastUrl).searchParams;
      return (
        params.get('assigned_to') === 'me' &&
        params.get('status') === 'open' &&
        params.get('priority_min') === '2' &&
        params.get('decision_state') === 'rescored_neutral' &&
        params.get('created_from') === '2026-07-05' &&
        params.get('updated_to') === '2026-07-06'
      );
    }).toBeTruthy();

    await page.locator('[data-testid="case-claim-button"]').click();
    await expect(page.locator('text=Case assignment updated.')).toBeVisible();
    await page.locator('[data-testid="case-note"]').fill('Customer confirmed this transfer was expected.');
    await page.locator('[data-testid="case-add-note-button"]').click();
    await expect(page.locator('text=Case note added.')).toBeVisible();
    await page.locator('[data-testid="case-resolution-disposition"]').selectOption('false_positive');
    await page.locator('[data-testid="case-resolution-action"]').selectOption('release_transaction');
    await casesPage.resolutionNote.fill('Verified customer profile and cleared case.');
    await casesPage.resolveButton.click();

    await expect(page.locator('text=Case resolved.')).toBeVisible();
  });

  test('requires case view permission', async ({ page }) => {
    await mockAuthMe(page, ['view_rules']);

    await page.goto('/cases');

    await expect(page).toHaveURL(/\/access-denied/);
    await expect(page.locator('text=View cases')).toBeVisible();
  });
});
