import type {
  APIRequestContext,
  APIResponse,
  TestInfo,
} from '@playwright/test';
import { CasesPage } from '../pages/cases.page';
import { DashboardPage } from '../pages/dashboard.page';
import {
  createRule,
  deleteRuleById,
  expectApiOk,
  promoteRule,
} from '../support/api-helpers';
import { getApiBaseUrl, getAuthToken } from '../support/config';
import { expect, test } from '../support/fixtures';
import { testResourceName } from '../support/test-data';

const API_BASE = getApiBaseUrl();

type ApiKey = {
  gid: string;
  raw_key: string;
};

type AlertRule = {
  id: number;
};

type AlertIncident = {
  id: number;
  alert_rule_id: number;
  observed_count: number;
  status: string;
};

type InAppNotification = {
  id: number;
  source_id: number;
  title: string;
};

type EvaluationResponse = {
  evaluation_status: string;
  resolved_outcome: string | null;
};

type CaseItem = {
  transaction_id: string;
};

function authHeaders(): { Authorization: string } {
  return { Authorization: `Bearer ${getAuthToken()}` };
}

async function jsonResponse<T>(
  response: APIResponse,
  context: string,
): Promise<T> {
  await expectApiOk(response, context);
  return (await response.json()) as T;
}

async function createOutcome(
  request: APIRequestContext,
  outcome: string,
): Promise<void> {
  const response = await request.post(`${API_BASE}/api/v2/outcomes`, {
    headers: authHeaders(),
    data: { outcome_name: outcome },
  });
  const body = await jsonResponse<{ success: boolean; error?: string }>(
    response,
    `Create outcome ${outcome}`,
  );
  if (!body.success) {
    throw new Error(
      `Create outcome ${outcome} was unsuccessful: ${body.error ?? 'unknown error'}`,
    );
  }
}

async function createApiKey(
  request: APIRequestContext,
  label: string,
): Promise<ApiKey> {
  const response = await request.post(`${API_BASE}/api/v2/api-keys`, {
    headers: authHeaders(),
    data: { label },
  });
  return await jsonResponse<ApiKey>(response, `Create API key ${label}`);
}

async function createAlertRule(
  request: APIRequestContext,
  name: string,
  outcome: string,
): Promise<AlertRule> {
  const response = await request.post(`${API_BASE}/api/v2/alerts/rules`, {
    headers: authHeaders(),
    data: {
      name,
      outcome,
      threshold: 1,
      window_seconds: 60,
      cooldown_seconds: 300,
      enabled: true,
    },
  });
  const body = await jsonResponse<{ success: boolean; rule?: AlertRule }>(
    response,
    `Create alert rule ${name}`,
  );
  if (!body.success || !body.rule) {
    throw new Error(
      `Create alert rule ${name} returned an unsuccessful response`,
    );
  }
  return body.rule;
}

async function evaluate(
  request: APIRequestContext,
  apiKey: string,
  transactionId: string,
  marker: string,
  effectiveAt: number,
): Promise<EvaluationResponse> {
  const response = await request.post(`${API_BASE}/api/v2/evaluate`, {
    headers: { 'X-API-Key': apiKey },
    data: {
      transaction_id: transactionId,
      effective_at: effectiveAt,
      event_data: {
        alert_probe: marker,
        amount: 50,
        currency: 'USD',
        txn_type: 'card_purchase',
        channel: 'web',
        customer_id: `customer-${transactionId}`,
        customer_country: 'US',
        billing_country: 'US',
        shipping_country: 'US',
        ip_country: 'US',
        merchant_id: `merchant-${transactionId}`,
        merchant_category: 'groceries',
        merchant_country: 'US',
        email_domain: 'example.com',
        account_age_days: 400,
        email_age_days: 400,
        customer_avg_amount_30d: 50,
        customer_std_amount_30d: 10,
        prior_chargebacks_180d: 0,
        manual_review_hits_30d: 0,
        decline_count_24h: 0,
        txn_velocity_10m: 1,
        txn_velocity_1h: 1,
        unique_cards_24h: 1,
        device_age_days: 400,
        device_trust_score: 95,
        has_3ds: 1,
        card_present: 1,
        is_guest_checkout: 0,
        password_reset_age_hours: 720,
        distance_from_home_km: 5,
        ip_proxy_score: 0,
        beneficiary_country: 'US',
        beneficiary_age_days: 400,
        local_hour: 12,
      },
    },
  });
  return await jsonResponse<EvaluationResponse>(
    response,
    `Evaluate transaction ${transactionId}`,
  );
}

async function getMatchingIncident(
  request: APIRequestContext,
  alertRuleId: number,
): Promise<AlertIncident | undefined> {
  const response = await request.get(
    `${API_BASE}/api/v2/alerts/incidents?limit=200`,
    {
      headers: authHeaders(),
    },
  );
  const body = await jsonResponse<{ incidents: AlertIncident[] }>(
    response,
    'List alert incidents',
  );
  return body.incidents.find(
    (incident) => incident.alert_rule_id === alertRuleId,
  );
}

