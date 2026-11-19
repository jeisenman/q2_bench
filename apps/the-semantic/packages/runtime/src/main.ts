import { readFile, stat } from 'node:fs/promises';
import { execute } from './run.js';

try {
  if (process.argv.length !== 4 || process.argv[2] !== '--request') throw new Error('Usage: node main.js --request <request.json>');
  const path = process.argv[3]!;
  if ((await stat(path)).size > 200_000) throw new Error('Runtime request exceeds 200 KB.');
  const raw: unknown = JSON.parse(await readFile(path, 'utf8'));
  const result = await execute(raw, process.env.SEMANTIC_CLI ?? '');
  process.stdout.write(JSON.stringify(result) + '\n');
} catch {
  process.stderr.write('Invalid runtime request. Supply a bounded accepted specification and pinned agent.\n');
  process.exitCode = 2;
}
