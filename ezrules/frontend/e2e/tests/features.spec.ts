import { expect, test } from '@playwright/test';
import { FeaturesPage } from '../pages/features.page';

test.describe('Features Page', () => {
  let featuresPage: FeaturesPage;

  test.beforeEach(async ({ page }) => {
    featuresPage = new FeaturesPage(page);
  });

  test('loads from sidebar navigation', async ({ page }) => {
    await page.goto('/dashboard');
    const link = page.locator('a:has-text("Features")');
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/.*features/);
    await expect(featuresPage.heading).toHaveText('Features');
  });

  test('creates and activates a feature definition', async () => {
    await featuresPage.goto();
    await featuresPage.waitForLoad();

    const suffix = Date.now();
    const name = `Sender velocity ${suffix}`;
    const featureName = `sent_amount_sum_24h_${suffix}`;

    await featuresPage.createFeature(name, featureName);
    await expect(featuresPage.featureRow(name)).toContainText(`stat[sender.${featureName}]`);
    await expect(featuresPage.featureRow(name)).toContainText('draft');

    await featuresPage.activateFeature(name);
    await expect(featuresPage.featureRow(name)).toContainText('active');
  });
});
