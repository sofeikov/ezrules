import { spawn } from 'child_process';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { writeRuntimeConfig } from './write-runtime-config.mjs';

writeRuntimeConfig();

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const ngEntryPoint = join(currentDirectory, '..', 'node_modules', '@angular', 'cli', 'bin', 'ng.js');
const child = spawn(process.execPath, [ngEntryPoint, 'serve', ...process.argv.slice(2)], {
  env: process.env,
  stdio: 'inherit',
});

child.on('exit', (code) => {
  process.exit(code ?? 0);
});
