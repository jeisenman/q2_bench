import { execFile } from 'node:child_process';
import path from 'node:path';
import { homedir } from 'node:os';
import { GherkinRequestSchema, GherkinListSchema, GherkinFeatureSchema, GHERKIN_CAPABILITIES } from './gherkin-contracts.js';
const DEFAULT_ROOT = path.join(homedir(), 'ra', 'pl-application');
const MAX_FEATURES = 10000;
const MAX_SOURCE_BYTES = 1_000_000;
/** Reads only committed Gherkin source. No model or specification execution occurs. */
export async function readGherkin(raw: unknown, root = process.env.SEMANTIC_GHERKIN_ROOT ?? DEFAULT_ROOT): Promise<unknown> {
  const request = GherkinRequestSchema.parse(raw);
  if (request.operation === 'gherkin.capabilities') return GHERKIN_CAPABILITIES;
  if (request.operation === 'gherkin.search' && request.mode === 'vector') throw new Error(GHERKIN_CAPABILITIES.vector.reason);
  if (!path.isAbsolute(root)) throw new Error('Gherkin unavailable: SEMANTIC_GHERKIN_ROOT must be an absolute checkout path.');
  const repository = path.basename(root);
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('GIT_')));
  async function git(args: string[], maxBuffer = 8_000_000, allowNoMatches = false): Promise<Buffer> {
    return new Promise((resolve, reject) => {
      execFile('git', ['--no-replace-objects', '--no-optional-locks', '-C', root, ...args], { timeout: 10000, maxBuffer, env, encoding: 'buffer' }, (error, stdout) => {
        if (error && !(allowNoMatches && 'code' in error && error.code === 1)) {
          reject(new Error('Gherkin unavailable: the committed source could not be read within its size or time limit. Check the configured checkout and commit.'));
        } else resolve(stdout);
      });
    });
  }
  const commit = (await git(['rev-parse', '--verify', `${request.commit ?? 'HEAD'}^{commit}`], 128)).toString('utf8').trim();
  if (!/^[0-9a-f]{40}$/.test(commit) || (request.commit && commit !== request.commit)) throw new Error('Gherkin unavailable: the exact source commit is required.');
  const records = (await git(['ls-tree', '-r', '-z', commit])).toString('utf8').split('\0').filter(Boolean);
  const paths = records.flatMap(record => {
    const match = /^(100644|100755) blob [0-9a-f]{40}\t(.+\.feature)$/s.exec(record);
    return match ? [match[2]!] : [];
  }).sort();
  if (paths.length > MAX_FEATURES) throw new Error('Gherkin unavailable: source exceeds the 10000-feature inventory limit.');
  if (request.operation === 'gherkin.feature') {
    if (!paths.includes(request.path)) throw new Error('Gherkin unavailable: feature is not tracked at the requested commit.');
    const bytes = await git(['show', `${commit}:${request.path}`], MAX_SOURCE_BYTES);
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    return GherkinFeatureSchema.parse({ repository, commit, path: request.path, title: title(request.path), text });
  }
  let matches = paths;
  if (request.operation === 'gherkin.search') {
    const output = (await git(['grep', '-l', '-z', '-i', '-F', '-e', request.query, commit, '--', '*.feature'], 8_000_000, true)).toString('utf8');
    const found = new Set(output.split('\0').filter(Boolean).map(value => value.startsWith(`${commit}:`) ? value.slice(commit.length + 1) : value));
    matches = paths.filter(value => found.has(value));
  }
  return GherkinListSchema.parse({ repository, commit, features: matches.slice(request.offset, request.offset + 25).map(value => ({ path: value, title: title(value) })), count: matches.length, offset: request.offset, has_more: request.offset + 25 < matches.length });
}
function title(value: string): string { return path.posix.basename(value, '.feature').replace(/[_-]+/g, ' '); }
