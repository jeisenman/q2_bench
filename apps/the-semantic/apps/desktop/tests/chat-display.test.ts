import test from 'node:test';
import assert from 'node:assert/strict';
import { chatDisplayText } from '../src/chat-display.js';

test('chat projection removes nested execution metadata without changing its source', () => {
  const source={answer:'Loans reviewed',research_id:'private-run',details:{trace_id:'private-trace',metrics:{roe:0.1},input_tokens:500,output_tokens:100,usage:{total_tokens:600},elapsed_ms:900,status:'Complete'}};
  const original=JSON.stringify(source);const projected=chatDisplayText(original);
  assert.deepEqual(JSON.parse(projected),{answer:'Loans reviewed',details:{status:'Complete'}});
  assert.equal(JSON.stringify(source),original);
});
test('chat projection hides labelled metadata and opaque references but keeps public results', () => {
  const source='Association remains unproven.\n**Research run ID:** private-run\ntrace_id: private-trace\ninput_tokens: 500\nelapsed_ms: 900\nWall time: 0.9 seconds\nReference '+ 'a'.repeat(32);
  const result=chatDisplayText(source);
  assert.match(result,/Association remains unproven/);assert.match(result,/\[internal reference\]/);
  assert.doesNotMatch(result,/private-run|private-trace|500|900|0\.9|a{32}/);
  assert.equal(chatDisplayText('{"metrics":{"runtime_duration_seconds":9}}'),'Internal execution metadata omitted.');
  assert.equal(chatDisplayText('Loan duration needs review.'),'Loan duration needs review.');
  assert.equal(chatDisplayText('**Usage:** 512 tokens'),'Internal execution metadata omitted.');
});
