import { test, expect } from '@playwright/test';
import { UserListsPage } from '../pages/user-lists.page';

/**
 * E2E tests for the User Lists management page.
 */
test.describe('User Lists Page', () => {
  let userListsPage: UserListsPage;

  test.beforeEach(async ({ page }) => {
    userListsPage = new UserListsPage(page);
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

    test('should create a new list and display it', async ({ page }) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      const uniqueName = `E2ELIST${Date.now()}`;

      await userListsPage.createList(uniqueName);

      // Wait for the list to appear
      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return Array.from(items).some(item => item.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );

      expect(await userListsPage.hasListWithName(uniqueName)).toBe(true);

      // Cleanup: delete the list we created
      page.on('dialog', dialog => dialog.accept());
      await userListsPage.clickDeleteList(uniqueName);
      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return !Array.from(items).some(item => item.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );
    });

    test('should show error for duplicate list name', async ({ page }) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      // Create a unique list first
      const uniqueName = `DUPTEST${Date.now()}`;
      await userListsPage.createList(uniqueName);

      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return Array.from(items).some(item => item.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );

      // Try to create the same list again
      await userListsPage.createList(uniqueName);

      // Should show an error about already exists
      const errorText = page.locator('text=/already exists/i');
      await expect(errorText).toBeVisible();

      // Cleanup
      page.on('dialog', dialog => dialog.accept());
      await userListsPage.clickDeleteList(uniqueName);
      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return !Array.from(items).some(item => item.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );
    });

    test('should delete a list after confirmation', async ({ page }) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      // Create a list to delete
      const uniqueName = `DELLIST${Date.now()}`;
      await userListsPage.createList(uniqueName);

      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return Array.from(items).some(item => item.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );

      // Accept the confirmation dialog
      page.on('dialog', dialog => dialog.accept());

      const countBefore = await userListsPage.getListCount();
      await userListsPage.clickDeleteList(uniqueName);

      // Wait for the list to disappear
      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return !Array.from(items).some(item => item.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );

      const countAfter = await userListsPage.getListCount();
      expect(countAfter).toBe(countBefore - 1);
    });

    test('should not delete a list when confirmation is dismissed', async ({ page }) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      // Create a list to test with
      const uniqueName = `NODELL${Date.now()}`;
      await userListsPage.createList(uniqueName);

      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return Array.from(items).some(item => item.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );

      const countBefore = await userListsPage.getListCount();

      // Dismiss the confirmation dialog
      page.on('dialog', dialog => dialog.dismiss());

      await userListsPage.clickDeleteList(uniqueName);

      // Wait briefly and check count is unchanged
      await page.waitForTimeout(500);
      const countAfter = await userListsPage.getListCount();
      expect(countAfter).toBe(countBefore);

      // Cleanup: need to re-register with accept
      page.removeAllListeners('dialog');
      page.on('dialog', dialog => dialog.accept());
      await userListsPage.clickDeleteList(uniqueName);
      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return !Array.from(items).some(item => item.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );
    });
  });

  test.describe('Entries Management', () => {
    test('should show empty state when no list is selected', async ({ page }) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      const emptyState = page.locator('text=Select a list to view and manage its entries');
      await expect(emptyState).toBeVisible();
    });

    test('should show entries panel when a list is selected', async ({ page }) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      // Create a list to select
      const uniqueName = `ENTRYTEST${Date.now()}`;
      await userListsPage.createList(uniqueName);

      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return Array.from(items).some(item => item.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );

      // Select the list
      await userListsPage.selectList(uniqueName);
      await userListsPage.waitForEntriesToLoad();

      // Should show the list name as heading in right panel
      const listHeading = page.locator('.w-2\\/3 h2:has-text("' + uniqueName + '")');
      await expect(listHeading).toBeVisible();

      // Should show Add Entry form
      await expect(userListsPage.entryValueInput).toBeVisible();
      await expect(userListsPage.addEntryButton).toBeVisible();

      // Cleanup
      page.on('dialog', dialog => dialog.accept());
      await userListsPage.clickDeleteList(uniqueName);
      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return !Array.from(items).some(item => item.textContent?.includes(name));
        },
        uniqueName,
        { timeout: 5000 }
      );
    });

    test('should add an entry to a list', async ({ page }) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      // Create a list
      const listName = `ADDENTRY${Date.now()}`;
      await userListsPage.createList(listName);

      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return Array.from(items).some(item => item.textContent?.includes(name));
        },
        listName,
        { timeout: 5000 }
      );

      // Select the list
      await userListsPage.selectList(listName);
      await userListsPage.waitForEntriesToLoad();

      // Add an entry
      const entryValue = `VAL${Date.now()}`;
      await userListsPage.addEntry(entryValue);

      // Wait for the entry to appear
      await page.waitForFunction(
        (val: string) => {
          const items = document.querySelectorAll('.w-2\\/3 ul li');
          return Array.from(items).some(item => item.textContent?.includes(val));
        },
        entryValue,
        { timeout: 5000 }
      );

      expect(await userListsPage.hasEntry(entryValue)).toBe(true);

      // Cleanup
      page.on('dialog', dialog => dialog.accept());
      await userListsPage.clickDeleteList(listName);
      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return !Array.from(items).some(item => item.textContent?.includes(name));
        },
        listName,
        { timeout: 5000 }
      );
    });

    test('should show error for duplicate entry', async ({ page }) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      // Create a list and add an entry
      const listName = `DUPENTRY${Date.now()}`;
      await userListsPage.createList(listName);

      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return Array.from(items).some(item => item.textContent?.includes(name));
        },
        listName,
        { timeout: 5000 }
      );

      await userListsPage.selectList(listName);
      await userListsPage.waitForEntriesToLoad();

      const entryValue = `DUP${Date.now()}`;
      await userListsPage.addEntry(entryValue);

      await page.waitForFunction(
        (val: string) => {
          const items = document.querySelectorAll('.w-2\\/3 ul li');
          return Array.from(items).some(item => item.textContent?.includes(val));
        },
        entryValue,
        { timeout: 5000 }
      );

      // Try to add the same entry again
      await userListsPage.addEntry(entryValue);

      // Should show an error about already exists
      const errorText = page.locator('text=/already exists/i');
      await expect(errorText).toBeVisible();

      // Cleanup
      page.on('dialog', dialog => dialog.accept());
      await userListsPage.clickDeleteList(listName);
      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return !Array.from(items).some(item => item.textContent?.includes(name));
        },
        listName,
        { timeout: 5000 }
      );
    });

    test('should delete an entry after confirmation', async ({ page }) => {
      await userListsPage.goto();
      await userListsPage.waitForListsToLoad();

      // Create a list and add an entry
      const listName = `DELENTRY${Date.now()}`;
      await userListsPage.createList(listName);

      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return Array.from(items).some(item => item.textContent?.includes(name));
        },
        listName,
        { timeout: 5000 }
      );

      await userListsPage.selectList(listName);
      await userListsPage.waitForEntriesToLoad();

      const entryValue = `TODEL${Date.now()}`;
      await userListsPage.addEntry(entryValue);

      await page.waitForFunction(
        (val: string) => {
          const items = document.querySelectorAll('.w-2\\/3 ul li');
          return Array.from(items).some(item => item.textContent?.includes(val));
        },
        entryValue,
        { timeout: 5000 }
      );

      // Accept the confirmation dialog and delete the entry
      page.on('dialog', dialog => dialog.accept());
      await userListsPage.clickDeleteEntry(entryValue);

      // Wait for the entry to disappear
      await page.waitForFunction(
        (val: string) => {
          const items = document.querySelectorAll('.w-2\\/3 ul li');
          return !Array.from(items).some(item => item.textContent?.includes(val));
        },
        entryValue,
        { timeout: 5000 }
      );

      expect(await userListsPage.hasEntry(entryValue)).toBe(false);

      // Cleanup: delete the list
      await userListsPage.clickDeleteList(listName);
      await page.waitForFunction(
        (name: string) => {
          const items = document.querySelectorAll('.w-1\\/3 ul li');
          return !Array.from(items).some(item => item.textContent?.includes(name));
        },
        listName,
        { timeout: 5000 }
      );
    });
  });
});
