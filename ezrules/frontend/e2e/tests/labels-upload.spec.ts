import { APIRequestContext, expect, test } from '@playwright/test';
import { LabelsPage } from '../pages/labels.page';
import { getApiBaseUrl, getAuthToken } from '../support/config';

const API_BASE = getApiBaseUrl();

function authHeaders() {
  return { Authorization: `Bearer ${getAuthToken()}` };
}

async function createLabel(request: APIRequestContext, labelName: string) {
  const response = await request.post(`${API_BASE}/api/v2/labels`, {
    headers: authHeaders(),
    data: { label_name: labelName },
  });
  const payload = await response.json();
  if (response.status() !== 201 || !payload.success) {
    throw new Error(`Failed to create label ${labelName}: ${JSON.stringify(payload)}`);
  }
}

async function createEvaluatedEvent(request: APIRequestContext, eventId: string) {
  const response = await request.post(`${API_BASE}/api/v2/evaluate`, {
    headers: authHeaders(),
    data: {
      event_id: eventId,
      event_timestamp: Math.floor(Date.now() / 1000),
      event_data: {
        amount: 125,
        currency: 'USD',
        customer_id: `cust-${eventId}`,
      },
    },
  });
  if (!response.ok()) {
    throw new Error(`Failed to create evaluated event ${eventId}: ${response.status()} ${await response.text()}`);
  }
}

test.describe('Labels CSV Upload', () => {
  test('should upload a valid CSV and show a success summary', async ({ page, request }) => {
    const labelsPage = new LabelsPage(page);
    const suffix = Date.now();
    const labelName = `E2E_CSV_${suffix}`;
    const eventId = `e2e-csv-event-${suffix}`;

    await createLabel(request, labelName);
    await createEvaluatedEvent(request, eventId);

    await labelsPage.goto();
    await labelsPage.waitForLabelsToLoad();
    await labelsPage.uploadCsvContent(`${eventId},${labelName}\n`);

    await expect(labelsPage.uploadResult).toBeVisible();
    await expect(labelsPage.uploadSummary).toHaveText('1 row processed');
    await expect(labelsPage.uploadResult).toContainText('1 applied');
    await expect(labelsPage.uploadResult).toContainText('0 failed');
  });

  test('should show row-level errors for invalid CSV uploads', async ({ page, request }) => {
    const labelsPage = new LabelsPage(page);
    const suffix = Date.now();
    const labelName = `E2E_CSV_ERR_${suffix}`;
    const missingEventId = `missing-event-${suffix}`;

    await createLabel(request, labelName);

    await labelsPage.goto();
    await labelsPage.waitForLabelsToLoad();
    await labelsPage.uploadCsvContent(`${missingEventId},${labelName}\n`);

    await expect(labelsPage.uploadResult).toBeVisible();
    await expect(labelsPage.uploadSummary).toHaveText('1 row processed');
    await expect(labelsPage.uploadResult).toContainText('0 applied');
    await expect(labelsPage.uploadResult).toContainText('1 failed');
    await expect(labelsPage.uploadErrors).toContainText(`Event with id '${missingEventId}' not found`);
  });
});
