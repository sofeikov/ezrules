import type {
  APIRequestContext,
  APIResponse,
  TestInfo,
} from '@playwright/test';
import { RolloutsPage } from '../pages/rollouts.page';
import {
  createRule,
  deleteRuleById,
  expectApiOk,
  promoteRule,
} from '../support/api-helpers';
import { getApiBaseUrl, getAuthToken } from '../support/config';
import { expect, test } from '../support/fixtures';
import {
  deterministicUnixTimestamp,
  testResourceName,
} from '../support/test-data';
import { STATEFUL_TAG, TEST_DATA_TAG } from '../support/tags';

const API_BASE = getApiBaseUrl();

type ApiKey = {
  gid: string;
  raw_key: string;
};

type EvaluationResponse = {
  rule_results: Record<string, string>;
};

type RolloutStats = {
  rules: Array<{
    r_id: number;
    total: number;
    served_candidate: number;
    served_control: number;
  }>;
};

const mockedRollout = {
  r_id: 999_001,
  rid: 'E2E_LIVE_MONITOR',
  description: 'Existing live rollout',
  logic: 'return !HOLD',
  traffic_percent: 50,
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
  expect(body.success, body.error).toBe(true);
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
        rollout_probe: marker,
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

async function getRolloutStats(
  request: APIRequestContext,
): Promise<RolloutStats> {
  const response = await request.get(`${API_BASE}/api/v2/rollouts/stats`, {
    headers: authHeaders(),
  });
  return await jsonResponse<RolloutStats>(response, 'Get rollout stats');
}

function runToken(testInfo: TestInfo): string {
  return testResourceName(
    testInfo,
    `rollout_${Date.now()}_${testInfo.workerIndex}`,
    { maxLength: 48 },
  );
}

test.describe(`Live rollout monitoring ${STATEFUL_TAG} ${TEST_DATA_TAG}`, () => {
  let apiKeyGid: string | null = null;
  let controlOutcome: string | null = null;
  let candidateOutcome: string | null = null;
  let ruleId: number | null = null;

  test.afterEach(async ({ request }) => {
    if (ruleId !== null) {
      const response = await request.delete(
        `${API_BASE}/api/v2/rules/${ruleId}/rollout`,
        { headers: authHeaders() },
      );
      await expectApiOk(response, `Remove rollout for rule ${ruleId}`);
      await deleteRuleById(request, ruleId);
    }
    if (apiKeyGid !== null) {
      const response = await request.delete(
        `${API_BASE}/api/v2/api-keys/${apiKeyGid}`,
        { headers: authHeaders() },
      );
      await expectApiOk(response, `Revoke API key ${apiKeyGid}`);
    }
    for (const outcome of [candidateOutcome, controlOutcome]) {
      if (outcome !== null) {
        const response = await request.delete(
          `${API_BASE}/api/v2/outcomes/${outcome}`,
          { headers: authHeaders() },
        );
        await expectApiOk(response, `Delete outcome ${outcome}`);
      }
    }

    apiKeyGid = null;
    controlOutcome = null;
    candidateOutcome = null;
    ruleId = null;
  });

  test('keeps an open rollout monitor synchronized with live served decisions', async ({
    page,
    request,
  }, testInfo) => {
    const token = runToken(testInfo);
    const marker = `marker_${token}`;
    controlOutcome = testResourceName(testInfo, `CONTROL_${token}`, {
      maxLength: 120,
      uppercase: true,
    });
    candidateOutcome = testResourceName(testInfo, `CANDIDATE_${token}`, {
      maxLength: 120,
      uppercase: true,
    });

    await createOutcome(request, controlOutcome);
    await createOutcome(request, candidateOutcome);
    const rule = await createRule(request, {
      rid: testResourceName(testInfo, `E2E_ROLLOUT_${token}`, {
        maxLength: 120,
        uppercase: true,
      }),
      description: 'Exercise live rollout monitoring',
      logic: `if $rollout_probe == '${marker}':\n\treturn !${controlOutcome}`,
    });
    ruleId = rule.r_id;
    await promoteRule(request, ruleId);

    const deployResponse = await request.post(
      `${API_BASE}/api/v2/rules/${ruleId}/rollout`,
      {
        headers: authHeaders(),
        data: {
          logic: `if $rollout_probe == '${marker}':\n\treturn !${candidateOutcome}`,
          description: 'Candidate for live rollout monitoring',
          traffic_percent: 100,
        },
      },
    );
    await expectApiOk(deployResponse, `Deploy rollout for rule ${ruleId}`);

    const apiKey = await createApiKey(request, `rollout-live-${token}`);
    apiKeyGid = apiKey.gid;

    const rolloutsPage = new RolloutsPage(page);
    await rolloutsPage.goto();
    await rolloutsPage.waitForLoad();
    const rolloutRow = rolloutsPage.rowForRule(rule.rid);
    await expect(rolloutRow).toContainText('0 events compared');

    const evaluation = await evaluate(
      request,
      apiKey.raw_key,
      `rollout-live-${token}`,
      marker,
      deterministicUnixTimestamp(testInfo),
    );
    expect(evaluation.rule_results[String(ruleId)]).toBe(candidateOutcome);

    await expect
      .poll(
        async () => {
          const stats = await getRolloutStats(request);
          return stats.rules.find((item) => item.r_id === ruleId);
        },
        {
          message: 'the backend should record the candidate-served decision',
          timeout: 10_000,
          intervals: [250, 500, 1_000],
        },
      )
      .toMatchObject({
        total: 1,
        served_candidate: 1,
        served_control: 0,
      });

    await expect(
      rolloutRow,
      'an operator monitoring a live rollout should see newly served decisions without manually refreshing',
    ).toContainText('1 events compared', { timeout: 10_000 });
  });

  test('renders rollout configuration without waiting for slow best-effort statistics', async ({ page }) => {
    await page.route('**/api/v2/rollouts/stats', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 5_500));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rules: [{
            r_id: mockedRollout.r_id,
            traffic_percent: mockedRollout.traffic_percent,
            total: 7,
            served_candidate: 4,
            served_control: 3,
            candidate_outcomes: [],
            control_outcomes: [],
          }],
        }),
      });
    });
    await page.route('**/api/v2/rollouts', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ rules: [mockedRollout], version: 1 }),
      });
    });

    const rolloutsPage = new RolloutsPage(page);
    await rolloutsPage.goto();
    const rolloutRow = rolloutsPage.rowForRule(mockedRollout.rid);
    await expect(rolloutRow).toBeVisible({ timeout: 2_000 });
    await expect(rolloutRow).toContainText('7 events compared', {
      timeout: 7_000,
    });
  });

  test('keeps the last rollout data visible when a background refresh fails', async ({ page }) => {
    let configRequests = 0;
    await page.route('**/api/v2/rollouts/stats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rules: [{
            r_id: mockedRollout.r_id,
            traffic_percent: mockedRollout.traffic_percent,
            total: 0,
            served_candidate: 0,
            served_control: 0,
            candidate_outcomes: [],
            control_outcomes: [],
          }],
        }),
      });
    });
    await page.route('**/api/v2/rollouts', async (route) => {
      configRequests += 1;
      if (configRequests === 1) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ rules: [mockedRollout], version: 1 }),
        });
        return;
      }
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Temporarily unavailable' }),
      });
    });

    const rolloutsPage = new RolloutsPage(page);
    await rolloutsPage.goto();
    const rolloutRow = rolloutsPage.rowForRule(mockedRollout.rid);
    await expect(rolloutRow).toBeVisible();
    await expect
      .poll(() => configRequests, {
        message: 'the background rollout refresh should run',
        timeout: 7_000,
      })
      .toBeGreaterThan(1);
    await expect(page.getByTestId('rollout-refresh-warning')).toContainText(
      'Rollout configuration could not be refreshed. Showing the last known data.',
    );
    await expect(rolloutRow).toBeVisible();
  });
});
