import { Locator, Page } from '@playwright/test';

export class AccessDeniedPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly requestedPath: Locator;
  readonly requiredPermissionBadges: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.requestedPath = page.locator('text=Requested path').locator('..');
    this.requiredPermissionBadges = page.locator('.bg-blue-50');
  }
}
