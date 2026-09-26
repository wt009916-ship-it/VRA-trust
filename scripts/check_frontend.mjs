import { spawnSync } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const source = new URL('../frontend/src/', import.meta.url);
for (const name of readdirSync(source).filter(name => name.endsWith('.js')).sort()) {
  const path = fileURLToPath(new URL(name, source));
  const r = spawnSync(process.execPath, ['--check', path], { stdio: 'inherit' });
  if (r.status !== 0) process.exit(r.status || 1);
}
console.log('Frontend syntax checks passed');
