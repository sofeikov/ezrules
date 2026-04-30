import { expect, test } from '@playwright/test';
import { EventTesterPage } from '../pages/event-tester.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

test.describe('Event Tester Page', () => {
  let eventTesterPage: EventTesterPage;

  test.beforeEach(async ({ page }) => {
    eventTesterPage = new EventTesterPage(page);
  });

  test('should load the event tester page successfully', async ({ page }) => {
    await eventTesterPage.goto();

    await expect(page).toHaveURL(/.*event-tester/);
    await expect(eventTesterPage.heading).toHaveText('Event Tester');
    await expect(eventTesterPage.payloadTextarea).toBeVisible();
    await expect(eventTesterPage.runButton).toBeVisible();
  });

  test('should be reachable from sidebar navigation', async ({ page }) => {
    await page.goto('/rules');

    const eventTesterLink = page.locator('a:has-text("Event Tester")');
    await expect(eventTesterLink).toBeVisible();
    await eventTesterLink.click();

    await expect(page).toHaveURL(/.*event-tester/);
    await expect(eventTesterPage.heading).toHaveText('Event Tester');
  });

  test('should run the stock event payload without missing-field errors', async () => {
    await eventTesterPage.goto();
    await eventTesterPage.runButton.click();

    await expect(eventTesterPage.errorMessage).toBeHidden();
    await expect(eventTesterPage.ledgerState).toHaveText('None');
    await expect(eventTesterPage.resolvedOutcome).not.toHaveText('No result');
  });

  test('should dry-run an event without storing it', async ({ request }) => {
    const eventId = `e2e-dry-run-${Date.now()}`;
    const headers = { Authorization: `Bearer ${getAuthToken()}` };
    const createResponse = await request.post(`${API_BASE}/api/v2/rules`, {
      headers,
      data: {
        rid: `E2E_EVENT_TEST_${Date.now()}`,
        description: 'E2E event tester rule',
        logic: 'return !RELEASE',
        evaluation_lane: 'allowlist',
      },
    });
    expect(createResponse.ok()).toBeTruthy();
    const createdRule = await createResponse.json();
    const ruleId = createdRule.rule.r_id;

    const promoteResponse = await request.post(`${API_BASE}/api/v2/rules/${ruleId}/promote`, { headers });
    expect(promoteResponse.ok()).toBeTruthy();

    try {
      await eventTesterPage.goto();
      await eventTesterPage.runTest(eventId, {
        amount: 15000,
        currency: 'USD',
        customer_country: 'US',
        customer_id: 'e2e_customer',
      });

      await expect(eventTesterPage.ledgerState).toHaveText('None');
      await expect(eventTesterPage.resolvedOutcome).toHaveText('RELEASE');
      await expect(eventTesterPage.ruleResults.filter({ hasText: 'E2E event tester rule' })).toBeVisible();

      const testedEventsResponse = await request.get(`${API_BASE}/api/v2/tested-events?limit=200`, {
        headers,
      });
      expect(testedEventsResponse.ok()).toBeTruthy();
      const testedEvents = await testedEventsResponse.json();
      expect(testedEvents.events.some((event: { event_id: string }) => event.event_id === eventId)).toBe(false);
    } finally {
      await request.delete(`${API_BASE}/api/v2/rules/${ruleId}`, { headers });
    }
  });
});
