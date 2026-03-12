import { resolveRuntimeApiUrl } from './runtime-config';

export const environment = {
  production: true,
  apiUrl: resolveRuntimeApiUrl('http://localhost:8888'),  // Update this for production deployment
};
