import type { Dialog, Page } from '@playwright/test';

async function runWithDialog(page: Page, action: () => Promise<unknown>, handleDialog: (dialog: Dialog) => Promise<void>) {
  await Promise.all([page.waitForEvent('dialog').then(handleDialog), action()]);
}

export async function acceptDialog(page: Page, action: () => Promise<unknown>) {
  await runWithDialog(page, action, dialog => dialog.accept());
}

export async function dismissDialog(page: Page, action: () => Promise<unknown>) {
  await runWithDialog(page, action, dialog => dialog.dismiss());
}