async function getIncidentNotifications(
  request: APIRequestContext,
  incidentId: number,
): Promise<InAppNotification[]> {
  const response = await request.get(
    `${API_BASE}/api/v2/notifications?limit=100`,
    {
      headers: authHeaders(),
    },
  );
  const body = await jsonResponse<{ notifications: InAppNotification[] }>(
    response,
    'List notifications',
  );
  return body.notifications.filter(
    (notification) => notification.source_id === incidentId,
  );
}

async function getCasesForIncident(
  request: APIRequestContext,
  incidentId: number,
): Promise<CaseItem[]> {
  const response = await request.get(
    `${API_BASE}/api/v2/cases?alert_incident_id=${incidentId}&limit=200`,
    { headers: authHeaders() },
  );
  const body = await jsonResponse<{ cases: CaseItem[] }>(
    response,
    `List cases for incident ${incidentId}`,
  );
  return body.cases;
}

async function getUnreadCount(request: APIRequestContext): Promise<number> {
  const response = await request.get(
    `${API_BASE}/api/v2/notifications/unread-count`,
    {
      headers: authHeaders(),
    },
  );
  const body = await jsonResponse<{ unread_count: number }>(
    response,
    'Get unread notification count',
  );
  return body.unread_count;
}

function runToken(testInfo: TestInfo): string {
  return testResourceName(
    testInfo,
    `live_${Date.now()}_${testInfo.workerIndex}`,
    {
      maxLength: 48,
    },
  );
}

