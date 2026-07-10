# E2E Tests for ezrules Angular Frontend

This directory contains end-to-end (E2E) tests for the ezrules Angular frontend using Playwright.

## Quick Start

Preferred: use the repo agent stack helper so ports and env vars stay aligned.

```bash
docker compose up -d postgres redis mailpit
./scripts/start-agent-stack.sh
source .env.agent-stack
cd ezrules/frontend
npm run test:e2e
./scripts/stop-agent-stack.sh
```

Manual setup with custom ports (all four values must match):

```bash
# Example high ports — pick unused ports if these are taken
API_PORT=38888
FRONTEND_PORT=44200

# 1. Make sure the API service is running
EZRULES_TESTING=false \
EZRULES_SMTP_HOST=localhost \
EZRULES_SMTP_PORT=1025 \
EZRULES_FROM_EMAIL=no-reply@ezrules.local \
EZRULES_APP_BASE_URL=http://localhost:$FRONTEND_PORT \
EZRULES_CORS_ALLOWED_ORIGINS=http://localhost:$FRONTEND_PORT \
uv run ezrules api --port $API_PORT

# 2. Make sure Angular dev server is running
cd ezrules/frontend
EZRULES_FRONTEND_API_URL=http://localhost:$API_PORT \
npm start -- --port $FRONTEND_PORT

# 3. Run E2E tests
cd ezrules/frontend
E2E_BASE_URL=http://localhost:$FRONTEND_PORT \
E2E_API_BASE_URL=http://localhost:$API_PORT \
npm run test:e2e
```

## Directory Structure

```
e2e/
├── tests/           # Test specifications
├── pages/           # Page Object Models
├── support/         # Shared config, API helpers, fixtures, and deterministic test data
└── README.md        # This file
```

## What's Tested

Current coverage includes:
- Authentication and login
- Rule management pages
- Rule quality analytics page
- Security pages (roles/users/API keys/audit trail)
- Invite + password reset flows, including Mailpit email delivery assertions

## Prerequisites

Before running E2E tests, you need to have the following services running:

1. **API Service**: The unified API service (includes rule evaluation)
   ```bash
   # Terminal 1: Start API service
   # Important: invite/reset tests require TESTING=false because TESTING=true skips SMTP sends.
   API_PORT=38888
   FRONTEND_PORT=44200
   EZRULES_TESTING=false \
   EZRULES_SMTP_HOST=localhost \
   EZRULES_SMTP_PORT=1025 \
   EZRULES_FROM_EMAIL=no-reply@ezrules.local \
   EZRULES_APP_BASE_URL=http://localhost:$FRONTEND_PORT \
   EZRULES_CORS_ALLOWED_ORIGINS=http://localhost:$FRONTEND_PORT \
   uv run ezrules api --port $API_PORT
   ```

2. **Angular Dev Server**: Frontend application
   ```bash
   # Terminal 2: Start Angular dev server
   cd ezrules/frontend
   EZRULES_FRONTEND_API_URL=http://localhost:$API_PORT \
   npm start -- --port $FRONTEND_PORT
   ```

3. **Mailpit**: Required for invite/reset email E2E tests
   ```bash
   # Terminal 3: start local infrastructure (includes mailpit on :8025)
   docker compose up -d postgres redis mailpit
   ```

4. **Playwright Browsers**: Install Playwright browsers (first time only)
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

# Run stateful specs with repeats
npm run test:e2e -- --grep "@stateful" --project=chromium --workers=1 --repeat-each=5

# Run a specific test by line number
npm run test:e2e -- rule-list.spec.ts:42
```

### Endpoint Overrides

If your frontend, API, or Mailpit runs on non-default hosts/ports, set:

```bash
E2E_BASE_URL=http://localhost:4200 \
E2E_API_BASE_URL=http://localhost:8888 \
E2E_MAILPIT_BASE_URL=http://localhost:8025 \
npm run test:e2e -- auth-email-flows.spec.ts
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
import { test, expect } from '../support/fixtures';
import { YourPage } from '../pages/your-page.page';
import { testResourceName } from '../support/test-data';

test.describe('Your Feature', () => {
  let yourPage: YourPage;

  test.beforeEach(async ({ page }) => {
    yourPage = new YourPage(page);
    await yourPage.goto();
  });

  test('should do something', async () => {
    // Arrange
    await yourPage.waitForPageLoad();
    const name = testResourceName(test.info(), 'E2E_RESOURCE');

    // Act
    await yourPage.createSomething(name);

    // Assert
    await expect(yourPage.rowFor(name)).toBeVisible();
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

- **Base URL**: `E2E_BASE_URL` (defaults to `http://localhost:4200`)
- **Timeout**: 30s per test
- **Retries**: 2 on CI, 0 locally
- **Workers**: 1 locally, 4 on CI
- **Browsers**: Chromium (Firefox and WebKit available)
- **Screenshots**: On failure only
- **Videos**: Retained on failure
- **Traces**: Retained on failure
- **Diagnostics**: Specs importing `../support/fixtures` attach console errors, page errors, failed requests, and failed API response bodies on failure

## CI/CD Integration

Tests can be integrated into CI/CD pipelines. Example GitHub Actions workflow:

```yaml
- name: Start API service
  run: |
    uv run ezrules api --port 8888 &
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

1. **Add event-based waits**: Wait for responses, URL changes, toast text, modal close, row counts, or polling status instead of fixed sleeps
2. **Check network timing**: Ensure API responses are awaited
3. **Use deterministic data**: Build names with `testResourceName(test.info(), ...)` so cleanup failures are easy to find
4. **Tag stateful specs**: Add `@stateful` to settings/auth/global-order/data-mutating specs so they can be repeated with `--grep`
5. **Increase timeout**: For slow operations, use `test.setTimeout(60000)`

### "Connection refused" errors

- Ensure the API service is running and healthy
- Check service logs in `/tmp/ezrules-*.log`
- Verify ports are not in use by other processes
- Run `./scripts/verify-stack.sh` after changing ports

### Login fails but API responds to curl

Likely a frontend/API topology mismatch rather than a bad password.

1. Confirm `ezrules/frontend/public/runtime-config.js` points at the API port you started
2. Confirm `EZRULES_CORS_ALLOWED_ORIGINS` includes the frontend origin (for example `http://localhost:44200`)
3. Run `./scripts/verify-stack.sh`
4. In the browser DevTools Network tab, check whether the login request is blocked by CORS or sent to the wrong host/port

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
6. **Wait explicitly**: Don't use `sleep()`, use event-based waits or page-object wait helpers
7. **Clean with API helpers**: Use `e2e/support/api-helpers.ts` for setup/cleanup such as rules, labels, user lists, field types, runtime settings, and outcome order
8. **Assert restoration**: Specs that mutate shared state should restore the original value and assert it was restored
9. **Test user workflows**: Focus on real user journeys, not implementation details

## Resources

- [Playwright Documentation](https://playwright.dev)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Page Object Model Pattern](https://playwright.dev/docs/pom)
- [Debugging Guide](https://playwright.dev/docs/debug)
