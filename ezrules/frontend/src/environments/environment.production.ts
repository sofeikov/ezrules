import { resolveRuntimeApiUrl } from './runtime-config';

export const environment = {
  production: true,
  apiUrl: resolveRuntimeApiUrl(''),
};
