import { test, expect } from '@playwright/test';
import { RuleListPage } from '../pages/rule-list.page';
import { RuleCreatePage } from '../pages/rule-create.page';
import { RuleDetailPage } from '../pages/rule-detail.page';

/**
 * E2E tests for the Create Rule page.
 * Tests navigation, form fields, rule testing, and rule creation.
 */

test.describe('Rule Create Page', () => {
  let ruleListPage: RuleListPage;
  let ruleCreatePage: RuleCreatePage;
  let ruleDetailPage: RuleDetailPage;

  test.beforeEach(async ({ page }) => {
    ruleListPage = new RuleListPage(page);
    ruleCreatePage = new RuleCreatePage(page);
    ruleDetailPage = new RuleDetailPage(page);
  });

  test.describe('Navigation', () => {
    test('should be accessible from the New Rule button on the rules list page', async ({ page }) => {
      await ruleListPage.goto();
      await ruleListPage.waitForRulesToLoad();

      // Click the "New Rule" button in the header
      const newRuleButton = page.locator('a:has-text("New Rule")');
      await newRuleButton.click();

      // Should navigate to /rules/create
      await expect(page).toHaveURL(/\/rules\/create/);
      await expect(ruleCreatePage.heading).toBeVisible();
    });

    test('should navigate back to rules list when Back to Rules button is clicked', async ({ page }) => {
      await ruleCreatePage.goto();
      await expect(ruleCreatePage.heading).toBeVisible();

      await ruleCreatePage.clickBack();

      await expect(page).toHaveURL(/\/rules/);
      await ruleListPage.waitForRulesToLoad();
    });

    test('should navigate back to rules list via breadcrumb', async ({ page }) => {
      await ruleCreatePage.goto();
      await expect(ruleCreatePage.heading).toBeVisible();

      await ruleCreatePage.clickBreadcrumbBack();

      await expect(page).toHaveURL(/\/rules/);
      await ruleListPage.waitForRulesToLoad();
    });
  });

  test.describe('Form Fields', () => {
    test('should display all form fields: Rule ID, Description, Logic', async () => {
      await ruleCreatePage.goto();

      await expect(ruleCreatePage.ruleIdInput).toBeVisible();
      await expect(ruleCreatePage.descriptionTextarea).toBeVisible();
      await expect(ruleCreatePage.logicTextarea).toBeVisible();
    });

    test('should display the Create Rule and Back to Rules buttons', async () => {
      await ruleCreatePage.goto();

      await expect(ruleCreatePage.submitButton).toBeVisible();
      await expect(ruleCreatePage.backButton).toBeVisible();
    });

    test('should allow filling in Rule ID field', async () => {
      await ruleCreatePage.goto();

      const testId = 'TEST_RULE_ID';
      await ruleCreatePage.fillRuleId(testId);

      const value = await ruleCreatePage.ruleIdInput.inputValue();
      expect(value).toBe(testId);
    });

    test('should allow filling in Description field', async () => {
      await ruleCreatePage.goto();

      const testDesc = 'A test description';
      await ruleCreatePage.fillDescription(testDesc);

      const value = await ruleCreatePage.descriptionTextarea.inputValue();
      expect(value).toBe(testDesc);
    });

    test('should allow filling in Logic field', async () => {
      await ruleCreatePage.goto();

      const testLogic = "if $amount > 100:\n\treturn 'HOLD'";
      await ruleCreatePage.fillLogic(testLogic);

      const value = await ruleCreatePage.logicTextarea.inputValue();
      expect(value).toBe(testLogic);
    });

    test('should support TAB key in Logic textarea', async () => {
      await ruleCreatePage.goto();

      await ruleCreatePage.logicTextarea.click();
      await ruleCreatePage.logicTextarea.fill('line1');
      await ruleCreatePage.logicTextarea.press('Tab');

      const value = await ruleCreatePage.logicTextarea.inputValue();
      expect(value).toContain('\t');
    });
  });

  test.describe('Test Rule Section', () => {
    test('should display Test Rule section with textarea and button', async () => {
      await ruleCreatePage.goto();

      await expect(ruleCreatePage.testJsonTextarea).toBeVisible();
      await expect(ruleCreatePage.testRuleButton).toBeVisible();
    });

    test('should populate Test JSON when valid Logic is entered', async ({ page }) => {
      await ruleCreatePage.goto();

      // Fill in logic with a rule that uses $amount parameter
      await ruleCreatePage.fillLogic("if $amount > 100:\n\treturn 'HOLD'");

      // Wait for the verify API call to complete and populate testJson
      await page.waitForResponse(resp => resp.url().includes('/api/v2/rules/verify'));
      await page.waitForTimeout(500);

      const testJsonValue = await ruleCreatePage.getTestJsonValue();
      expect(testJsonValue).toContain('amount');
    });

    test('should test the rule successfully with valid input', async ({ page }) => {
      await ruleCreatePage.goto();

      // Fill in logic
      await ruleCreatePage.fillLogic("if $amount > 100:\n\treturn 'HOLD'");

      // Wait for params to populate
      await page.waitForResponse(resp => resp.url().includes('/api/v2/rules/verify'));
      await page.waitForTimeout(500);

      // Fill in test JSON with a value that triggers HOLD
      await ruleCreatePage.fillTestJson('{"amount": 500}');

      // Click test button and wait for response
      await Promise.all([
        page.waitForResponse(resp => resp.url().includes('/api/v2/rules/test')),
        ruleCreatePage.clickTestRule()
      ]);

      // Should show a test result
      const resultContainer = page.locator('.bg-green-50, .bg-red-50').filter({ hasText: 'Rule Result' });
      await expect(resultContainer).toBeVisible();
    });

    test('should Test Rule button be disabled when logic is empty', async () => {
      await ruleCreatePage.goto();

      // Logic is empty by default, button should be disabled
      await expect(ruleCreatePage.testRuleButton).toBeDisabled();
    });
  });

  test.describe('Rule Creation', () => {
    test('should create a rule and navigate to the detail page', async ({ page }) => {
      await ruleCreatePage.goto();

      const uniqueRid = 'E2E_CREATE_' + Date.now();
      const description = 'E2E test rule created at ' + Date.now();
      const logic = "if $amount > 100:\n\treturn 'HOLD'";

      await ruleCreatePage.fillRuleId(uniqueRid);
      await ruleCreatePage.fillDescription(description);
      await ruleCreatePage.fillLogic(logic);

      // Submit and wait for POST response
      await Promise.all([
        page.waitForResponse(resp => resp.url().endsWith('/api/v2/rules') && resp.request().method() === 'POST'),
        ruleCreatePage.clickSubmit()
      ]);

      // Should navigate to the rule detail page
      await expect(page).toHaveURL(/\/rules\/\d+/);

      // Verify the detail page shows our created rule
      await ruleDetailPage.waitForRuleToLoad();
      const displayedRuleId = await ruleDetailPage.getRuleId();
      expect(displayedRuleId).toBe(uniqueRid);
    });

    test('should display error for invalid logic syntax', async ({ page }) => {
      await ruleCreatePage.goto();

      await ruleCreatePage.fillRuleId('INVALID_LOGIC_TEST');
      await ruleCreatePage.fillDescription('Test with bad logic');
      await ruleCreatePage.fillLogic('this is not valid python syntax !!!');

      await ruleCreatePage.clickSubmit();

      // Should show error message
      await expect(ruleCreatePage.saveErrorMessage).toBeVisible({ timeout: 5000 });

      // Should stay on the create page
      await expect(page).toHaveURL(/\/rules\/create/);
    });

    test('should display error when Rule ID is missing', async ({ page }) => {
      await ruleCreatePage.goto();

      // Leave Rule ID empty, fill others
      await ruleCreatePage.fillDescription('Test description');
      await ruleCreatePage.fillLogic("if $amount > 100:\n\treturn 'HOLD'");

      await ruleCreatePage.clickSubmit();

      // Should show error
      await expect(ruleCreatePage.saveErrorMessage).toBeVisible({ timeout: 5000 });

      // Should stay on create page
      await expect(page).toHaveURL(/\/rules\/create/);
    });

    test('should send POST request with correct body to /api/v2/rules', async ({ page }) => {
      let postRequestBody: any = null;

      page.on('request', request => {
        if (request.method() === 'POST' && request.url().endsWith('/api/v2/rules')) {
          postRequestBody = request.postDataJSON();
        }
      });

      await ruleCreatePage.goto();

      const uniqueRid = 'E2E_POST_CHECK_' + Date.now();
      const description = 'POST body test';
      const logic = "if $amount > 50:\n\treturn 'REVIEW'";

      await ruleCreatePage.fillRuleId(uniqueRid);
      await ruleCreatePage.fillDescription(description);
      await ruleCreatePage.fillLogic(logic);

      await Promise.all([
        page.waitForResponse(resp => resp.url().endsWith('/api/v2/rules') && resp.request().method() === 'POST'),
        ruleCreatePage.clickSubmit()
      ]);

      expect(postRequestBody).not.toBeNull();
      expect(postRequestBody.rid).toBe(uniqueRid);
      expect(postRequestBody.description).toBe(description);
      expect(postRequestBody.logic).toBe(logic);
    });
  });
});
