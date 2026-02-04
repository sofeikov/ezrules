import { test, expect } from '@playwright/test';
import { OutcomesPage } from '../pages/outcomes.page';

/**
 * E2E tests for the Outcomes management page.
 */
test.describe('Outcomes Page', () => {
  let outcomesPage: OutcomesPage;

  test.beforeEach(async ({ page }) => {
    outcomesPage = new OutcomesPage(page);
  });

  test.describe('Page Structure', () => {
    test('should load the outcomes page successfully', async ({ page }) => {
      await outcomesPage.goto();
      await expect(page).toHaveURL(/.*outcomes/);
    });

    test('should display the correct heading', async () => {
      await outcomesPage.goto();
      await expect(outcomesPage.heading).toHaveText('Outcomes');
    });

    test('should display the page description', async ({ page }) => {
      await outcomesPage.goto();
      const description = page.locator('text=Manage allowed outcomes for business rules');
      await expect(description).toBeVisible();
    });

    test('should be reachable from sidebar navigation', async ({ page }) => {
      await page.goto('/rules');
      const outcomesLink = page.locator('a:has-text("Outcomes")');
      await expect(outcomesLink).toBeVisible();
      await outcomesLink.click();
      await expect(page).toHaveURL(/.*outcomes/);
      await expect(outcomesPage.heading).toHaveText('Outcomes');
    });
  });

  test.describe('Outcomes List', () => {
    test('should display existing outcomes', async () => {
      await outcomesPage.goto();
      await outcomesPage.waitForOutcomesToLoad();

      const count = await outcomesPage.getOutcomeCount();
      expect(count).toBeGreaterThan(0);
    });

    test('should show default outcomes (RELEASE, HOLD, CANCEL)', async () => {
      await outcomesPage.goto();
      await outcomesPage.waitForOutcomesToLoad();

      for (const outcome of ['RELEASE', 'HOLD', 'CANCEL']) {
        await expect(await outcomesPage.hasOutcome(outcome)).toBe(true);
      }
    });

    test('should show outcome count summary', async () => {
      await outcomesPage.goto();
      await outcomesPage.waitForOutcomesToLoad();

      await expect(outcomesPage.outcomeCountText).toBeVisible();
    });

    test('should show Delete button for each outcome', async ({ page }) => {
      await outcomesPage.goto();
      await outcomesPage.waitForOutcomesToLoad();

      const count = await outcomesPage.getOutcomeCount();
      const deleteButtons = page.locator('button:has-text("Delete")');
      await expect(deleteButtons).toHaveCount(count);
    });
  });

  test.describe('Create Outcome', () => {
    test('should have the outcome input and Add Outcome button', async () => {
      await outcomesPage.goto();
      await outcomesPage.waitForOutcomesToLoad();

      await expect(outcomesPage.outcomeInput).toBeVisible();
      await expect(outcomesPage.addOutcomeButton).toBeVisible();
    });

    test('should create a new outcome and display it in the list', async ({ page }) => {
      await outcomesPage.goto();
      await outcomesPage.waitForOutcomesToLoad();

      const uniqueOutcome = `E2ETEST${Date.now()}`;

      await outcomesPage.addOutcome(uniqueOutcome);

      // Wait for the list to refresh and show the new outcome (uppercased)
      const upperOutcome = uniqueOutcome.toUpperCase();
      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('ul li');
          return Array.from(items).some(item => item.textContent?.includes(name));
        },
        upperOutcome,
        { timeout: 5000 }
      );

      await expect(await outcomesPage.hasOutcome(upperOutcome)).toBe(true);

      // Cleanup: delete the outcome we created
      page.on('dialog', dialog => dialog.accept());
      await outcomesPage.clickDelete(upperOutcome);
      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('ul li');
          return !Array.from(items).some(item => item.textContent?.includes(name));
        },
        upperOutcome,
        { timeout: 5000 }
      );
    });

    test('should show error for duplicate outcome', async ({ page }) => {
      await outcomesPage.goto();
      await outcomesPage.waitForOutcomesToLoad();

      // RELEASE is a default outcome — try to add it again
      await outcomesPage.addOutcome('RELEASE');

      // Should show an error about duplicate
      const errorText = page.locator('text=/already exists/i');
      await expect(errorText).toBeVisible();
    });
  });

  test.describe('Delete Outcome', () => {
    test('should delete an outcome after confirmation', async ({ page }) => {
      await outcomesPage.goto();
      await outcomesPage.waitForOutcomesToLoad();

      // First create an outcome to delete
      const uniqueOutcome = `DELTEST${Date.now()}`;
      await outcomesPage.addOutcome(uniqueOutcome);
      const upperOutcome = uniqueOutcome.toUpperCase();

      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('ul li');
          return Array.from(items).some(item => item.textContent?.includes(name));
        },
        upperOutcome,
        { timeout: 5000 }
      );

      // Accept the confirmation dialog
      page.on('dialog', dialog => dialog.accept());

      const countBefore = await outcomesPage.getOutcomeCount();
      await outcomesPage.clickDelete(upperOutcome);

      // Wait for the outcome to disappear
      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('ul li');
          return !Array.from(items).some(item => item.textContent?.includes(name));
        },
        upperOutcome,
        { timeout: 5000 }
      );

      const countAfter = await outcomesPage.getOutcomeCount();
      expect(countAfter).toBe(countBefore - 1);
    });

    test('should not delete an outcome when confirmation is dismissed', async ({ page }) => {
      await outcomesPage.goto();
      await outcomesPage.waitForOutcomesToLoad();

      const countBefore = await outcomesPage.getOutcomeCount();

      // Dismiss the confirmation dialog
      page.on('dialog', dialog => dialog.dismiss());

      // Click delete on the first outcome
      const firstDeleteButton = page.locator('button:has-text("Delete")').first();
      await firstDeleteButton.click();

      // Wait briefly and check count is unchanged
      await page.waitForTimeout(500);
      const countAfter = await outcomesPage.getOutcomeCount();
      expect(countAfter).toBe(countBefore);
    });
  });
});
