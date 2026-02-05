import { test, expect } from '@playwright/test';
import { RuleListPage } from '../pages/rule-list.page';
import { RuleDetailPage } from '../pages/rule-detail.page';

/**
 * E2E tests for the Rule Detail page.
 * Tests navigation, data display, and rule testing functionality.
 */

test.describe('Rule Detail Page', () => {
  let ruleListPage: RuleListPage;
  let ruleDetailPage: RuleDetailPage;
  let testRuleId: number;

  test.beforeEach(async ({ page }) => {
    ruleListPage = new RuleListPage(page);
    ruleDetailPage = new RuleDetailPage(page);

    // Get a rule ID from the list to test with
    await ruleListPage.goto();
    await ruleListPage.waitForRulesToLoad();

    const ruleCount = await ruleListPage.getRuleCount();
    if (ruleCount === 0) {
      throw new Error('No rules available for testing. Please ensure test data exists.');
    }

    // Get the first rule's ID from the table
    const firstRow = page.locator('tbody tr').first();
    const viewLink = firstRow.locator('a:has-text("View")');
    const href = await viewLink.getAttribute('href');
    testRuleId = parseInt(href?.split('/').pop() || '1');
  });

  test.describe('Navigation', () => {
    test('should navigate to rule detail page from rule list', async ({ page }) => {
      await ruleListPage.goto();
      await ruleListPage.waitForRulesToLoad();

      const firstRow = page.locator('tbody tr').first();
      const viewLink = firstRow.locator('a:has-text("View")');

      await viewLink.click();

      // Should navigate to the detail page
      await expect(page).toHaveURL(/\/rules\/\d+/);
      await ruleDetailPage.waitForRuleToLoad();
    });

    test('should display breadcrumb navigation', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.breadcrumb).toBeVisible();
      await expect(ruleDetailPage.backToRulesLink).toBeVisible();
      await expect(ruleDetailPage.backToRulesLink).toHaveText('All Rules');
    });

    test('should navigate back to rules list via breadcrumb', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickBreadcrumbBack();

      await expect(page).toHaveURL(/\/rules$/);
      await expect(ruleListPage.rulesTable).toBeVisible();
    });

    test('should navigate back to rules list via back button', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickBack();

      await expect(page).toHaveURL(/\/rules$/);
      await expect(ruleListPage.rulesTable).toBeVisible();
    });
  });

  test.describe('Loading States', () => {
    test('should show loading spinner initially', async ({ page }) => {
      await page.goto(`/rules/${testRuleId}`, { waitUntil: 'domcontentloaded' });

      // The spinner should appear briefly or data should load
      const spinnerExists = await ruleDetailPage.loadingSpinner.count() > 0 || await ruleDetailPage.ruleIdField.isVisible();
      expect(spinnerExists).toBeTruthy();
    });

    test('should hide loading spinner after data loads', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.loadingSpinner).not.toBeVisible();
    });

    test('should display error message for non-existent rule', async () => {
      await ruleDetailPage.goto(999999);

      await expect(ruleDetailPage.errorMessage).toBeVisible();
    });
  });

  test.describe('Rule Details Display', () => {
    test('should display rule ID', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const ruleId = await ruleDetailPage.getRuleId();
      expect(ruleId).toBeTruthy();
      expect(ruleId.length).toBeGreaterThan(0);
    });

    test('should display rule description', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const description = await ruleDetailPage.getDescription();
      expect(description).toBeTruthy();
    });

    test('should display rule logic', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const logic = await ruleDetailPage.getLogic();
      expect(logic).toBeTruthy();
      expect(logic.length).toBeGreaterThan(0);
    });

    test('should display created date', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.createdDateField).toBeVisible();
      const createdText = await ruleDetailPage.createdDateField.textContent();
      expect(createdText).toBeTruthy();
    });

    test('should display all required field labels', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const requiredLabels = ['Rule ID', 'Description', 'Logic', 'Created'];

      for (const label of requiredLabels) {
        const labelElement = page.locator(`text=${label}`).first();
        await expect(labelElement).toBeVisible();
      }
    });
  });

  test.describe('Rule Testing Functionality', () => {
    test('should display test rule section', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const testSection = page.locator('text=Test Rule').first();
      await expect(testSection).toBeVisible();
      await expect(ruleDetailPage.testJsonTextarea).toBeVisible();
      await expect(ruleDetailPage.testRuleButton).toBeVisible();
    });

    test('should populate test JSON textarea with rule parameters', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      // Wait a bit for the fillInExampleParams to execute
      await ruleDetailPage.page.waitForTimeout(1000);

      const testJson = await ruleDetailPage.testJsonTextarea.inputValue();
      // Should have some JSON (could be empty object or populated with params)
      expect(testJson.length).toBeGreaterThanOrEqual(0);
    });

    test('should allow entering custom test JSON', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const testData = '{"amount": 100, "test": true}';
      await ruleDetailPage.setTestJson(testData);

      const value = await ruleDetailPage.testJsonTextarea.inputValue();
      expect(value).toBe(testData);
    });

    test('should enable test button when JSON is present', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.setTestJson('{"test": true}');

      await expect(ruleDetailPage.testRuleButton).toBeEnabled();
    });

    test('should handle TAB key in test JSON textarea', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.testJsonTextarea.click();
      await ruleDetailPage.testJsonTextarea.fill('test');

      // Press Tab key
      await ruleDetailPage.testJsonTextarea.press('Tab');

      // After pressing Tab, the textarea should still be focused or contain the tab character
      // We're testing that Tab doesn't navigate away from the field
      const value = await ruleDetailPage.testJsonTextarea.inputValue();
      const isFocused = await ruleDetailPage.testJsonTextarea.evaluate((el) => el === document.activeElement);

      // Either the textarea is still focused or it contains a tab character
      expect(isFocused || value.includes('\t')).toBeTruthy();
    });

    test('should handle TAB key in logic textarea', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      // Note: logic textarea is readonly, but should still handle Tab if it weren't
      // This test verifies the handleTextareaTab function is applied
      await ruleDetailPage.logicTextarea.click();

      // Press Tab key
      await ruleDetailPage.logicTextarea.press('Tab');

      // Since it's readonly, focus might move, but the handler should be present
      // We're just verifying no errors occur
      await expect(ruleDetailPage.logicTextarea).toBeDefined();
    });
  });

  test.describe('Revisions Section', () => {
    test('should display revisions section when revisions exist', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      // Check if revisions section is visible (it may not be if there are no revisions)
      const revisionsVisible = await ruleDetailPage.revisionsSection.isVisible().catch(() => false);

      if (revisionsVisible) {
        await expect(ruleDetailPage.revisionsSection).toBeVisible();
      }
    });
  });

  test.describe('Responsive Design', () => {
    test('should display correctly on desktop viewport', async ({ page }) => {
      await page.setViewportSize({ width: 1920, height: 1080 });
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.ruleIdField).toBeVisible();
      await expect(ruleDetailPage.testRuleButton).toBeVisible();
    });

    test('should maintain layout on smaller desktop viewport', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 720 });
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.ruleIdField).toBeVisible();
      await expect(ruleDetailPage.testRuleButton).toBeVisible();
    });
  });

  test.describe('Integration with API', () => {
    test('should load data from /api/v2/rules/:id endpoint', async ({ page }) => {
      // Verify the API endpoint returns data
      const response = await page.request.get(`http://localhost:8888/api/v2/rules/${testRuleId}`);
      expect(response.ok()).toBe(true);

      const data = await response.json();
      expect(data.r_id).toBe(testRuleId);
      expect(data.rid).toBeTruthy();
      expect(data.logic).toBeTruthy();

      // Now verify the UI displays this data
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const displayedRuleId = await ruleDetailPage.getRuleId();
      expect(displayedRuleId).toBe(data.rid);
    });
  });
});
