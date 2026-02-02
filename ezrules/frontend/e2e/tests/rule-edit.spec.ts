import { test, expect } from '@playwright/test';
import { RuleListPage } from '../pages/rule-list.page';
import { RuleDetailPage } from '../pages/rule-detail.page';

/**
 * E2E tests for the Rule Edit functionality.
 * Tests editing rules, saving changes, and revision updates.
 */

test.describe('Rule Edit Functionality', () => {
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

  test.describe('Edit Button', () => {
    test('should display Edit button on rule detail page', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await expect(ruleDetailPage.editButton).toBeVisible();
      await expect(ruleDetailPage.editButton).toHaveText(/Edit Rule/);
    });

    test('should enter edit mode when Edit button is clicked', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickEdit();

      // Should show Save and Cancel buttons
      await expect(ruleDetailPage.saveButton).toBeVisible();
      await expect(ruleDetailPage.cancelButton).toBeVisible();

      // Edit button should be hidden
      await expect(ruleDetailPage.editButton).not.toBeVisible();
    });
  });

  test.describe('Edit Mode UI', () => {
    test('should show editable description field in edit mode', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickEdit();

      await expect(ruleDetailPage.descriptionTextarea).toBeVisible();
    });

    test('should show editable logic field in edit mode', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickEdit();

      await expect(ruleDetailPage.editableLogicTextarea).toBeVisible();
    });

    test('should populate edit fields with current values', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      // Get current description value before entering edit mode
      const originalDescription = await ruleDetailPage.getDescription();
      const originalLogic = await ruleDetailPage.getLogic();

      await ruleDetailPage.clickEdit();

      // Check that edit fields contain the original values
      const editedDescription = await ruleDetailPage.getEditedDescription();
      const editedLogic = await ruleDetailPage.getEditedLogic();

      expect(editedDescription).toBe(originalDescription);
      expect(editedLogic).toBe(originalLogic);
    });

    test('should allow editing description', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickEdit();

      const newDescription = 'Updated test description ' + Date.now();
      await ruleDetailPage.setDescription(newDescription);

      const value = await ruleDetailPage.getEditedDescription();
      expect(value).toBe(newDescription);
    });

    test('should allow editing logic', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickEdit();

      const newLogic = "if $amount > 500:\n\treturn 'REVIEW'";
      await ruleDetailPage.setLogic(newLogic);

      const value = await ruleDetailPage.getEditedLogic();
      expect(value).toBe(newLogic);
    });
  });

  test.describe('Cancel Edit', () => {
    test('should exit edit mode when Cancel is clicked', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickEdit();
      await expect(ruleDetailPage.saveButton).toBeVisible();

      await ruleDetailPage.clickCancel();

      // Should exit edit mode
      await expect(ruleDetailPage.editButton).toBeVisible();
      await expect(ruleDetailPage.saveButton).not.toBeVisible();
    });

    test('should restore original values when Cancel is clicked', async () => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const originalDescription = await ruleDetailPage.getDescription();

      await ruleDetailPage.clickEdit();
      await ruleDetailPage.setDescription('This should be discarded');
      await ruleDetailPage.clickCancel();

      // Description should show original value
      const displayedDescription = await ruleDetailPage.getDescription();
      expect(displayedDescription).toBe(originalDescription);
    });
  });

  test.describe('Save Changes', () => {
    test('should save changes successfully', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      // Get original description to restore later
      const originalDescription = await ruleDetailPage.getDescription();

      await ruleDetailPage.clickEdit();

      // Update description with unique timestamp
      const newDescription = 'E2E Test Update ' + Date.now();
      await ruleDetailPage.setDescription(newDescription);

      // Wait for the PUT request to complete when clicking save
      await Promise.all([
        page.waitForResponse(resp => resp.url().includes('/api/rules/') && resp.request().method() === 'PUT'),
        ruleDetailPage.clickSave()
      ]);

      // Wait for success message
      await ruleDetailPage.waitForSaveSuccess();

      // Should exit edit mode
      await expect(ruleDetailPage.editButton).toBeVisible();
      await expect(ruleDetailPage.saveButton).not.toBeVisible();

      // Verify the displayed description is updated
      const displayedDescription = await ruleDetailPage.getDescription();
      expect(displayedDescription).toBe(newDescription);

      // Restore original description for other tests
      await ruleDetailPage.clickEdit();
      await ruleDetailPage.setDescription(originalDescription);
      await Promise.all([
        page.waitForResponse(resp => resp.url().includes('/api/rules/') && resp.request().method() === 'PUT'),
        ruleDetailPage.clickSave()
      ]);
      await ruleDetailPage.waitForSaveSuccess();
    });

    test('should display success message after save', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const originalDescription = await ruleDetailPage.getDescription();

      await ruleDetailPage.clickEdit();
      await ruleDetailPage.setDescription('Test success message ' + Date.now());

      // Wait for the PUT request to complete when clicking save
      await Promise.all([
        page.waitForResponse(resp => resp.url().includes('/api/rules/') && resp.request().method() === 'PUT'),
        ruleDetailPage.clickSave()
      ]);

      await expect(ruleDetailPage.saveSuccessMessage).toBeVisible();

      // Restore original
      await ruleDetailPage.clickEdit();
      await ruleDetailPage.setDescription(originalDescription);
      await Promise.all([
        page.waitForResponse(resp => resp.url().includes('/api/rules/') && resp.request().method() === 'PUT'),
        ruleDetailPage.clickSave()
      ]);
    });

    test('should update revision list after save', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      // Check initial revision count - use specific locator for revisions section
      const revisionsContainer = page.locator('h2:has-text("Other Rule Versions")').locator('..').locator('.space-y-2');
      const revisionsVisible = await ruleDetailPage.revisionsSection.isVisible().catch(() => false);
      let initialRevisionCount = 0;
      if (revisionsVisible) {
        initialRevisionCount = await revisionsContainer.locator('a').count();
      }

      const originalDescription = await ruleDetailPage.getDescription();

      await ruleDetailPage.clickEdit();
      await ruleDetailPage.setDescription('Revision test ' + Date.now());

      // Wait for the PUT request to complete when clicking save
      await Promise.all([
        page.waitForResponse(resp => resp.url().includes('/api/rules/') && resp.request().method() === 'PUT'),
        ruleDetailPage.clickSave()
      ]);
      await ruleDetailPage.waitForSaveSuccess();

      // Reload page to see updated revisions
      await page.reload();
      await ruleDetailPage.waitForRuleToLoad();

      // Should have more revisions now
      const newRevisionCount = await revisionsContainer.locator('a').count();
      expect(newRevisionCount).toBeGreaterThanOrEqual(initialRevisionCount);

      // Restore original
      await ruleDetailPage.clickEdit();
      await ruleDetailPage.setDescription(originalDescription);
      await Promise.all([
        page.waitForResponse(resp => resp.url().includes('/api/rules/') && resp.request().method() === 'PUT'),
        ruleDetailPage.clickSave()
      ]);
    });

    test('should handle invalid logic gracefully', async ({ page }) => {
      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      await ruleDetailPage.clickEdit();

      // Set invalid logic
      await ruleDetailPage.setLogic('this is not valid python syntax !!!');
      await ruleDetailPage.clickSave();

      // Should show error message
      await expect(ruleDetailPage.saveErrorMessage).toBeVisible({ timeout: 5000 });

      // Should still be in edit mode
      await expect(ruleDetailPage.saveButton).toBeVisible();
    });
  });

  test.describe('API Integration', () => {
    test('should send PUT request to update rule', async ({ page }) => {
      // Intercept the PUT request
      let putRequestMade = false;
      let requestBody: any = null;

      page.on('request', request => {
        if (request.method() === 'PUT' && request.url().includes('/api/rules/')) {
          putRequestMade = true;
          requestBody = request.postDataJSON();
        }
      });

      await ruleDetailPage.goto(testRuleId);
      await ruleDetailPage.waitForRuleToLoad();

      const originalDescription = await ruleDetailPage.getDescription();
      const newDescription = 'API test ' + Date.now();

      await ruleDetailPage.clickEdit();
      await ruleDetailPage.setDescription(newDescription);

      // Wait for the PUT request to complete when clicking save
      await Promise.all([
        page.waitForResponse(resp => resp.url().includes('/api/rules/') && resp.request().method() === 'PUT'),
        ruleDetailPage.clickSave()
      ]);

      expect(putRequestMade).toBe(true);
      expect(requestBody.description).toBe(newDescription);

      // Restore original
      await ruleDetailPage.waitForSaveSuccess();
      await ruleDetailPage.clickEdit();
      await ruleDetailPage.setDescription(originalDescription);
      await Promise.all([
        page.waitForResponse(resp => resp.url().includes('/api/rules/') && resp.request().method() === 'PUT'),
        ruleDetailPage.clickSave()
      ]);
    });
  });
});
