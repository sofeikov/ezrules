import { Locator, Page } from '@playwright/test';

export class EventTesterPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly eventIdInput: Locator;
  readonly timestampInput: Locator;
  readonly payloadTextarea: Locator;
  readonly runButton: Locator;
  readonly resetButton: Locator;
  readonly resolvedOutcome: Locator;
  readonly matchedCount: Locator;
  readonly ledgerState: Locator;
  readonly ruleResults: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1');
    this.eventIdInput = page.getByTestId('event-test-id');
    this.timestampInput = page.getByTestId('event-test-timestamp');
    this.payloadTextarea = page.getByTestId('event-test-payload');
    this.runButton = page.getByTestId('event-test-run');
    this.resetButton = page.getByTestId('event-test-reset');
    this.resolvedOutcome = page.getByTestId('event-test-resolved-outcome');
    this.matchedCount = page.getByTestId('event-test-matched-count');
    this.ledgerState = page.getByTestId('event-test-ledger-state');
    this.ruleResults = page.getByTestId('event-test-rule-result');
    this.errorMessage = page.getByTestId('event-test-error');
  }

  async goto() {
    await this.page.goto('/event-tester');
  }

  async runTest(eventId: string, payload: Record<string, unknown>) {
    await this.eventIdInput.fill(eventId);
    await this.payloadTextarea.fill(JSON.stringify(payload, null, 2));
    await this.runButton.click();
  }
}
