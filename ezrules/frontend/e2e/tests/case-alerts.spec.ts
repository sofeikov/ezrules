import { expect, Page, test } from '@playwright/test';
import { CasesPage } from '../pages/cases.page';

const caseItem = {
  id: 84,
  transaction_id: 'txn-cancellation-spike-084',
  current_event_version_id: 184,
  current_evaluation_decision_id: 284,
  opened_by_evaluation_decision_id: 284,
  previous_evaluation_decision_id: null,
  resolved_outcome: 'CANCEL',
  previous_resolved_outcome: null,
  status: 'open',
  decision_state: 'current',
  priority: 3,
  assigned_to_user_id: null,
  assigned_to_email: null,
  resolved_by_user_id: null,
  resolved_by_email: null,
  resolution_disposition: null,
  resolution_action: null,
  resolution_note: null,
  resolution_label_id: null,
  reopened_from_case_id: null,
  created_at: '2026-07-10T09:00:00Z',
  updated_at: '2026-07-10T09:00:00Z',
  resolved_at: null,
};

async function mockAuthentication(page: Page) {
  await page.addInitScript(() => localStorage.setItem('ezrules_access_token', 'alert-case-token'));
  await page.route('**/api/v2/auth/me', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      id: 9,
      email: 'fraud.analyst@example.com',
      active: true,
      roles: [],
      permissions: ['view_cases', 'manage_cases'],
      last_login_at: null,
    }),
  }));
}

test('filters the case queue from a spike notification and shows alert evidence', async ({ page }) => {
  await mockAuthentication(page);
  const listUrls: string[] = [];
  await page.route('**/api/v2/cases?**', async route => {
    listUrls.push(route.request().url());
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ cases: [caseItem], total: 1 }) });
  });
  await page.route('**/api/v2/cases/assignees', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ users: [] }),
  }));
  await page.route('**/api/v2/cases/84', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      case: caseItem,
      alerts: [{
        incident_id: 73,
        alert_rule_id: 12,
        alert_rule_name: 'Cancellation volume surge',
        evaluation_decision_id: 284,
        outcome: 'CANCEL',
        severity: 'critical',
        observed_count: 52,
        threshold: 50,
        window_start: '2026-07-10T08:00:00Z',
        window_end: '2026-07-10T09:00:00Z',
        triggered_at: '2026-07-10T09:00:00Z',
      }],
      evaluation: null,
      events: [],
    }),
  }));
  await page.route('**/api/v2/integration-events?**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ events: [], next_cursor: null }),
  }));

  const casesPage = new CasesPage(page);
  await page.goto('/cases?alert_incident_id=73');
  await casesPage.waitForLoad();

  await expect(page.locator('[data-testid="case-alert-evidence"]')).toContainText('Cancellation volume surge');
  await expect(page.locator('[data-testid="case-alert-evidence"]')).toContainText('52 CANCEL decisions; threshold 50');
  expect(listUrls.some(url => new URL(url).searchParams.get('alert_incident_id') === '73')).toBe(true);

  await page.evaluate(() => {
    window.history.pushState({}, '', '/cases?alert_incident_id=74');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect.poll(() => listUrls.some(url => new URL(url).searchParams.get('alert_incident_id') === '74')).toBe(true);
  await page.locator('[data-testid="case-clear-filters"]').click();
  await expect(page).toHaveURL(/\/cases$/);
  await page.reload();
  await expect.poll(() => listUrls.some(url => new URL(url).searchParams.get('alert_incident_id') === null)).toBe(true);

  await page.locator('[data-testid="case-alert-severity-filter"]').selectOption('critical');
  await page.locator('[data-testid="case-alert-rule-filter"]').fill('12');
  await page.locator('[data-testid="case-outcome-filter"]').fill('CANCEL');
  await page.locator('[data-testid="case-alerted-from-filter"]').fill('2026-07-10');
  await page.locator('[data-testid="case-alerted-to-filter"]').fill('2026-07-11');
  await page.locator('[data-testid="case-alert-rule-filter"]').press('Tab');
  await expect.poll(() => listUrls.some(url => {
    const params = new URL(url).searchParams;
    return params.get('alert_severity') === 'critical'
      && params.get('alert_rule_id') === '12'
      && params.get('outcome') === 'CANCEL'
      && params.get('alerted_from') === '2026-07-10'
      && params.get('alerted_to') === '2026-07-11';
  })).toBe(true);
});
