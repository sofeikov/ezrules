import { test, expect } from '@playwright/test';
import { ApiKeysPage } from '../pages/api-keys.page';

test.describe('API Keys Page', () => {
  let apiKeysPage: ApiKeysPage;

  test.beforeEach(async ({ page }) => {
    apiKeysPage = new ApiKeysPage(page);
  });

  test.describe('Page Structure', () => {
    test('should load the API Keys page successfully', async ({ page }) => {
      await apiKeysPage.goto();
      await apiKeysPage.waitForLoad();
      await expect(page).toHaveURL(/.*api-keys/);
    });

    test('should display the correct heading', async () => {
      await apiKeysPage.goto();
      await expect(apiKeysPage.heading).toHaveText('API Keys');
    });

    test('should be reachable from sidebar navigation', async ({ page }) => {
      await page.goto('/dashboard');
      const link = page.locator('a:has-text("API Keys")');
      await expect(link).toBeVisible();
      await link.click();
      await expect(page).toHaveURL(/.*api-keys/);
    });

    test('should show the Create API Key button', async () => {
      await apiKeysPage.goto();
      await expect(apiKeysPage.createBtn).toBeVisible();
    });

    test('should show the Active Keys section', async ({ page }) => {
      await apiKeysPage.goto();
      await apiKeysPage.waitForLoad();
      await expect(page.locator('h2:has-text("Active Keys")')).toBeVisible();
    });
  });

  test.describe('Create API Key', () => {
    test('should open the create dialog when button is clicked', async () => {
      await apiKeysPage.goto();
      await apiKeysPage.createBtn.click();
      await expect(apiKeysPage.createDialog).toBeVisible();
      await expect(apiKeysPage.labelInput).toBeVisible();
      await expect(apiKeysPage.confirmCreateBtn).toBeVisible();
    });

    test('should close dialog on cancel', async ({ page }) => {
      await apiKeysPage.goto();
      await apiKeysPage.createBtn.click();
      await expect(apiKeysPage.createDialog).toBeVisible();
      await page.locator('[data-testid="create-dialog"] button:has-text("Cancel")').click();
      await expect(apiKeysPage.createDialog).not.toBeVisible();
    });

    test('should create a key and show the raw key once', async ({ page }) => {
      await apiKeysPage.goto();
      await apiKeysPage.waitForLoad();

      const label = `e2e-key-${Date.now()}`;
      await apiKeysPage.createBtn.click();
      await apiKeysPage.labelInput.fill(label);
      await apiKeysPage.confirmCreateBtn.click();

      // Key reveal dialog should appear
      await expect(apiKeysPage.keyRevealDialog).toBeVisible();
      const rawKey = await apiKeysPage.rawKeyValue.textContent();
      expect(rawKey?.trim()).toMatch(/^ezrk_[0-9a-f]{64}$/);

      // Warning text about one-time display
      await expect(page.locator('text=not')).toBeVisible();

      // Copy button should be visible
      await expect(apiKeysPage.copyKeyBtn).toBeVisible();

      // Close the dialog
      await apiKeysPage.closeRevealBtn.click();
      await expect(apiKeysPage.keyRevealDialog).not.toBeVisible();

      // Key should now appear in the table
      await expect(page.locator('[data-testid="api-key-row"]').filter({ hasText: label })).toBeVisible();
    });

    test('confirm button should be disabled when label is empty', async () => {
      await apiKeysPage.goto();
      await apiKeysPage.createBtn.click();
      await apiKeysPage.labelInput.fill('');
      await expect(apiKeysPage.confirmCreateBtn).toBeDisabled();
    });
  });

  test.describe('Revoke API Key', () => {
    test('should revoke a key and remove it from the list', async ({ page }) => {
      await apiKeysPage.goto();
      await apiKeysPage.waitForLoad();

      const label = `e2e-revoke-${Date.now()}`;
      await apiKeysPage.createKey(label);

      // Key should be in the list
      await expect(page.locator('[data-testid="api-key-row"]').filter({ hasText: label })).toBeVisible();

      const initialCount = await apiKeysPage.getKeyCount();

      // Revoke it
      page.on('dialog', d => d.accept());
      const row = page.locator('[data-testid="api-key-row"]').filter({ hasText: label });
      await row.locator('[data-testid="revoke-btn"]').click();

      // Row should disappear
      await expect(page.locator('[data-testid="api-key-row"]').filter({ hasText: label })).not.toBeVisible();
      expect(await apiKeysPage.getKeyCount()).toBe(initialCount - 1);
    });
  });
});
