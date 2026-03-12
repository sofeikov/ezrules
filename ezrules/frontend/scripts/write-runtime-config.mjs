import { mkdirSync, writeFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

export function writeRuntimeConfig() {
  const apiUrl = (process.env.EZRULES_FRONTEND_API_URL ?? process.env.E2E_API_BASE_URL ?? '').trim();
  const scriptContents = apiUrl
    ? `window.__EZRULES_RUNTIME_CONFIG__ = { apiUrl: ${JSON.stringify(apiUrl)} };\n`
    : 'window.__EZRULES_RUNTIME_CONFIG__ = {};\n';

  const currentDirectory = dirname(fileURLToPath(import.meta.url));
  const publicDirectory = join(currentDirectory, '..', 'public');
  const outputPath = join(publicDirectory, 'runtime-config.js');

  mkdirSync(publicDirectory, { recursive: true });
  writeFileSync(outputPath, scriptContents, 'utf8');
}

writeRuntimeConfig();
