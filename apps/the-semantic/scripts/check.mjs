import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const checks = [
  ['npm', ['run', 'build:host']],
  ['cargo', ['fmt', '--all', '--', '--check']],
  ['cargo', ['clippy', '--workspace', '--all-targets', '--', '-D', 'warnings']],
  ['cargo', ['test', '--workspace']],
  ['uv', ['run', '--project', 'server', 'ruff', 'check', 'server']],
  ['uv', ['run', '--project', 'server', 'ruff', 'format', '--check', 'server']],
  ['uv', ['run', '--project', 'server', 'pytest', 'server/tests', '-q']],
  ['npm', ['run', 'check']],
  ['npm', ['test']],
  ['npm', ['run', 'build']],
  ['node', ['scripts/closure-smoke.mjs']],
];
for (const [command, args] of checks) {
  const result = spawnSync(command, args, {cwd: root, stdio: 'inherit'});
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
const files = spawnSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', '.'], {cwd: root, encoding: 'utf8'});
if (files.status !== 0) throw new Error('Cannot inspect source lengths.');
for (const path of new Set(files.stdout.split(String.fromCharCode(0)).filter(Boolean))) {
  if (!/\.(?:rs|py|ts|mts|mjs|js|css|html|md)$/.test(path)) continue;
  if (!existsSync(new URL('../' + path, import.meta.url))) continue;
  const count = readFileSync(new URL('../' + path, import.meta.url), 'utf8').split('\n').length - 1;
  if (count > 400) throw new Error(path + ' exceeds 400 lines: ' + count);
}
console.log('All The Semantic checks passed.');
