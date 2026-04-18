import { expect, test } from '@playwright/test';
import { RuleCreatePage } from '../pages/rule-create.page';

test.describe('Rule Test JSON Demo Nested Values', () => {
  let ruleCreatePage: RuleCreatePage;

  test.beforeEach(async ({ page }) => {
    ruleCreatePage = new RuleCreatePage(page);
  });

  test('prefills nested customer and sender paths with demo-friendly values', async ({ page }) => {
    await ruleCreatePage.goto();
    await ruleCreatePage.fillLogic(
      'if $customer.profile.age >= 21 and $sender.device.trust_score <= 35 and $sender.origin.country != "US":\n\treturn !HOLD'
    );

    await page.waitForResponse((response) => response.url().includes('/api/v2/rules/verify'));

    await expect.poll(async () => {
      const rawValue = await ruleCreatePage.getTestJsonValue();
      return rawValue.trim() ? JSON.parse(rawValue) : null;
    }).toMatchObject({
      customer: {
        profile: {
          age: 34,
        },
      },
      sender: {
        device: {
          trust_score: 18,
        },
        origin: {
          country: 'BR',
        },
      },
    });
  });
});
