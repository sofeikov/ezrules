import { readFileSync } from 'fs';
import { join } from 'path';
import { APIRequestContext, expect, test } from '@playwright/test';
import { AcceptInvitePage } from '../pages/accept-invite.page';
import { ForgotPasswordPage } from '../pages/forgot-password.page';
import { LoginPage } from '../pages/login.page';
import { ResetPasswordPage } from '../pages/reset-password.page';
import { UserManagementPage } from '../pages/user-management.page';

const API_BASE = process.env.E2E_API_BASE_URL ?? 'http://localhost:8888';
const MAILPIT_BASE = process.env.E2E_MAILPIT_BASE_URL ?? 'http://localhost:8025';

type MailpitMessage = {
  id: string;
  subject: string;
  to: string;
};

/** Read the JWT access token from the saved auth state file. */
function getAuthToken(): string {
  const state = JSON.parse(readFileSync(join(__dirname, '../.auth/user.json'), 'utf-8'));
  const origin = state.origins?.find((o: any) => o.origin === 'http://localhost:4200');
  return origin?.localStorage?.find((e: any) => e.name === 'ezrules_access_token')?.value ?? '';
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseMessages(payload: any): any[] {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (Array.isArray(payload?.messages)) {
    return payload.messages;
  }
  if (Array.isArray(payload?.Messages)) {
    return payload.Messages;
  }
  return [];
}

function toText(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  return typeof value === 'string' ? value : JSON.stringify(value);
}

function normalizeSummary(message: any): MailpitMessage {
  return {
    id: String(message?.ID ?? message?.id ?? message?.MessageID ?? ''),
    subject: toText(message?.Subject ?? message?.subject),
    to: toText(message?.To ?? message?.to ?? message?.Recipients ?? message?.recipients),
  };
}

function extractLink(messageDetails: any, routePath: 'accept-invite' | 'reset-password'): string {
  const flattened = JSON.stringify(messageDetails).replace(/\\\//g, '/');
  const matcher = new RegExp(`https?://[^\\s"]+/${routePath}\\?token=[A-Za-z0-9._~-]+`);
  const match = flattened.match(matcher);
  if (!match?.[0]) {
    throw new Error(`Failed to find ${routePath} link in message payload`);
  }
  return match[0];
}

async function clearMailpitInbox(request: APIRequestContext): Promise<void> {
  await request.delete(`${MAILPIT_BASE}/api/v1/messages`);
}

async function waitForMailpitMessage(
  request: APIRequestContext,
  recipientEmail: string,
  subjectContains: string,
  timeoutMs: number = 20000
): Promise<MailpitMessage> {
  const emailNeedle = recipientEmail.toLowerCase();
  const subjectNeedle = subjectContains.toLowerCase();
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const response = await request.get(`${MAILPIT_BASE}/api/v1/messages`);
    if (response.ok()) {
      const payload = await response.json();
      const messages = parseMessages(payload).map(normalizeSummary);
      const found = messages.find((message) => message.to.toLowerCase().includes(emailNeedle) && message.subject.toLowerCase().includes(subjectNeedle));
      if (found?.id) {
        return found;
      }
    }
    await sleep(750);
  }

  throw new Error(`Timed out waiting for mail "${subjectContains}" to ${recipientEmail}`);
}

async function fetchMailpitMessageDetails(request: APIRequestContext, messageId: string): Promise<any> {
  const response = await request.get(`${MAILPIT_BASE}/api/v1/message/${messageId}`);
  if (!response.ok()) {
    throw new Error(`Failed to fetch Mailpit message ${messageId}: HTTP ${response.status()}`);
  }
  return response.json();
}

async function createUserViaApi(request: APIRequestContext, email: string, password: string): Promise<void> {
  const response = await request.post(`${API_BASE}/api/v2/users`, {
    headers: { Authorization: `Bearer ${getAuthToken()}` },
    data: { email, password },
  });
  if (!response.ok()) {
    throw new Error(`Failed to create user ${email}: HTTP ${response.status()}`);
  }
  const payload = await response.json();
  if (!payload.success) {
    throw new Error(`Failed to create user ${email}: ${JSON.stringify(payload)}`);
  }
}

async function deleteUserByEmail(request: APIRequestContext, email: string): Promise<void> {
  const listResponse = await request.get(`${API_BASE}/api/v2/users`, {
    headers: { Authorization: `Bearer ${getAuthToken()}` },
  });
  if (!listResponse.ok()) {
    return;
  }

  const payload = await listResponse.json();
  const users = Array.isArray(payload?.users) ? payload.users : [];
  const target = users.find((user: any) => String(user?.email ?? '').toLowerCase() === email.toLowerCase());
  if (!target?.id) {
    return;
  }

  await request.delete(`${API_BASE}/api/v2/users/${target.id}`, {
    headers: { Authorization: `Bearer ${getAuthToken()}` },
  });
}

test.describe('Auth Email Flows', () => {
  const createdEmails: string[] = [];

  test.afterEach(async ({ request }) => {
    while (createdEmails.length > 0) {
      const email = createdEmails.pop();
      if (email) {
        await deleteUserByEmail(request, email);
      }
    }
  });

  test('should send invite email and allow accepting the invitation', async ({ browser, page, request }) => {
    const userManagementPage = new UserManagementPage(page);
    const inviteEmail = `e2e_invite_${Date.now()}@example.com`;
    const invitePassword = `InvitePass_${Date.now()}`;
    createdEmails.push(inviteEmail);

    await clearMailpitInbox(request);
    await userManagementPage.goto();
    await userManagementPage.waitForUsersToLoad();
    await userManagementPage.inviteUser(inviteEmail);
    await expect(userManagementPage.inviteSuccessMessage).toContainText(`Invitation sent to ${inviteEmail}`);

    const mailSummary = await waitForMailpitMessage(request, inviteEmail, 'invited');
    const messageDetails = await fetchMailpitMessageDetails(request, mailSummary.id);
    const inviteLink = extractLink(messageDetails, 'accept-invite');

    const guestContext = await browser.newContext({ storageState: { cookies: [], origins: [] } });
    const guestPage = await guestContext.newPage();
    const acceptInvitePage = new AcceptInvitePage(guestPage);
    const loginPage = new LoginPage(guestPage);

    await acceptInvitePage.gotoByUrl(inviteLink);
    await expect(acceptInvitePage.heading).toHaveText('Accept Invitation');
    await acceptInvitePage.accept(invitePassword);
    await expect(acceptInvitePage.successMessage).toContainText('Invitation accepted');

    await loginPage.goto();
    await loginPage.login(inviteEmail, invitePassword);
    await expect(guestPage).toHaveURL(/.*dashboard/, { timeout: 10000 });

    await guestContext.close();
  });

  test('should send reset email and allow resetting password from email link', async ({ browser, request }) => {
    const resetEmail = `e2e_reset_${Date.now()}@example.com`;
    const originalPassword = `OriginalPass_${Date.now()}`;
    const newPassword = `ResetPass_${Date.now()}`;
    createdEmails.push(resetEmail);

    await createUserViaApi(request, resetEmail, originalPassword);
    await clearMailpitInbox(request);

    const guestContext = await browser.newContext({ storageState: { cookies: [], origins: [] } });
    const guestPage = await guestContext.newPage();
    const forgotPasswordPage = new ForgotPasswordPage(guestPage);
    const resetPasswordPage = new ResetPasswordPage(guestPage);
    const loginPage = new LoginPage(guestPage);

    await forgotPasswordPage.goto();
    await expect(forgotPasswordPage.heading).toHaveText('Forgot Password');
    await forgotPasswordPage.requestReset(resetEmail);
    await expect(forgotPasswordPage.successMessage).toContainText('If an account with that email exists');

    const mailSummary = await waitForMailpitMessage(request, resetEmail, 'reset your ezrules password');
    const messageDetails = await fetchMailpitMessageDetails(request, mailSummary.id);
    const resetLink = extractLink(messageDetails, 'reset-password');

    await resetPasswordPage.gotoByUrl(resetLink);
    await expect(resetPasswordPage.heading).toHaveText('Reset Password');
    await resetPasswordPage.reset(newPassword);
    await expect(resetPasswordPage.successMessage).toContainText('Password has been reset successfully');

    await loginPage.goto();
    await loginPage.login(resetEmail, newPassword);
    await expect(guestPage).toHaveURL(/.*dashboard/, { timeout: 10000 });

    await guestContext.close();
  });
});
