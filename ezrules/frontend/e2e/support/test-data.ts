import type { TestInfo } from '@playwright/test';

type ResourceNameOptions = {
  maxLength?: number;
  uppercase?: boolean;
};

function testInfoId(testInfo: TestInfo): string {
  const candidate = (testInfo as TestInfo & { testId?: string }).testId;
  if (candidate) {
    return candidate;
  }

  const titlePath = (testInfo as unknown as { titlePath?: string[] | (() => string[]) }).titlePath;
  if (Array.isArray(titlePath)) {
    return titlePath.join(' ');
  }
  if (typeof titlePath === 'function') {
    return titlePath().join(' ');
  }
  return testInfo.title;
}

function compactToken(value: string, maxLength: number): string {
  const normalized = value
    .normalize('NFKD')
    .replace(/[^\w]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/_{2,}/g, '_');
  const fallback = normalized || 'test';
  return fallback.slice(0, maxLength).replace(/_+$/g, '') || 'test';
}

export function sanitizeTestToken(value: string, maxLength = 48): string {
  return compactToken(value, maxLength);
}

export function testResourceName(
  testInfo: TestInfo,
  prefix: string,
  { maxLength = 64, uppercase = false }: ResourceNameOptions = {}
): string {
  const suffixBudget = Math.max(8, maxLength - prefix.length - 1);
  const repeatSuffix = testInfo.repeatEachIndex > 0 ? `_repeat_${testInfo.repeatEachIndex}` : '';
  const retrySuffix = testInfo.retry > 0 ? `_retry_${testInfo.retry}` : '';
  const suffix = compactToken(`${testInfoId(testInfo)}${repeatSuffix}${retrySuffix}`, suffixBudget);
  const name = `${prefix}_${suffix}`.slice(0, maxLength).replace(/_+$/g, '');
  return uppercase ? name.toUpperCase() : name;
}

export function deterministicUnixTimestamp(testInfo: TestInfo, baseTimestamp = 1_893_456_000): number {
  const source = testInfoId(testInfo);
  let hash = 0;
  for (let index = 0; index < source.length; index += 1) {
    hash = (hash * 31 + source.charCodeAt(index)) % 86_400;
  }
  return baseTimestamp + hash + testInfo.repeatEachIndex * 1_000 + testInfo.retry;
}
