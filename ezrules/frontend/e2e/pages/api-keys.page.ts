import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the API Keys management page.
 */
export class ApiKeysPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly createBtn: Locator;
  readonly createDialog: Locator;
  readonly labelInput: Locator;
  readonly confirmCreateBtn: Locator;
  readonly keyRevealDialog: Locator;
  readonly rawKeyValue: Locator;
  readonly copyKeyBtn: Locator;
  readonly closeRevealBtn: Locator;
  readonly loadingSpinner: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.createBtn = page.locator('[data-testid="create-api-key-btn"]');
    this.createDialog = page.locator('[data-testid="create-dialog"]');
    this.labelInput = page.locator('[data-testid="label-input"]');
    this.confirmCreateBtn = page.locator('[data-testid="confirm-create-btn"]');
    this.keyRevealDialog = page.locator('[data-testid="key-reveal-dialog"]');
    this.rawKeyValue = page.locator('[data-testid="raw-key-value"]');
    this.copyKeyBtn = page.locator('[data-testid="copy-key-btn"]');
    this.closeRevealBtn = page.locator('[data-testid="close-reveal-btn"]');
    this.loadingSpinner = page.locator('.animate-spin');
  }

  async goto() {
    await this.page.goto('/api-keys');
  }

  async waitForLoad() {
    await this.loadingSpinner.waitFor({ state: 'hidden', timeout: 10000 });
  }

  async getKeyCount(): Promise<number> {
    return await this.page.locator('[data-testid="api-key-row"]').count();
  }

  async hasKeyWithLabel(label: string): Promise<boolean> {
    return await this.page
      .locator('[data-testid="api-key-row"]')
      .filter({ hasText: label })
      .isVisible()
      .catch(() => false);
  }

  async createKey(label: string): Promise<string> {
    await this.createBtn.click();
    await this.createDialog.waitFor({ state: 'visible' });
    await this.labelInput.fill(label);
    await this.confirmCreateBtn.click();
    await this.keyRevealDialog.waitFor({ state: 'visible' });
    const rawKey = await this.rawKeyValue.textContent() ?? '';
    await this.closeRevealBtn.click();
    await this.keyRevealDialog.waitFor({ state: 'hidden' });
    return rawKey.trim();
  }

  async revokeKeyByLabel(label: string) {
    const row = this.page.locator('[data-testid="api-key-row"]').filter({ hasText: label });
    this.page.on('dialog', d => d.accept());
    await row.locator('[data-testid="revoke-btn"]').click();
  }
}
