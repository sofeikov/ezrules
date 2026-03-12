import { resolveRuntimeApiUrl } from './runtime-config';

export const environment = {
  production: false,
  apiUrl: resolveRuntimeApiUrl('http://localhost:8888'),  // Manager service default port
};
