import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { execute } from '../dist/run.js';
import { RuntimeRequestSchema, ResearchRecordSchema } from '../dist/contracts.js';

const agent = { id: 'test-agent', version: '1', name: 'Test Agent', purpose: 'Test one accepted plan.',
  instructions: 'Use supplied plan only.', model: 'exact-test-model', allowed_tools: [], page_plugin: 'run-summary',
  definition_digest: 'a'.repeat(64), mlflow_run_id: 'agent-run' };
const request = { research_id: 'research-run', attempt_id: 'attempt-run', agent,
  spec: { title: 'Test', question: 'What is four?', hypothesis: 'It is 2 + 2.', plan: 'Compute it.', agent_id: agent.id,
    agent_version: '1', accepted: true, max_runs: 1, max_seconds: 5, idempotency_key: 'test-once' } };
async function fixture(body, action) {
  const dir = await mkdtemp(path.join(tmpdir(), 'semantic-runtime-'));
  const cli = path.join(dir, 'fake-rust'); const capture = path.join(dir, 'capture.json');
  await writeFile(cli, `#!/usr/bin/env node\nlet raw='';process.stdin.on('data',c=>raw+=c);process.stdin.on('end',()=>{${body}});\n`, { mode: 0o700 });
  try { await action(cli, capture); } finally { delete process.env.SEMANTIC_DEADLINE_MS; await rm(dir, { recursive: true, force: true }); }
}
test('strict accepted specification rejects unsupported runs, tools and mismatched agent', () => {
  for (const raw of [ { ...request, extra: true }, { ...request, spec: { ...request.spec, accepted: false } },
    { ...request, spec: { ...request.spec, max_runs: 2 } }, { ...request, spec: { ...request.spec, max_seconds: 301 } },
    { ...request, agent: { ...agent, allowed_tools: ['shell'] } }, { ...request, agent: { ...agent, version: '2' } } ]) {
    assert.equal(RuntimeRequestSchema.safeParse(raw).success, false);
  }
});
test('actual SDK calls exact Rust model once and retains real usage and only metadata', async () => {
  await fixture("require('node:fs').writeFileSync(process.env.TEST_CAPTURE,JSON.stringify({args:process.argv.slice(2),payload:JSON.parse(raw)}));process.stdout.write(JSON.stringify({output:'actual fixture answer',input_tokens:17,output_tokens:4,duration_seconds:0.25}));", async (cli, capture) => {
    process.env.TEST_CAPTURE = capture;
    const result = await execute(request, cli);
    assert.equal(result.status, 'FINISHED'); assert.equal(result.output, 'actual fixture answer');
    assert.equal(result.metrics.input_tokens, 17); assert.equal(result.metrics.output_tokens, 4);
    assert.equal(result.metrics.duration_seconds, 0.25); assert.equal(result.metrics.sdk_model_calls, 1);
    assert.equal(result.metrics.provider_warning_count, 0);
    const sent = JSON.parse(await readFile(capture, 'utf8'));
    assert.deepEqual(sent.args.slice(0, 3), ['complete', '--model', agent.model]);
    assert.equal(sent.payload.instructions, agent.instructions);
    for (const part of [request.spec.question, request.spec.hypothesis, request.spec.plan]) assert.ok(sent.payload.input.includes(part));
    assert.ok(result.sdk_events.some(e => e.event === 'span.end'));
    for (const event of result.sdk_events) assert.ok(Object.keys(event).every(k => ['event','trace_id','span_id','type'].includes(k)));
    assert.ok(!JSON.stringify(result.sdk_events).includes(agent.instructions));
    delete process.env.TEST_CAPTURE;
  });
});
test('provider failure, invalid evidence, missing executable and deadline are terminal', async () => {
  await fixture("process.stdout.write(JSON.stringify({error:{code:'model_access_denied',message:'Selected model unavailable.'}}));process.exitCode=1;", async cli => {
    const result = await execute(request, cli); assert.equal(result.status, 'FAILED'); assert.match(result.error, /model_access_denied/);
  });
  await fixture("process.stdout.write(JSON.stringify({output:'bad',input_tokens:-1,output_tokens:2,duration_seconds:1}));", async cli => {
    const result = await execute(request, cli); assert.equal(result.status, 'FAILED'); assert.equal(result.output, '');
  });
  assert.equal((await execute(request, '/nonexistent/semantic-test-executable')).status, 'FAILED');
  await fixture("setTimeout(()=>{},5000);", async cli => {
    process.env.SEMANTIC_DEADLINE_MS = String(Date.now() + 150);
    const start = Date.now(); const result = await execute(request, cli);
    assert.equal(result.status, 'KILLED'); assert.ok(Date.now() - start < 1500);
  });
});
test('research evidence rejects NaN and unsupported statuses', () => {
  assert.equal(ResearchRecordSchema.safeParse({ metrics: { input_tokens: NaN }, status: 'SUCCESS' }).success, false);
});

test('preserves provider warning count and rejects invalid warning evidence', async () => {
  await fixture("process.stdout.write(JSON.stringify({output:'warning fixture',input_tokens:1,output_tokens:2,duration_seconds:0.1,warning_count:2}));", async cli => {
    const result = await execute(request, cli); assert.equal(result.status, 'FINISHED'); assert.equal(result.metrics.provider_warning_count, 2);
  });
  for (const warning_count of [-1, 0.5]) {
    await fixture(`process.stdout.write(JSON.stringify({output:'invalid warning',input_tokens:1,output_tokens:2,duration_seconds:0.1,warning_count:${warning_count}}));`, async cli => {
      const result = await execute(request, cli); assert.equal(result.status, 'FAILED'); assert.equal(result.output, '');
    });
  }
});
