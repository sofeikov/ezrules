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
  resolved_by_user_id: null,
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

    await page.route('**/api/v2/cases?**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ cases: [caseItem], total: 1 }),
      });
    });
    await page.route('**/api/v2/cases/42', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          case: caseItem,
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
    await expect(casesPage.eventsList).toContainText('created');
    await expect(page.locator('text=evaluation.completed')).toBeVisible();

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
