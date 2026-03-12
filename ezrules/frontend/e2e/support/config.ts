import { readFileSync } from 'fs';
import { join } from 'path';

type StorageEntry = {
  name?: string;
  value?: string;
};

type StorageOrigin = {
  origin?: string;
  localStorage?: StorageEntry[];
};

type StorageState = {
  origins?: StorageOrigin[];
};

const DEFAULT_FRONTEND_BASE_URL = 'http://localhost:4200';
const DEFAULT_API_BASE_URL = 'http://localhost:8888';
const DEFAULT_MAILPIT_BASE_URL = 'http://localhost:8025';
const ACCESS_TOKEN_STORAGE_KEY = 'ezrules_access_token';

export function getFrontendBaseUrl(): string {
  return process.env.E2E_BASE_URL ?? DEFAULT_FRONTEND_BASE_URL;
}

export function getFrontendOrigin(): string {
  return new URL(getFrontendBaseUrl()).origin;
}

export function getApiBaseUrl(): string {
  return process.env.E2E_API_BASE_URL ?? DEFAULT_API_BASE_URL;
}

export function getMailpitBaseUrl(): string {
  return process.env.E2E_MAILPIT_BASE_URL ?? DEFAULT_MAILPIT_BASE_URL;
}

function readStorageState(): StorageState {
  return JSON.parse(readFileSync(join(__dirname, '../.auth/user.json'), 'utf-8')) as StorageState;
}

function findAccessToken(origin: StorageOrigin | undefined): string {
  if (!origin || !Array.isArray(origin.localStorage)) {
    return '';
  }

  return origin.localStorage.find((entry) => entry.name === ACCESS_TOKEN_STORAGE_KEY)?.value ?? '';
}

export function getAuthToken(): string {
  const state = readStorageState();
  const origins = Array.isArray(state.origins) ? state.origins : [];

  const preferredOrigin = origins.find((origin) => origin.origin === getFrontendOrigin());
  const preferredToken = findAccessToken(preferredOrigin);
  if (preferredToken) {
    return preferredToken;
  }

  for (const origin of origins) {
    const token = findAccessToken(origin);
    if (token) {
      return token;
    }
  }

  return '';
}
