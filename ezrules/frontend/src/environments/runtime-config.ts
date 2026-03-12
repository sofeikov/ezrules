type EzrulesRuntimeConfig = {
  apiUrl?: string;
};

type GlobalWithRuntimeConfig = typeof globalThis & {
  __EZRULES_RUNTIME_CONFIG__?: EzrulesRuntimeConfig;
};

export function resolveRuntimeApiUrl(defaultApiUrl: string): string {
  const runtimeConfig = (globalThis as GlobalWithRuntimeConfig).__EZRULES_RUNTIME_CONFIG__;
  const apiUrl = runtimeConfig?.apiUrl?.trim();
  return apiUrl && apiUrl.length > 0 ? apiUrl : defaultApiUrl;
}
