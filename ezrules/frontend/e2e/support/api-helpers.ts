import type { APIRequestContext, APIResponse } from '@playwright/test';
import { expect } from '@playwright/test';
import { getApiBaseUrl, getAuthToken } from './config';

const API_BASE = getApiBaseUrl();

type RuntimeSettings = {
  auto_promote_active_rule_updates: boolean;
  strict_mode_enabled: boolean;
  main_rule_execution_mode: string;
  rule_quality_lookback_days: number;
  neutral_outcome: string;
};

type AIAuthoringSettings = {
  provider: string;
  enabled: boolean;
  model: string;
  api_key_configured: boolean;
};

type OutcomeHierarchy = {
  outcomes: { ao_id: number; outcome_name: string; severity_rank: number }[];
};

export type CreatedRule = {
  r_id: number;
  rid: string;
  description: string;
  logic: string;
  status: string;
};

export type CreatedUserList = {
  id: number;
  name: string;
  entry_count: number;
};

function authHeaders() {
  return { Authorization: `Bearer ${getAuthToken()}` };
}

function truncateBody(body: string): string {
  return body.length > 4_000 ? `${body.slice(0, 4_000)}... [truncated]` : body;
}

async function responseBody(response: APIResponse): Promise<string> {
  try {
    return truncateBody(await response.text());
  } catch (error) {
    return `[body unavailable: ${String(error)}]`;
  }
}

export async function expectApiOk(response: APIResponse, context: string): Promise<void> {
  if (response.ok()) {
    return;
  }

  throw new Error(`${context} failed with HTTP ${response.status()}: ${await responseBody(response)}`);
}

async function jsonResponse<T>(response: APIResponse, context: string): Promise<T> {
  await expectApiOk(response, context);
  return (await response.json()) as T;
}

async function deleteIgnoringMissing(response: APIResponse, context: string): Promise<void> {
  if (response.ok() || response.status() === 404) {
    return;
  }

  throw new Error(`${context} failed with HTTP ${response.status()}: ${await responseBody(response)}`);
}

export async function createRule(
  request: APIRequestContext,
  data: { rid: string; description?: string; logic?: string; evaluation_lane?: string; execution_order?: number }
): Promise<CreatedRule> {
  const response = await request.post(`${API_BASE}/api/v2/rules`, {
    headers: authHeaders(),
    data: {
      description: 'E2E rule created by Playwright',
      logic: "if $amount > 100:\n\treturn !HOLD",
      ...data,
    },
  });
  const body = await jsonResponse<{ success: boolean; rule?: CreatedRule; error?: string }>(response, 'Create rule');
  if (!body.success || !body.rule?.r_id) {
    throw new Error(`Create rule returned an unsuccessful body: ${JSON.stringify(body)}`);
  }
  return body.rule;
}

export async function promoteRule(request: APIRequestContext, ruleId: number): Promise<void> {
  const response = await request.post(`${API_BASE}/api/v2/rules/${ruleId}/promote`, {
    headers: authHeaders(),
  });
  await expectApiOk(response, `Promote rule ${ruleId}`);
}

export async function deleteRuleById(request: APIRequestContext, ruleId: number): Promise<void> {
  const response = await request.delete(`${API_BASE}/api/v2/rules/${ruleId}`, {
    headers: authHeaders(),
  });
  await deleteIgnoringMissing(response, `Delete rule ${ruleId}`);
}

export async function deleteRuleByRid(request: APIRequestContext, rid: string): Promise<void> {
  const response = await request.get(`${API_BASE}/api/v2/rules`, { headers: authHeaders() });
  const body = await jsonResponse<{ rules: CreatedRule[] }>(response, `Find rule ${rid}`);
  const rule = body.rules.find(candidate => candidate.rid === rid);
  if (rule) {
    await deleteRuleById(request, rule.r_id);
  }
}

export async function createUserList(request: APIRequestContext, name: string): Promise<CreatedUserList> {
  const response = await request.post(`${API_BASE}/api/v2/user-lists`, {
    headers: authHeaders(),
    data: { name },
  });
  const body = await jsonResponse<{ success: boolean; list?: CreatedUserList; error?: string }>(
    response,
    `Create user list ${name}`
  );
  if (!body.success || !body.list?.id) {
    throw new Error(`Create user list returned an unsuccessful body: ${JSON.stringify(body)}`);
  }
  return body.list;
}

export async function createUserListEntry(
  request: APIRequestContext,
  listId: number,
  value: string
): Promise<{ id: number; value: string }> {
  const response = await request.post(`${API_BASE}/api/v2/user-lists/${listId}/entries`, {
    headers: authHeaders(),
    data: { value },
  });
  const body = await jsonResponse<{ success: boolean; entry?: { id: number; value: string }; error?: string }>(
    response,
    `Create entry ${value} in user list ${listId}`
  );
  if (!body.success || !body.entry?.id) {
    throw new Error(`Create user-list entry returned an unsuccessful body: ${JSON.stringify(body)}`);
  }
  return body.entry;
}

export async function deleteUserListById(request: APIRequestContext, listId: number): Promise<void> {
  const response = await request.delete(`${API_BASE}/api/v2/user-lists/${listId}`, {
    headers: authHeaders(),
  });
  await deleteIgnoringMissing(response, `Delete user list ${listId}`);
}

