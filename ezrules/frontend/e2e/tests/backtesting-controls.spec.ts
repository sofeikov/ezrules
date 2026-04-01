import { expect, test } from '@playwright/test';
import { BacktestingPage } from '../pages/backtesting.page';
import { RuleDetailPage } from '../pages/rule-detail.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

function nowIso(): string {
  return new Date().toISOString();
}

test.describe('Backtesting Controls', () => {
  let ruleId: number;

  test.beforeEach(async ({ request }) => {
    const response = await request.post(`${API_BASE}/api/v2/rules`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
      data: {
        rid: `E2E_BT_CTRL_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        description: 'E2E test rule for backtesting controls',
        logic: "if $amount > 100:\n\treturn 'HOLD'",
      },
    });
    const payload = await response.json();
    if (!payload.success || !payload.rule?.r_id) {
      throw new Error(`Failed to create test rule: ${JSON.stringify(payload)}`);
    }
    ruleId = payload.rule.r_id;
  });

  test.afterEach(async ({ request }) => {
    if (ruleId) {
      await request.delete(`${API_BASE}/api/v2/rules/${ruleId}`, {
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      });
      ruleId = 0;
    }
  });

  test('shows cancel control for running jobs and updates the badge after cancellation', async ({ page }) => {
    const ruleDetailPage = new RuleDetailPage(page);
    const backtestingPage = new BacktestingPage(page);
    const taskId = `mock-running-${Date.now()}`;
    let queueStatus: 'running' | 'cancelled' = 'running';

    await page.route(`${API_BASE}/api/v2/backtesting/${ruleId}*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: [
            {
              task_id: taskId,
              created_at: nowIso(),
              completed_at: queueStatus === 'cancelled' ? nowIso() : null,
              stored_logic: "return 'HOLD'",
              proposed_logic: "return 'BLOCK'",
              status: queueStatus === 'cancelled' ? 'CANCELLED' : 'PENDING',
              queue_status: queueStatus,
            },
          ],
        }),
      });
    });

    await page.route(`${API_BASE}/api/v2/backtesting/task/${taskId}*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: queueStatus === 'cancelled' ? 'CANCELLED' : 'PENDING',
          queue_status: queueStatus,
          error: queueStatus === 'cancelled' ? 'Backtest cancelled by operator' : null,
        }),
      });
    });

    await page.route(`${API_BASE}/api/v2/backtesting/${taskId}`, async (route) => {
      if (route.request().method() !== 'DELETE') {
        await route.fallback();
        return;
      }

      queueStatus = 'cancelled';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          task_id: taskId,
          message: 'Backtest cancelled',
          queue_status: 'cancelled',
        }),
      });
    });

    await ruleDetailPage.goto(ruleId);
    await ruleDetailPage.waitForRuleToLoad();
    await backtestingPage.waitForBacktestResults();

    await expect(backtestingPage.getCancelButton(0)).toBeVisible();
    await backtestingPage.cancelResult(0);
    await backtestingPage.waitForResultStatus(0, 'Cancelled');
    await expect(backtestingPage.getCancelButton(0)).toHaveCount(0);
    await expect(backtestingPage.getRetryButton(0)).toBeVisible();
  });

  test('shows retry control for failed jobs and refreshes the list after retry', async ({ page }) => {
    const ruleDetailPage = new RuleDetailPage(page);
    const backtestingPage = new BacktestingPage(page);
    const failedTaskId = `mock-failed-${Date.now()}`;
    const retriedTaskId = `mock-retried-${Date.now()}`;
    let history = [
      {
        task_id: failedTaskId,
        created_at: nowIso(),
        completed_at: nowIso(),
        stored_logic: "return 'HOLD'",
        proposed_logic: "return 'BLOCK'",
        status: 'FAILURE',
        queue_status: 'failed',
      },
    ];

    await page.route(`${API_BASE}/api/v2/backtesting/${ruleId}*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ results: history }),
      });
    });

    await page.route(new RegExp(`${API_BASE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/api/v2/backtesting/task/.*`), async (route) => {
      const url = route.request().url();
      if (url.includes(retriedTaskId)) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'SUCCESS',
            queue_status: 'done',
            total_records: 2,
            stored_result: { HOLD: 1 },
            proposed_result: { BLOCK: 2 },
            stored_result_rate: { HOLD: 50.0 },
            proposed_result_rate: { BLOCK: 100.0 },
            created_at: nowIso(),
            completed_at: nowIso(),
          }),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'FAILURE',
          queue_status: 'failed',
          error: 'Backtest task failed',
          created_at: nowIso(),
          completed_at: nowIso(),
        }),
      });
    });

    await page.route(`${API_BASE}/api/v2/backtesting/${failedTaskId}/retry`, async (route) => {
      if (route.request().method() !== 'POST') {
        await route.fallback();
        return;
      }

      history = [
        {
          task_id: retriedTaskId,
          created_at: nowIso(),
          completed_at: nowIso(),
          stored_logic: "return 'HOLD'",
          proposed_logic: "return 'BLOCK'",
          status: 'SUCCESS',
          queue_status: 'done',
        },
        ...history,
      ];

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          task_id: retriedTaskId,
          message: 'Backtest retried',
          queue_status: 'pending',
        }),
      });
    });

    await ruleDetailPage.goto(ruleId);
    await ruleDetailPage.waitForRuleToLoad();
    await backtestingPage.waitForBacktestResults();

    await expect(backtestingPage.getRetryButton(0)).toBeVisible();
    await backtestingPage.retryResult(0);
    await expect(backtestingPage.backtestItems).toHaveCount(2);
    await backtestingPage.waitForResultStatus(0, 'Completed');
  });
});
