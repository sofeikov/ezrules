import { resolveRuntimeApiUrl } from './runtime-config';
import { environment as developmentEnvironment } from './environment';
import { environment as productionEnvironment } from './environment.production';

type RuntimeConfigGlobal = typeof globalThis & {
  __EZRULES_RUNTIME_CONFIG__?: {
    apiUrl?: string;
  };
};

describe('resolveRuntimeApiUrl', () => {
  const runtimeGlobal = globalThis as RuntimeConfigGlobal;

  afterEach(() => {
    delete runtimeGlobal.__EZRULES_RUNTIME_CONFIG__;
  });

  it('uses the provided runtime api url when present', () => {
    runtimeGlobal.__EZRULES_RUNTIME_CONFIG__ = { apiUrl: 'https://api.example.com' };

    expect(resolveRuntimeApiUrl('')).toBe('https://api.example.com');
  });

  it('falls back to the supplied default when runtime config is absent', () => {
    expect(resolveRuntimeApiUrl('')).toBe('');
    expect(resolveRuntimeApiUrl('http://localhost:8888')).toBe('http://localhost:8888');
  });

  it('keeps the expected development and production defaults', () => {
    expect(developmentEnvironment.production).toBeFalse();
    expect(developmentEnvironment.apiUrl).toBe('http://localhost:8888');
    expect(productionEnvironment.production).toBeTrue();
    expect(productionEnvironment.apiUrl).toBe('');
  });
});
