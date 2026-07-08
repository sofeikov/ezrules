import type { Page } from '@playwright/test';
import { test, expect } from '../support/fixtures';
import { UserListsPage } from '../pages/user-lists.page';
import { deleteUserListByName } from '../support/api-helpers';
import { testResourceName } from '../support/test-data';
import { STATEFUL_TAG, TEST_DATA_TAG } from '../support/tags';

/**
 * E2E tests for the User Lists management page.
 */
test.describe(`User Lists Page ${STATEFUL_TAG} ${TEST_DATA_TAG}`, () => {
  let userListsPage: UserListsPage;
  let createdListNames: string[];

  async function createListAndWait(name: string) {
    await userListsPage.createList(name);
    await userListsPage.waitForList(name);
    createdListNames.push(name);
  }

  async function deleteListAndWait(page: Page, name: string) {
    const dialogPromise = page.waitForEvent('dialog');
    await userListsPage.clickDeleteList(name);
    const dialog = await dialogPromise;
    await dialog.accept();
    await userListsPage.waitForListRemoved(name);
  }

  async function addEntryAndWait(value: string) {
    await userListsPage.addEntry(value);
    await userListsPage.waitForEntry(value);
  }

  async function deleteEntryAndWait(page: Page, value: string) {
    const dialogPromise = page.waitForEvent('dialog');
    await userListsPage.clickDeleteEntry(value);
    const dialog = await dialogPromise;
    await dialog.accept();
    await userListsPage.waitForEntryRemoved(value);
  }

  test.beforeEach(async ({ page }) => {
    userListsPage = new UserListsPage(page);
    createdListNames = [];
  });

  test.afterEach(async ({ request }) => {
    for (const listName of createdListNames) {
      await deleteUserListByName(request, listName);
    }
  });

  test.describe('Page Structure', () => {
    test('should load the user lists page successfully', async ({ page }) => {
      await userListsPage.goto();
      await expect(page).toHaveURL(/.*user-lists/);
    });

    test('should display the correct heading', async () => {
      await userListsPage.goto();
      await expect(userListsPage.heading).toHaveText('User Lists');
    });

    test('should display the page description', async ({ page }) => {
      await userListsPage.goto();
      const description = page.locator('text=Manage user lists for rule conditions');
      await expect(description).toBeVisible();
    });

    test('should be reachable from sidebar navigation', async ({ page }) => {
      await page.goto('/rules');
      const userListsLink = page.locator('a:has-text("User Lists")');
      await expect(userListsLink).toBeVisible();
      await userListsLink.click();
      await expect(page).toHaveURL(/.*user-lists/);
      await expect(userListsPage.heading).toHaveText('User Lists');
    });
  });

  test.describe('Lists Management', () => {
    test('should display list count summary', async () => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      await expect(userListsPage.listCountText).toBeVisible();
    });

    test('should have the list name input and Create button', async () => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      await expect(userListsPage.listNameInput).toBeVisible();
      await expect(userListsPage.createListButton).toBeVisible();
    });

    test('should create a new list and display it', async ({ page }, testInfo) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      const uniqueName = testResourceName(testInfo, 'E2ELIST', { uppercase: true });
      await createListAndWait(uniqueName);

      expect(await userListsPage.hasListWithName(uniqueName)).toBe(true);

      // Cleanup: delete the list we created
      await deleteListAndWait(page, uniqueName);
    });

    test('should show error for duplicate list name', async ({ page }, testInfo) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      const uniqueName = testResourceName(testInfo, 'DUPTEST', { uppercase: true });
      await createListAndWait(uniqueName);

      // Try to create the same list again
      await userListsPage.createList(uniqueName);

      // Should show an error about already exists
      const errorText = page.locator('text=/already exists/i');
      await expect(errorText).toBeVisible();

      // Cleanup
      await deleteListAndWait(page, uniqueName);
    });

    test('should delete a list after confirmation', async ({ page }, testInfo) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      const uniqueName = testResourceName(testInfo, 'DELLIST', { uppercase: true });
      await createListAndWait(uniqueName);

      const countBefore = await userListsPage.getListCount();
      await deleteListAndWait(page, uniqueName);

      await expect(userListsPage.listItems).toHaveCount(countBefore - 1);
    });

    test('should not delete a list when confirmation is dismissed', async ({ page }, testInfo) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      const uniqueName = testResourceName(testInfo, 'NODELL', { uppercase: true });
      await createListAndWait(uniqueName);

      const countBefore = await userListsPage.getListCount();

      const dialogPromise = page.waitForEvent('dialog');
      await userListsPage.clickDeleteList(uniqueName);
      const dialog = await dialogPromise;
      await dialog.dismiss();

      await expect(userListsPage.listItems).toHaveCount(countBefore);
      await expect(userListsPage.listItem(uniqueName)).toBeVisible();

      // Cleanup
      await deleteListAndWait(page, uniqueName);
    });
  });

  test.describe('Entries Management', () => {
    test('should show empty state when no list is selected', async ({ page }) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      const emptyState = page.locator('text=Select a list to view and manage its entries');
      await expect(emptyState).toBeVisible();
    });

    test('should show entries panel when a list is selected', async ({ page }, testInfo) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      const uniqueName = testResourceName(testInfo, 'ENTRYTEST', { uppercase: true });
      await createListAndWait(uniqueName);

      await userListsPage.selectList(uniqueName);
      await userListsPage.waitForEntriesToLoad();

      // Should show the list name as heading in right panel
      const listHeading = page.locator('.w-2\\/3 h2').filter({ hasText: uniqueName });
      await expect(listHeading).toBeVisible();

      // Should show Add Entry form
      await expect(userListsPage.entryValueInput).toBeVisible();
      await expect(userListsPage.addEntryButton).toBeVisible();

      // Cleanup
      await deleteListAndWait(page, uniqueName);
    });

    test('should add an entry to a list', async ({ page }, testInfo) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      const listName = testResourceName(testInfo, 'ADDENTRY', { uppercase: true });
      await createListAndWait(listName);

      await userListsPage.selectList(listName);
      await userListsPage.waitForEntriesToLoad();

      const entryValue = testResourceName(testInfo, 'VAL', { uppercase: true });
      await addEntryAndWait(entryValue);

      expect(await userListsPage.hasEntry(entryValue)).toBe(true);

      // Cleanup
      await deleteListAndWait(page, listName);
    });

    test('should show error for duplicate entry', async ({ page }, testInfo) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      const listName = testResourceName(testInfo, 'DUPENTRY', { uppercase: true });
      await createListAndWait(listName);

      await userListsPage.selectList(listName);
      await userListsPage.waitForEntriesToLoad();

      const entryValue = testResourceName(testInfo, 'DUP', { uppercase: true });
      await addEntryAndWait(entryValue);

      // Try to add the same entry again
      await userListsPage.addEntry(entryValue);

      // Should show an error about already exists
      const errorText = page.locator('text=/already exists/i');
      await expect(errorText).toBeVisible();

      // Cleanup
      await deleteListAndWait(page, listName);
    });

    test('should delete an entry after confirmation', async ({ page }, testInfo) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      const listName = testResourceName(testInfo, 'DELENTRY', { uppercase: true });
      await createListAndWait(listName);

      await userListsPage.selectList(listName);
      await userListsPage.waitForEntriesToLoad();

      const entryValue = testResourceName(testInfo, 'TODEL', { uppercase: true });
      await addEntryAndWait(entryValue);

      await deleteEntryAndWait(page, entryValue);

      expect(await userListsPage.hasEntry(entryValue)).toBe(false);

      // Cleanup: delete the list
      await deleteListAndWait(page, listName);
    });
  });
});
