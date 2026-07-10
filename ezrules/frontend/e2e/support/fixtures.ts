import { test as base, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { getApiBaseUrl } from './config';

type DiagnosticEntry = {
  type: string;
  message?: string;
  url?: string;
  method?: string;
  status?: number;
  body?: string;
  location?: unknown;
  failure?: string | null;
};

function truncate(value: string, maxLength = 4_000): string {
  return value.length > maxLength ? `${value.slice(0, maxLength)}... [truncated]` : value;
}

function registerDiagnostics(page: Page) {
  const apiBase = getApiBaseUrl();
  const entries: DiagnosticEntry[] = [];
  const pending: Promise<void>[] = [];

  page.on('console', message => {
    if (message.type() !== 'error') {
      return;
    }
    entries.push({
      type: 'console-error',
      message: message.text(),
      location: message.location(),
    });
  });

  page.on('pageerror', error => {
    entries.push({
      type: 'page-error',
      message: error.stack ?? error.message,
    });
  });

  page.on('requestfailed', request => {
    entries.push({
      type: 'request-failed',
      method: request.method(),
      url: request.url(),
      failure: request.failure()?.errorText ?? null,
    });
  });

  page.on('response', response => {
    const isApiResponse = response.url().startsWith(apiBase) || response.url().includes('/api/v2/');
    if (!isApiResponse || response.status() < 400) {
      return;
    }

    const task = response.text()
      .then(body => {
        entries.push({
          type: 'http-error',
          method: response.request().method(),
          url: response.url(),
          status: response.status(),
          body: truncate(body),
        });
      })
      .catch(error => {
        entries.push({
          type: 'http-error',
          method: response.request().method(),
          url: response.url(),
          status: response.status(),
          body: `[body unavailable: ${String(error)}]`,
        });
      });
    pending.push(task);
  });

  return async () => {
    await Promise.allSettled(pending);
    return entries;
  };
}

export const test = base.extend<{ page: Page }>({
  page: async ({ page }, use, testInfo) => {
    const collectDiagnostics = registerDiagnostics(page);
    await use(page);

    const diagnostics = await collectDiagnostics();
    if (testInfo.status !== testInfo.expectedStatus && diagnostics.length > 0) {
      await testInfo.attach('e2e-diagnostics.json', {
        body: JSON.stringify(diagnostics, null, 2),
        contentType: 'application/json',
      });
    }
  },
});

export { expect };
