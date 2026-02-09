import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the User Lists management page.
 * Encapsulates all interactions with the user lists UI.
 */
export class UserListsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly listNameInput: Locator;
  readonly createListButton: Locator;
  readonly entryValueInput: Locator;
  readonly addEntryButton: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly listCountText: Locator;
  readonly entryCountText: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.listNameInput = page.locator('input[placeholder="Enter list name"]');
    this.createListButton = page.locator('button:has-text("Create")');
    this.entryValueInput = page.locator('input[placeholder="Enter entry value"]');
    this.addEntryButton = page.locator('button:has-text("Add Entry")');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('.bg-red-50.border-red-200');
    this.listCountText = page.locator('text=/\\d+ lists? total/');
    this.entryCountText = page.locator('.w-2\\/3 .bg-gray-50 p');
  }

  /**
   * Navigate to the user lists page
   */
  async goto() {
    await this.page.goto('/user-lists');
  }

  /**
   * Wait for lists to be rendered (count text visible)
   */
  async waitForListsToLoad() {
    await this.listCountText.waitFor({ state: 'visible' });
  }

  /**
   * Get the number of list items displayed in the left panel
   */
  async getListCount(): Promise<number> {
    await this.waitForListsToLoad();
    // Lists are in the left panel (w-1/3) ul
    return await this.page.locator('.w-1\\/3 ul li').count();
  }

  /**
   * Check whether a list with the given name is visible
   */
  async hasListWithName(name: string): Promise<boolean> {
    await this.waitForListsToLoad();
    return await this.page.locator('.w-1\\/3 li:has-text("' + name + '")').isVisible();
  }

  /**
   * Create a new list with the given name
   */
  async createList(name: string) {
    await this.listNameInput.fill(name);
    await this.createListButton.click();
  }

  /**
   * Click on a list to select it and view its entries
   */
  async selectList(name: string) {
    const listItem = this.page.locator('.w-1\\/3 li', { hasText: name });
    await listItem.click();
  }

  /**
   * Click the Delete button for a specific list
   */
  async clickDeleteList(name: string) {
    const row = this.page.locator('.w-1\\/3 li', { hasText: name });
    await row.locator('button:has-text("Delete")').click();
  }

  /**
   * Add an entry to the currently selected list
   */
  async addEntry(value: string) {
    await this.entryValueInput.fill(value);
    await this.addEntryButton.click();
  }

  /**
   * Check if an entry with the given value exists in the right panel
   */
  async hasEntry(value: string): Promise<boolean> {
    return await this.page.locator('.w-2\\/3 li:has-text("' + value + '")').isVisible();
  }

  /**
   * Click the Delete button for a specific entry
   */
  async clickDeleteEntry(value: string) {
    const row = this.page.locator('.w-2\\/3 li', { hasText: value });
    await row.locator('button:has-text("Delete")').click();
  }

  /**
   * Wait for entries panel to show (after selecting a list)
   */
  async waitForEntriesToLoad() {
    await this.entryCountText.waitFor({ state: 'visible' });
  }
}
