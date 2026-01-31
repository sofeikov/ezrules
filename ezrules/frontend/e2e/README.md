# E2E Tests for ezrules Angular Frontend

This directory contains end-to-end (E2E) tests for the ezrules Angular frontend using Playwright.

## Quick Start

```bash
# 1. Make sure backend services are running (in separate terminals)
uv run ezrules manager --port 8888
uv run ezrules evaluator --port 9999

# 2. Make sure Angular dev server is running
cd ezrules/frontend
npm start

# 3. Run E2E tests
cd ezrules/frontend
npm run test:e2e
```

## Directory Structure

```
e2e/
├── tests/           # Test specifications
├── pages/           # Page Object Models
└── README.md        # This file
```

## What's Tested

Currently tests only the **implemented features**:
- Rule list page display (from `/api/rules` endpoint)
- Loading states
- Table rendering with rule data
- "How to Run" section toggle
- Responsive design

Navigation and other pages are not yet implemented, so they're not tested.

## Prerequisites

Before running E2E tests, you need to have the following services running:

1. **Backend Services**: Manager and Evaluator services
   ```bash
   # Terminal 1: Start Manager service
   uv run ezrules manager --port 8888

   # Terminal 2: Start Evaluator service
   uv run ezrules evaluator --port 9999
   ```

2. **Angular Dev Server**: Frontend application
   ```bash
   # Terminal 3: Start Angular dev server
   cd ezrules/frontend
   npm start
   ```

3. **Playwright Browsers**: Install Playwright browsers (first time only)
   ```bash
   cd ezrules/frontend
   npx playwright install chromium
   ```

## Running Tests

Once all prerequisites are running, navigate to the frontend directory and run tests:

```bash
cd ezrules/frontend

# Run all tests (headless)
npm run test:e2e

# Run with UI mode (best for development/debugging)
npm run test:e2e:ui

# Run with browser visible
npm run test:e2e:headed

# Run in debug mode
npm run test:e2e:debug

# View last test report
npm run test:e2e:report
```

### Running Specific Tests

```bash
cd ezrules/frontend

# Run only rule-list tests
npm run test:e2e -- rule-list.spec.ts

# Run tests matching a pattern
npm run test:e2e -- --grep "should display"

# Run a specific test by line number
npm run test:e2e -- rule-list.spec.ts:42
```

## Test Organization

### Page Object Models (POM)

Located in `e2e/pages/`, these encapsulate page interactions:

- **rule-list.page.ts**: Interactions with the Rules list page

Example usage:
```typescript
import { RuleListPage } from '../pages/rule-list.page';

test('example test', async ({ page }) => {
  const rulePage = new RuleListPage(page);
  await rulePage.goto();
  await rulePage.waitForRulesToLoad();
  const count = await rulePage.getRuleCount();
});
```

## Writing New Tests

1. **Create test file** in `e2e/tests/` with `.spec.ts` extension
2. **Use Page Objects** for all page interactions (don't use raw selectors in tests)
3. **Organize tests** using `test.describe()` blocks
4. **Add meaningful descriptions** to each test
5. **Use beforeEach/afterEach** for setup/cleanup

Example template:
```typescript
import { test, expect } from '@playwright/test';
import { YourPage } from '../pages/your-page.page';

test.describe('Your Feature', () => {
  let yourPage: YourPage;

  test.beforeEach(async ({ page }) => {
    yourPage = new YourPage(page);
    await yourPage.goto();
  });

  test('should do something', async () => {
    // Arrange
    await yourPage.waitForPageLoad();

    // Act
    await yourPage.clickSomething();

    // Assert
    await expect(yourPage.someElement).toBeVisible();
  });
});
```

## Debugging Tests

### UI Mode (Recommended)

The best way to debug tests interactively:

```bash
npm run test:e2e:ui
```

This opens the Playwright UI where you can:
- Run tests step-by-step
- Inspect the DOM
- Time-travel through test execution
- See network requests
- View console logs

### Debug Mode

Run tests with browser DevTools:

```bash
npm run test:e2e:debug
```

### Headed Mode

Run with browser visible (non-headless):

```bash
npm run test:e2e:headed
```

### VSCode Debugging

Install the [Playwright VSCode extension](https://marketplace.visualstudio.com/items?itemName=ms-playwright.playwright) for:
- Test explorer integration
- Breakpoint debugging
- Running tests from editor

## Test Configuration

Main configuration is in `playwright.config.ts`:

- **Base URL**: `http://localhost:4200`
- **Timeout**: 30s per test
- **Retries**: 2 on CI, 0 locally
- **Workers**: 4 parallel (1 on CI)
- **Browsers**: Chromium (Firefox and WebKit available)
- **Screenshots**: On failure only
- **Videos**: Retained on failure
- **Traces**: On first retry

## CI/CD Integration

Tests can be integrated into CI/CD pipelines. Example GitHub Actions workflow:

```yaml
- name: Start backend services
  run: |
    uv run ezrules manager --port 8888 &
    uv run ezrules evaluator --port 9999 &
    sleep 5

- name: Start Angular dev server
  run: |
    cd ezrules/frontend
    npm start &
    sleep 10

- name: Install Playwright browsers
  run: |
    cd ezrules/frontend
    npx playwright install --with-deps chromium

- name: Run E2E tests
  run: |
    cd ezrules/frontend
    npm run test:e2e
```

## Troubleshooting

### Tests are flaky

1. **Add explicit waits**: Use `waitFor()` instead of fixed `sleep()`
2. **Check network timing**: Ensure API responses are awaited
3. **Increase timeout**: For slow operations, use `test.setTimeout(60000)`

### "Connection refused" errors

- Ensure all backend services are running and healthy
- Check service logs in `/tmp/ezrules-*.log`
- Verify ports are not in use by other processes

### "Element not found" errors

- Use Page Object Methods instead of raw selectors
- Add proper waits before interactions
- Check if element is in viewport
- Verify element isn't in a shadow DOM

### Tests pass locally but fail in CI

- Check CI environment variables
- Ensure database is properly seeded
- Increase timeouts for slower CI environments
- Check for race conditions

## Best Practices

1. **Use Page Objects**: Never use raw selectors in test files
2. **No mocking**: Tests interact with real backend APIs
3. **Clean state**: Each test should be independent
4. **Descriptive names**: Test names should describe expected behavior
5. **Arrange-Act-Assert**: Follow AAA pattern in tests
6. **Wait explicitly**: Don't use `sleep()`, use `waitFor()` methods
7. **Test user workflows**: Focus on real user journeys, not implementation details

## Resources

- [Playwright Documentation](https://playwright.dev)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Page Object Model Pattern](https://playwright.dev/docs/pom)
- [Debugging Guide](https://playwright.dev/docs/debug)