export async function deleteUserListByName(request: APIRequestContext, name: string): Promise<void> {
  const response = await request.get(`${API_BASE}/api/v2/user-lists`, { headers: authHeaders() });
  const body = await jsonResponse<{ lists: CreatedUserList[] }>(response, `Find user list ${name}`);
  const list = body.lists.find(candidate => candidate.name === name);
  if (list) {
    await deleteUserListById(request, list.id);
  }
}

export async function createLabel(request: APIRequestContext, name: string): Promise<{ el_id: number; label: string }> {
  const response = await request.post(`${API_BASE}/api/v2/labels`, {
    headers: authHeaders(),
    data: { label_name: name },
  });
  const body = await jsonResponse<{ success: boolean; label?: { el_id: number; label: string }; error?: string }>(
    response,
    `Create label ${name}`
  );
  if (!body.success || !body.label?.el_id) {
    throw new Error(`Create label returned an unsuccessful body: ${JSON.stringify(body)}`);
  }
  return body.label;
}

export async function deleteLabelByName(request: APIRequestContext, name: string): Promise<void> {
  const response = await request.delete(`${API_BASE}/api/v2/labels/${encodeURIComponent(name)}`, {
    headers: authHeaders(),
  });
  await deleteIgnoringMissing(response, `Delete label ${name}`);
}

export async function deleteFieldTypeByName(request: APIRequestContext, fieldName: string): Promise<void> {
  const response = await request.delete(`${API_BASE}/api/v2/field-types/${encodeURIComponent(fieldName)}`, {
    headers: authHeaders(),
  });
  await deleteIgnoringMissing(response, `Delete field type ${fieldName}`);
}

export async function getRuntimeSettings(request: APIRequestContext): Promise<RuntimeSettings> {
  const response = await request.get(`${API_BASE}/api/v2/settings/runtime`, { headers: authHeaders() });
  return await jsonResponse<RuntimeSettings>(response, 'Get runtime settings');
}

export async function restoreRuntimeSettings(
  request: APIRequestContext,
  settings: RuntimeSettings
): Promise<RuntimeSettings> {
  const response = await request.put(`${API_BASE}/api/v2/settings/runtime`, {
    headers: authHeaders(),
    data: {
      auto_promote_active_rule_updates: settings.auto_promote_active_rule_updates,
      strict_mode_enabled: settings.strict_mode_enabled,
      main_rule_execution_mode: settings.main_rule_execution_mode,
      rule_quality_lookback_days: settings.rule_quality_lookback_days,
      neutral_outcome: settings.neutral_outcome,
    },
  });
  return await jsonResponse<RuntimeSettings>(response, 'Restore runtime settings');
}

export async function expectRuntimeSettingsRestored(
  request: APIRequestContext,
  expected: RuntimeSettings
): Promise<void> {
  const actual = await getRuntimeSettings(request);
  expect(actual.auto_promote_active_rule_updates).toBe(expected.auto_promote_active_rule_updates);
  expect(actual.strict_mode_enabled).toBe(expected.strict_mode_enabled);
  expect(actual.main_rule_execution_mode).toBe(expected.main_rule_execution_mode);
  expect(actual.rule_quality_lookback_days).toBe(expected.rule_quality_lookback_days);
  expect(actual.neutral_outcome).toBe(expected.neutral_outcome);
}

export async function getAIAuthoringSettings(request: APIRequestContext): Promise<AIAuthoringSettings> {
  const response = await request.get(`${API_BASE}/api/v2/settings/ai-authoring`, { headers: authHeaders() });
  return await jsonResponse<AIAuthoringSettings>(response, 'Get AI authoring settings');
}

export async function restoreAIAuthoringSettings(
  request: APIRequestContext,
  settings: AIAuthoringSettings
): Promise<AIAuthoringSettings> {
  const response = await request.put(`${API_BASE}/api/v2/settings/ai-authoring`, {
    headers: authHeaders(),
    data: {
      provider: settings.provider,
      enabled: settings.api_key_configured ? settings.enabled : false,
      model: settings.model,
      clear_api_key: settings.api_key_configured ? undefined : true,
    },
  });
  return await jsonResponse<AIAuthoringSettings>(response, 'Restore AI authoring settings');
}

export async function getOutcomeHierarchy(request: APIRequestContext): Promise<OutcomeHierarchy> {
  const response = await request.get(`${API_BASE}/api/v2/settings/outcome-hierarchy`, { headers: authHeaders() });
  return await jsonResponse<OutcomeHierarchy>(response, 'Get outcome hierarchy');
}

export async function restoreOutcomeHierarchy(
  request: APIRequestContext,
  hierarchy: OutcomeHierarchy
): Promise<OutcomeHierarchy> {
  const response = await request.put(`${API_BASE}/api/v2/settings/outcome-hierarchy`, {
    headers: authHeaders(),
    data: { ordered_ao_ids: hierarchy.outcomes.map(outcome => outcome.ao_id) },
  });
  return await jsonResponse<OutcomeHierarchy>(response, 'Restore outcome hierarchy');
}
