import { test, expect } from '../support/fixtures';
import { LabelsPage } from '../pages/labels.page';
import { acceptDialog, dismissDialog } from '../support/dialogs';
import { testResourceName } from '../support/test-data';
import { STATEFUL_TAG, TEST_DATA_TAG } from '../support/tags';

/**
 * E2E tests for the Labels management page.
 */
test.describe(`Labels Page ${STATEFUL_TAG} ${TEST_DATA_TAG}`, () => {
  let labelsPage: LabelsPage;

  test.beforeEach(async ({ page }) => {
    labelsPage = new LabelsPage(page);
  });

  test.describe('Page Structure', () => {
    test('should load the labels page successfully', async ({ page }) => {
      await labelsPage.goto();
      await expect(page).toHaveURL(/.*labels/);
    });

    test('should display the correct heading', async () => {
      await labelsPage.goto();
      await expect(labelsPage.heading).toHaveText('Labels');
    });

    test('should display the page description', async ({ page }) => {
      await labelsPage.goto();
      const description = page.locator('text=Manage labels for transaction categorization and analysis');
      await expect(description).toBeVisible();
    });

    test('should be reachable from sidebar navigation', async ({ page }) => {
      await page.goto('/rules');
      const labelsLink = page.locator('a:has-text("Labels")');
      await expect(labelsLink).toBeVisible();
      await labelsLink.click();
      await expect(page).toHaveURL(/.*labels/);
      await expect(labelsPage.heading).toHaveText('Labels');
    });
  });

  test.describe('Labels List', () => {
    test('should display existing labels', async () => {
      await labelsPage.goto();
      await labelsPage.waitForLabelsToLoad();

      const count = await labelsPage.getLabelCount();
      expect(count).toBeGreaterThan(0);
    });

    test('should show label count summary', async () => {
      await labelsPage.goto();
      await labelsPage.waitForLabelsToLoad();

      await expect(labelsPage.labelCountText).toBeVisible();
    });

    test('should show Delete button for each label', async ({ page }) => {
      await labelsPage.goto();
      await labelsPage.waitForLabelsToLoad();

      const count = await labelsPage.getLabelCount();
      const deleteButtons = page.locator('button:has-text("Delete")');
      await expect(deleteButtons).toHaveCount(count);
    });
  });

  test.describe('Create Label', () => {
    test('should have the label input and Add Label button', async () => {
      await labelsPage.goto();
      await labelsPage.waitForLabelsToLoad();

      await expect(labelsPage.labelInput).toBeVisible();
      await expect(labelsPage.addLabelButton).toBeVisible();
    });

    test('should create a new label and display it in the list', async ({ page }, testInfo) => {
      await labelsPage.goto();
      await labelsPage.waitForLabelsToLoad();

      const uniqueLabel = testResourceName(testInfo, 'E2ETEST', { maxLength: 48, uppercase: true });

      await page.route('**/labels', async (route) => {
        if (route.request().method() === 'POST') {
          await route.continue();
        } else {
          await route.continue();
        }
      });

      await labelsPage.addLabel(uniqueLabel);

      // Wait for the list to refresh and show the new label
      await page.waitForFunction(
        (label: string) => {
          const items = document.querySelectorAll('ul li');
          return Array.from(items).some(item => item.textContent?.includes(label));
        },
        uniqueLabel,
        { timeout: 5000 }
      );

      await expect(await labelsPage.hasLabel(uniqueLabel)).toBe(true);

      // Cleanup: delete the label we created
      await acceptDialog(page, () => labelsPage.clickDelete(uniqueLabel));
      await page.waitForFunction(
        (label: string) => {
          const items = document.querySelectorAll('ul li');
          return !Array.from(items).some(item => item.textContent?.includes(label));
        },
        uniqueLabel,
        { timeout: 5000 }
      );
    });

    test('should show error for duplicate label', async ({ page }) => {
      await labelsPage.goto();
      await labelsPage.waitForLabelsToLoad();

      // Get the first existing label
      const firstLabel = await page.locator('ul li').first().textContent();
      expect(firstLabel).toBeTruthy();

      // Try to add it again — the input will contain whitespace from the li text
      const labelName = firstLabel!.replace('Delete', '').trim();
      await labelsPage.addLabel(labelName);

      // Should show an error about duplicate
      const errorText = page.locator('text=/already exists/i');
      await expect(errorText).toBeVisible();
    });
  });

  test.describe('Delete Label', () => {
    test('should delete a label after confirmation', async ({ page }, testInfo) => {
      await labelsPage.goto();
      await labelsPage.waitForLabelsToLoad();

      // First create a label to delete
      const uniqueLabel = testResourceName(testInfo, 'DELTEST', { maxLength: 48, uppercase: true });
      await labelsPage.addLabel(uniqueLabel);

      await page.waitForFunction(
        (label: string) => {
          const items = document.querySelectorAll('ul li');
          return Array.from(items).some(item => item.textContent?.includes(label));
        },
        uniqueLabel,
        { timeout: 5000 }
      );

      const countBefore = await labelsPage.getLabelCount();
      await acceptDialog(page, () => labelsPage.clickDelete(uniqueLabel));

      // Wait for the label to disappear
      await page.waitForFunction(
        (label: string) => {
          const items = document.querySelectorAll('ul li');
          return !Array.from(items).some(item => item.textContent?.includes(label));
        },
        uniqueLabel,
        { timeout: 5000 }
      );

      const countAfter = await labelsPage.getLabelCount();
      expect(countAfter).toBe(countBefore - 1);
    });

    test('should not delete a label when confirmation is dismissed', async ({ page }) => {
      await labelsPage.goto();
      await labelsPage.waitForLabelsToLoad();

      const countBefore = await labelsPage.getLabelCount();

      const firstDeleteButton = page.locator('button:has-text("Delete")').first();
      await dismissDialog(page, () => firstDeleteButton.click());

      await expect(page.locator('ul li')).toHaveCount(countBefore);
    });
  });

});
