import { Locator, Page } from '@playwright/test';

export class AiRuleAuthoringPanel {
  readonly page: Page;
  readonly panel: Locator;
  readonly promptTextarea: Locator;
  readonly toggleButton: Locator;
  readonly generateButton: Locator;
  readonly applyButton: Locator;
  readonly result: Locator;
  readonly statusBadge: Locator;
  readonly errorBanner: Locator;
  readonly appliedBanner: Locator;
  readonly explanations: Locator;

  constructor(page: Page) {
    this.page = page;
    this.panel = page.getByTestId('ai-rule-authoring-panel');
    this.promptTextarea = page.getByTestId('ai-rule-authoring-prompt');
    this.toggleButton = page.getByTestId('ai-rule-authoring-toggle');
    this.generateButton = page.getByTestId('ai-rule-authoring-generate');
    this.applyButton = page.getByTestId('ai-rule-authoring-apply');
    this.result = page.getByTestId('ai-rule-authoring-result');
    this.statusBadge = page.getByTestId('ai-rule-authoring-status');
    this.errorBanner = page.getByTestId('ai-rule-authoring-error');
    this.appliedBanner = page.getByTestId('ai-rule-authoring-applied');
    this.explanations = page.getByTestId('ai-rule-authoring-explanation');
  }

  async fillPrompt(value: string) {
    await this.promptTextarea.fill(value);
  }

  async clickGenerate() {
    await this.generateButton.click();
  }

  async toggle() {
    await this.toggleButton.click();
  }

  async clickApply() {
    await this.applyButton.click();
  }
}
