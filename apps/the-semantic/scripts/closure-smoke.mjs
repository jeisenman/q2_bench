import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const dir = await mkdtemp(path.join(tmpdir(), 'semantic-closure-'));
const spec = {...JSON.parse(await readFile(root + 'examples/research.json', 'utf8')), max_seconds: 8};
const agent = {...JSON.parse(await readFile(root + 'examples/agent.json', 'utf8')),
  definition_digest: 'a'.repeat(64), mlflow_run_id: 'fixture-agent'};
let record = {research_id: 'fixture-research', experiment_id: 'fixture-experiment', attempt_id: 'fixture-attempt',
  title: spec.title, question: spec.question, hypothesis: spec.hypothesis, plan: spec.plan,
  agent_id: agent.id, agent_version: agent.version, agent_definition_digest: agent.definition_digest,
  model: agent.model, page_plugin: agent.page_plugin, created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  status: 'RUNNING', max_runs: 1, max_seconds: spec.max_seconds, output: null, metrics: {}, trace_id: null, error: null};
let completion;
const server = createServer(async (req, res) => {
  let body = ''; for await (const chunk of req) body += chunk;
  res.setHeader('Content-Type', 'application/json');
  if (req.method === 'POST' && req.url === '/api/research/v1/research') {
    assert.deepEqual(JSON.parse(body), spec); res.writeHead(201); res.end(JSON.stringify(record));
  } else if (req.method === 'GET' && req.url === '/api/research/v1/agents/' + agent.id + '?version=1') {
    res.end(JSON.stringify(agent));
  } else if (req.method === 'POST' && req.url === '/api/research/v1/research/fixture-research/complete') {
    completion = JSON.parse(body);
    const {sdk_events: _, ...terminal} = completion;
    record = {...record, ...terminal, trace_id: 'fixture-native-trace', updated_at: new Date().toISOString()};
    res.end(JSON.stringify(record));
  } else { res.writeHead(404); res.end(JSON.stringify({error:{code:'fixture_route',message:'Unexpected fixture route'}})); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const fake = path.join(dir, 'codex-fixture');
await writeFile(fake, "#!/usr/bin/env node\nlet prompt='';process.stdin.on('data',c=>prompt+=c);process.stdin.on('end',()=>{\n if(!prompt.includes('January 18')||!process.argv.includes('gpt-5.6-sol'))process.exit(2);\n require('node:fs').writeFileSync(process.env.FIXTURE_MARKER,'called');\n for(const event of [\n {type:'thread.started',thread_id:'fixture-thread'},\n {type:'item.completed',item:{type:'agent_message',text:'Fixture total 72; mean 24.'}},\n {type:'turn.completed',usage:{input_tokens:7,output_tokens:5}}\n ])console.log(JSON.stringify(event));\n});", {mode:0o700});
await writeFile(path.join(dir, 'spec.json'), JSON.stringify(spec));
let child;
try {
  const address = server.address();
  let output = '';
  const result = await new Promise((resolve, reject) => {
    child = spawn(root + 'target/debug/researcher-codex', ['run','--spec',path.join(dir,'spec.json')], {
      cwd: root, detached: true, env:{...process.env, SEMANTIC_API_URL:'http://127.0.0.1:'+address.port,
        CODEX_BINARY:fake, CODEX_HOME:dir, FIXTURE_MARKER:path.join(dir,'called')}, stdio:['ignore','pipe','pipe']});
    const timer = setTimeout(()=>{try{process.kill(-child.pid,'SIGKILL')}catch{} reject(new Error('Real SDK closure timed out'));},15000);
    child.stdout.on('data',c=>output+=c); child.stderr.resume();
    child.on('error',error=>{clearTimeout(timer);reject(error)});
    child.on('close',code=>{clearTimeout(timer);resolve(code)});
  });
  assert.equal(result,0); assert.equal(await readFile(path.join(dir,'called'),'utf8'),'called');
  const saved = JSON.parse(output); assert.equal(saved.status,'FINISHED');
  assert.equal(saved.output,'Fixture total 72; mean 24.'); assert.equal(saved.metrics.sdk_model_calls,1);
  assert.equal(saved.metrics.input_tokens,7); assert.equal(saved.metrics.output_tokens,5);
  assert.ok(completion.sdk_events.some(e=>e.event==='span.end'));
  console.log('PASS: real Rust CLI -> real Agents SDK -> Rust bridge -> fixture Codex -> API completion.');
} finally {
  if(child?.pid){try{process.kill(-child.pid,'SIGKILL')}catch{}}
  await new Promise(resolve=>server.close(resolve)); await rm(dir,{recursive:true,force:true});
}
