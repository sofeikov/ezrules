import { spawn } from 'child_process';
import { existsSync, readFileSync, unlinkSync, writeFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { writeRuntimeConfig } from './write-runtime-config.mjs';

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const publicRuntimeConfigPath = join(currentDirectory, '..', 'public', 'runtime-config.js');
const previousRuntimeConfig = existsSync(publicRuntimeConfigPath) ? readFileSync(publicRuntimeConfigPath, 'utf8') : null;

writeRuntimeConfig();

let restored = false;

function restoreRuntimeConfig() {
  if (restored) {
    return;
  }
  restored = true;

  if (previousRuntimeConfig === null) {
    if (existsSync(publicRuntimeConfigPath)) {
      unlinkSync(publicRuntimeConfigPath);
    }
    return;
  }

  writeFileSync(publicRuntimeConfigPath, previousRuntimeConfig, 'utf8');
}

const ngEntryPoint = join(currentDirectory, '..', 'node_modules', '@angular', 'cli', 'bin', 'ng.js');
const child = spawn(process.execPath, [ngEntryPoint, 'serve', ...process.argv.slice(2)], {
  env: process.env,
  stdio: 'inherit',
});

child.on('exit', (code) => {
  restoreRuntimeConfig();
  process.exit(code ?? 0);
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    child.kill(signal);
  });
}

process.on('exit', restoreRuntimeConfig);