test.describe('Live traffic alert workflow', () => {
  let alertRuleId: number | null = null;
  let apiKeyGid: string | null = null;
  let notificationId: number | null = null;
  let outcome: string | null = null;
  let ruleId: number | null = null;

  test.afterEach(async ({ request }) => {
    if (alertRuleId !== null) {
      const response = await request.patch(
        `${API_BASE}/api/v2/alerts/rules/${alertRuleId}`,
        {
          headers: authHeaders(),
          data: { enabled: false },
        },
      );
      await expectApiOk(response, `Disable alert rule ${alertRuleId}`);
    }
    if (notificationId !== null) {
      const response = await request.post(
        `${API_BASE}/api/v2/notifications/${notificationId}/read`,
        {
          headers: authHeaders(),
        },
      );
      await expectApiOk(response, `Mark notification ${notificationId} read`);
    }
    if (apiKeyGid !== null) {
      const response = await request.delete(
        `${API_BASE}/api/v2/api-keys/${apiKeyGid}`,
        {
          headers: authHeaders(),
        },
      );
      await expectApiOk(response, `Revoke API key ${apiKeyGid}`);
    }
    if (ruleId !== null) {
      await deleteRuleById(request, ruleId);
    }
    if (outcome !== null) {
      const response = await request.delete(
        `${API_BASE}/api/v2/outcomes/${outcome}`,
        {
          headers: authHeaders(),
        },
      );
      await expectApiOk(response, `Delete outcome ${outcome}`);
    }

    alertRuleId = null;
    apiKeyGid = null;
    notificationId = null;
    outcome = null;
    ruleId = null;
  });

  test('surfaces a live outcome spike and links the analyst to affected cases', async ({
    page,
    request,
  }, testInfo) => {
    const token = runToken(testInfo);
    outcome = testResourceName(testInfo, `E2E_SPIKE_${token}`, {
      maxLength: 120,
      uppercase: true,
    });
    const marker = `marker_${token}`;
    const alertName = `Live spike ${token}`;
    const effectiveAt = Math.floor(Date.now() / 1_000);
    const transactionIds = [
      `alert-live-${token}-1`,
      `alert-live-${token}-2`,
      `alert-live-${token}-3`,
    ];

    await createOutcome(request, outcome);
    const rule = await createRule(request, {
      rid: testResourceName(testInfo, `E2E_ALERT_${token}`, {
        maxLength: 120,
        uppercase: true,
      }),
      description: `Return ${outcome} for the live alert workflow`,
      logic: `if $alert_probe == '${marker}':\n\treturn !${outcome}`,
    });
    ruleId = rule.r_id;
    await promoteRule(request, ruleId);

    const alertRule = await createAlertRule(request, alertName, outcome);
    alertRuleId = alertRule.id;

    const apiKey = await createApiKey(request, `alert-live-${token}`);
    apiKeyGid = apiKey.gid;

    const baselineUnreadCount = await getUnreadCount(request);
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.waitForPageToLoad();
    const unreadBadge = page.getByTestId('notification-unread-count');
    if (baselineUnreadCount === 0) {
      await expect(unreadBadge).toHaveCount(0);
    } else {
      await expect(unreadBadge).toHaveText(
        baselineUnreadCount > 99 ? '99+' : String(baselineUnreadCount),
      );
    }

    const firstEvaluation = await evaluate(
      request,
      apiKey.raw_key,
      transactionIds[0],
      marker,
      effectiveAt,
    );
    expect(firstEvaluation.resolved_outcome).toBe(outcome);

    const secondEvaluation = await evaluate(
      request,
      apiKey.raw_key,
      transactionIds[1],
      marker,
      effectiveAt,
    );
    expect(secondEvaluation.resolved_outcome).toBe(outcome);

    await expect
      .poll(
        async () =>
          (await getMatchingIncident(request, alertRule.id))?.observed_count ??
          null,
        {
          message:
            'the real evaluation path should create one threshold-crossing incident',
          timeout: 20_000,
          intervals: [250, 500, 1_000],
        },
      )
      .toBe(2);

    const incident = await getMatchingIncident(request, alertRule.id);
    expect(incident).toBeDefined();
    notificationId = null;
    await expect
      .poll(
        async () => {
          const notifications = await getIncidentNotifications(
            request,
            incident!.id,
          );
          notificationId = notifications[0]?.id ?? null;
          return notifications.length;
        },
        {
          message:
            'the threshold-crossing incident should create exactly one notification',
          timeout: 20_000,
          intervals: [250, 500, 1_000],
        },
      )
      .toBe(1);

    await expect
      .poll(() => getUnreadCount(request), {
        message: 'the notification API should expose the newly unread incident',
        timeout: 20_000,
        intervals: [250, 500, 1_000],
      })
      .toBe(baselineUnreadCount + 1);

    await expect(
      unreadBadge,
      'an analyst already on the dashboard should see the live critical notification without refreshing',
    ).toHaveText(
      baselineUnreadCount + 1 > 99 ? '99+' : String(baselineUnreadCount + 1),
      { timeout: 10_000 },
    );

    await page.getByTestId('notification-bell').click();
    const notificationButton = page
      .getByTestId('notification-menu')
      .getByRole('button')
      .filter({ hasText: `${outcome} spike detected` });
    await expect(notificationButton).toHaveCount(1);
    await notificationButton.click();
    await expect(page).toHaveURL(
      new RegExp(`/cases\\?alert_incident_id=${incident!.id}$`),
    );

    const casesPage = new CasesPage(page);
    await casesPage.waitForLoad();
    await expect(casesPage.caseRows).toHaveCount(2);
    for (const transactionId of transactionIds.slice(0, 2)) {
      await expect(
        casesPage.caseRows.filter({ hasText: transactionId }),
      ).toHaveCount(1);
    }
    await casesPage.caseRows.filter({ hasText: transactionIds[0] }).click();
    await expect(page.getByTestId('case-alert-evidence')).toContainText(
      alertName,
    );
    await expect(page.getByTestId('case-alert-evidence')).toContainText(
      `2 ${outcome} decisions; threshold 1`,
    );

    const duplicateEvaluation = await evaluate(
      request,
      apiKey.raw_key,
      transactionIds[1],
      marker,
      effectiveAt,
    );
    expect(duplicateEvaluation.evaluation_status).toBe('duplicate');
    await expect
      .poll(
        async () =>
          (await getMatchingIncident(request, alertRule.id))?.observed_count,
      )
      .toBe(2);
    await expect
      .poll(
        async () =>
          (await getIncidentNotifications(request, incident!.id)).length,
      )
      .toBe(1);
    await expect
      .poll(
        async () => (await getCasesForIncident(request, incident!.id)).length,
      )
      .toBe(2);

    const thirdEvaluation = await evaluate(
      request,
      apiKey.raw_key,
      transactionIds[2],
      marker,
      effectiveAt,
    );
    expect(thirdEvaluation.resolved_outcome).toBe(outcome);
    await expect
      .poll(
        async () =>
          (await getMatchingIncident(request, alertRule.id))?.observed_count,
        {
          message:
            'cooldown should update the existing incident instead of creating another one',
          timeout: 20_000,
          intervals: [250, 500, 1_000],
        },
      )
      .toBe(3);
    await expect
      .poll(
        async () =>
          (await getIncidentNotifications(request, incident!.id)).length,
      )
      .toBe(1);
    await expect
      .poll(async () =>
        (await getCasesForIncident(request, incident!.id))
          .map((item) => item.transaction_id)
          .sort(),
      )
      .toEqual([...transactionIds].sort());

    await page.goto('/alerts');
    const incidentsSection = page.locator('section').filter({
      has: page.getByRole('heading', { name: 'Incidents' }),
    });
    const incidentRow = incidentsSection
      .locator('li')
      .filter({ hasText: outcome });
    await expect(incidentRow).toContainText('3 observed, threshold 1.');
    await incidentRow.getByRole('button', { name: 'Acknowledge' }).click();
    await expect(incidentRow).toContainText('acknowledged');

    await page.reload();
    await expect(
      incidentsSection.locator('li').filter({ hasText: outcome }),
    ).toContainText('acknowledged');
  });
});
