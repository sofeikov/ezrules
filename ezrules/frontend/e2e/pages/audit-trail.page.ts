import { Page, Locator } from '@playwright/test';

/**
 * Page Object Model for the Audit Trail page.
 * Encapsulates all interactions with the audit trail UI.
 * The page uses an accordion layout with collapsible sections.
 */
export class AuditTrailPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly description: Locator;
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;

  // Accordion section buttons
  readonly ruleHistoryAccordion: Locator;
  readonly configHistoryAccordion: Locator;
  readonly userListHistoryAccordion: Locator;
  readonly outcomeHistoryAccordion: Locator;
  readonly labelHistoryAccordion: Locator;

  // Section headings (inside accordion buttons)
  readonly ruleHistoryHeading: Locator;
  readonly configHistoryHeading: Locator;
  readonly userListHistoryHeading: Locator;
  readonly outcomeHistoryHeading: Locator;
  readonly labelHistoryHeading: Locator;

  // Tables (visible only when sections are expanded)
  readonly ruleHistoryTable: Locator;
  readonly configHistoryTable: Locator;
  readonly userListHistoryTable: Locator;
  readonly outcomeHistoryTable: Locator;
  readonly labelHistoryTable: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.description = page.locator('text=History of rule and configuration changes');
    this.loadingSpinner = page.locator('.animate-spin');
    this.errorMessage = page.locator('.bg-red-50.border-red-200');

    // Accordion buttons
    this.ruleHistoryAccordion = page.locator('[data-testid="accordion-rules"]');
    this.configHistoryAccordion = page.locator('[data-testid="accordion-config"]');
    this.userListHistoryAccordion = page.locator('[data-testid="accordion-user-lists"]');
    this.outcomeHistoryAccordion = page.locator('[data-testid="accordion-outcomes"]');
    this.labelHistoryAccordion = page.locator('[data-testid="accordion-labels"]');

    // Section headings
    this.ruleHistoryHeading = page.locator('h2:has-text("Rule History")');
    this.configHistoryHeading = page.locator('h2:has-text("Configuration History")');
    this.userListHistoryHeading = page.locator('h2:has-text("User List History")');
    this.outcomeHistoryHeading = page.locator('h2:has-text("Outcome History")');
    this.labelHistoryHeading = page.locator('h2:has-text("Label History")');

    // Tables - scoped to parent sections via data-testid
    this.ruleHistoryTable = this.ruleHistoryAccordion.locator('..').locator('table');
    this.configHistoryTable = this.configHistoryAccordion.locator('..').locator('table');
    this.userListHistoryTable = this.userListHistoryAccordion.locator('..').locator('table');
    this.outcomeHistoryTable = this.outcomeHistoryAccordion.locator('..').locator('table');
    this.labelHistoryTable = this.labelHistoryAccordion.locator('..').locator('table');
  }

  async goto() {
    await this.page.goto('/audit');
  }

  async waitForPageToLoad() {
    await this.heading.waitFor({ state: 'visible' });
    // Wait for loading spinner to disappear
    await this.loadingSpinner.waitFor({ state: 'hidden', timeout: 10000 }).catch(() => {});
  }

  async expandSection(section: 'rules' | 'config' | 'userLists' | 'outcomes' | 'labels') {
    const accordionMap = {
      rules: this.ruleHistoryAccordion,
      config: this.configHistoryAccordion,
      userLists: this.userListHistoryAccordion,
      outcomes: this.outcomeHistoryAccordion,
      labels: this.labelHistoryAccordion,
    };
    await accordionMap[section].click();
  }

  async getRuleHistoryRowCount(): Promise<number> {
    return await this.ruleHistoryTable.locator('tbody tr').count();
  }

  async getConfigHistoryRowCount(): Promise<number> {
    return await this.configHistoryTable.locator('tbody tr').count();
  }

  async getUserListHistoryRowCount(): Promise<number> {
    return await this.userListHistoryTable.locator('tbody tr').count();
  }

  async getOutcomeHistoryRowCount(): Promise<number> {
    return await this.outcomeHistoryTable.locator('tbody tr').count();
  }

  async getLabelHistoryRowCount(): Promise<number> {
    return await this.labelHistoryTable.locator('tbody tr').count();
  }

  async getRuleHistoryColumnHeaders(): Promise<string[]> {
    const headers = this.ruleHistoryTable.locator('thead th');
    const count = await headers.count();
    const result: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await headers.nth(i).textContent();
      if (text) result.push(text.trim());
    }
    return result;
  }

  async getConfigHistoryColumnHeaders(): Promise<string[]> {
    const headers = this.configHistoryTable.locator('thead th');
    const count = await headers.count();
    const result: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await headers.nth(i).textContent();
      if (text) result.push(text.trim());
    }
    return result;
  }

  async getUserListHistoryColumnHeaders(): Promise<string[]> {
    const headers = this.userListHistoryTable.locator('thead th');
    const count = await headers.count();
    const result: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await headers.nth(i).textContent();
      if (text) result.push(text.trim());
    }
    return result;
  }

  async getOutcomeHistoryColumnHeaders(): Promise<string[]> {
    const headers = this.outcomeHistoryTable.locator('thead th');
    const count = await headers.count();
    const result: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await headers.nth(i).textContent();
      if (text) result.push(text.trim());
    }
    return result;
  }

  async getLabelHistoryColumnHeaders(): Promise<string[]> {
    const headers = this.labelHistoryTable.locator('thead th');
    const count = await headers.count();
    const result: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await headers.nth(i).textContent();
      if (text) result.push(text.trim());
    }
    return result;
  }
}
