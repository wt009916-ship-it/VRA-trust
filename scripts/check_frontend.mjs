import { spawnSync } from 'node:child_process';
for (const path of ['frontend/src/main.js', 'frontend/src/api.js', 'frontend/src/layout.js']) {
  const r = spawnSync(process.execPath, ['--check', path], { stdio: 'inherit' });
  if (r.status !== 0) process.exit(r.status || 1);
}
console.log('Frontend syntax checks passed');
